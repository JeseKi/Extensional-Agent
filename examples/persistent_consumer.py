"""
持久化消息消费者示例实现

展示如何继承和扩展 MessageConsumer 基类，实现生产级的消息处理能力。
该实现结合了内存缓存和持久化存储，适合生产环境使用。
"""

from __future__ import annotations
from typing import Any, Dict, List
from collections import defaultdict, deque
import json
import asyncio
import time
from pathlib import Path

from extensional_agent.message_consumer import MessageConsumer, AsyncCallback
from extensional_agent.schemas import AgentEvent


class PersistentConsumer(MessageConsumer):
    """
    持久化消息消费者实现

    结合内存缓存和持久化存储的消息消费者，适合生产环境：
    - 内存缓存：提供快速的实时访问
    - 持久化存储：确保数据不丢失
    - 批量写入：提高存储性能
    - 自动清理：避免磁盘空间无限增长

    适用场景：
    - 生产环境
    - 需要数据持久化的场景
    - 高可用性要求
    - 审计和合规要求

    特性：
    - 双重保障：内存 + 磁盘存储
    - 批量操作：减少 I/O 开销
    - 自动清理：按时间/大小清理历史数据
    - 线程安全：支持并发访问
    """

    def __init__(
        self,
        storage_path: str = "./agent_events",
        max_memory_events: int = 1000,
        batch_size: int = 100,
        flush_interval: int = 10,
        retention_days: int = 30,
    ) -> None:
        """
        初始化持久化消息消费者

        Args:
            storage_path: 存储路径
            max_memory_events: 内存中保留的事件数量
            batch_size: 批量写入大小
            flush_interval: 刷新间隔（秒）
            retention_days: 数据保留天数
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.max_memory_events = max_memory_events
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.retention_days = retention_days

        # 内存缓存：快速访问最近的事件
        self._memory_events = defaultdict(lambda: deque(maxlen=max_memory_events))

        # 订阅者管理
        self._subscribers: defaultdict[str, Dict[int, AsyncCallback]] = defaultdict(
            dict
        )
        self._next_token = 1
        self._lock = asyncio.Lock()

        # 批量写入缓冲区
        self._write_buffer = []
        self._last_flush = time.time()

        # 启动后台任务
        asyncio.create_task(self._background_worker())

    async def publish(self, event: AgentEvent) -> None:
        """异步发布事件：同时写入内存缓存和持久化缓冲区"""
        async with self._lock:
            # 从 AgentEvent 对象获取 run_id
            run_id = event.run_id

            # 写入内存缓存（用于快速访问）
            self._memory_events[run_id].append(event)

            # 添加到持久化缓冲区（转为字典存储到磁盘）
            self._write_buffer.append(event.model_dump())

            # 检查是否需要立即刷新
            if (
                len(self._write_buffer) >= self.batch_size
                or time.time() - self._last_flush >= self.flush_interval
            ):
                await self._flush_to_disk()

            # 异步通知订阅者
            tasks = []
            for token, cb in list(self._subscribers[run_id].items()):
                tasks.append(self._safe_callback(cb, event))

            # 并行执行所有回调，但不等待完成（避免阻塞发布）
            if tasks:
                for task in tasks:
                    asyncio.create_task(task)

    async def subscribe(self, run_id: str, callback: AsyncCallback) -> int:
        """异步订阅指定 runId 的实时事件"""
        async with self._lock:
            token = self._next_token
            self._next_token += 1
            self._subscribers[run_id][token] = callback
            return token

    async def unsubscribe(self, run_id: str, token: int) -> None:
        """异步取消订阅"""
        async with self._lock:
            self._subscribers[run_id].pop(token, None)

    async def get_events(
        self, run_id: str, after_seq: int = 0, callback: AsyncCallback | None = None
    ) -> List[AgentEvent]:
        """异步获取历史事件：先从内存查找，不足时从磁盘补充"""
        async with self._lock:
            # 首先从内存缓存获取 AgentEvent 对象
            memory_events = [
                e
                for e in self._memory_events.get(run_id, [])
                if e.seq > after_seq
            ]

            # 如果内存中的事件足够，直接返回
            if memory_events and memory_events[0].seq <= after_seq + 1:
                return memory_events

            # 否则异步从磁盘读取完整历史（字典格式），然后转换为 AgentEvent
            disk_event_dicts = await self._load_from_disk(run_id, after_seq)
            disk_events = [AgentEvent(**event_dict) for event_dict in disk_event_dicts]

            # 合并并去重
            all_events = {e.seq: e for e in disk_events + memory_events}
            return [
                all_events[seq] for seq in sorted(all_events.keys()) if seq > after_seq
            ]

    async def cleanup(self, run_id: str) -> None:
        """异步清理指定 runId 的资源"""
        async with self._lock:
            # 清理内存缓存
            self._memory_events.pop(run_id, None)
            self._subscribers.pop(run_id, None)

            # 异步删除磁盘文件
            run_file = self.storage_path / f"{run_id}.jsonl"
            if run_file.exists():
                await asyncio.to_thread(run_file.unlink)

    async def _flush_to_disk(self) -> None:
        """异步将缓冲区的事件批量写入磁盘"""
        if not self._write_buffer:
            return

        # 按 runId 分组（此时 _write_buffer 中存储的是字典格式）
        events_by_run = defaultdict(list)
        for event_dict in self._write_buffer:
            # 从字典中获取 run_id
            run_id = event_dict.get("run_id", "unknown")
            events_by_run[run_id].append(event_dict)

        # 异步批量写入各个文件
        async def write_events_to_file(
            run_id: str, events: List[Dict[str, Any]]
        ) -> None:
            run_file = self.storage_path / f"{run_id}.jsonl"
            content = ""
            for event in events:
                content += json.dumps(event, ensure_ascii=False) + "\n"

            # 使用 asyncio.to_thread 来异步执行文件写入
            await asyncio.to_thread(self._write_file_sync, run_file, content)

        # 并行写入所有文件
        tasks = [
            write_events_to_file(run_id, events)
            for run_id, events in events_by_run.items()
        ]
        await asyncio.gather(*tasks)

        # 清空缓冲区
        self._write_buffer.clear()
        self._last_flush = time.time()

    def _write_file_sync(self, file_path: Path, content: str) -> None:
        """同步写入文件（在异步上下文中通过 to_thread 调用）"""
        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)

    async def _load_from_disk(
        self, run_id: str, after_seq: int = 0
    ) -> List[Dict[str, Any]]:
        """异步从磁盘加载指定 runId 的事件"""
        run_file = self.storage_path / f"{run_id}.jsonl"
        if not run_file.exists():
            return []

        # 使用 asyncio.to_thread 来异步执行文件读取
        return await asyncio.to_thread(self._read_events_sync, run_file, after_seq)

    def _read_events_sync(
        self, file_path: Path, after_seq: int
    ) -> List[Dict[str, Any]]:
        """同步读取事件文件（在异步上下文中通过 to_thread 调用）"""
        events = []
        with file_path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if int(event.get("seq", 0)) > after_seq:
                        events.append(event)
                except (json.JSONDecodeError, ValueError):
                    continue
        return events

    async def _background_worker(self) -> None:
        """异步后台任务：定期刷新和清理"""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                async with self._lock:
                    await self._flush_to_disk()
                    await self._cleanup_old_files()
            except Exception:
                pass  # 忽略后台任务异常

    async def _cleanup_old_files(self) -> None:
        """异步清理过期的存储文件"""
        cutoff_time = time.time() - (self.retention_days * 24 * 3600)

        # 使用 asyncio.to_thread 来异步执行文件系统操作
        await asyncio.to_thread(self._cleanup_old_files_sync, cutoff_time)

    def _cleanup_old_files_sync(self, cutoff_time: float) -> None:
        """同步清理过期文件（在异步上下文中通过 to_thread 调用）"""
        for file_path in self.storage_path.glob("*.jsonl"):
            try:
                if file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
            except Exception:
                pass  # 忽略清理异常

    async def get_stats(self) -> Dict[str, Any]:
        """异步获取消费者统计信息"""
        async with self._lock:
            memory_count = sum(len(events) for events in self._memory_events.values())

            # 异步获取磁盘文件数量
            disk_files = await asyncio.to_thread(
                lambda: len(list(self.storage_path.glob("*.jsonl")))
            )

            return {
                "memory_events": memory_count,
                "disk_files": disk_files,
                "buffer_size": len(self._write_buffer),
                "subscribers": sum(len(subs) for subs in self._subscribers.values()),
                "storage_path": str(self.storage_path),
                "retention_days": self.retention_days,
            }
