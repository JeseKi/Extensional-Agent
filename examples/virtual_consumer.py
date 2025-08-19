from __future__ import annotations
from typing import Dict, List, DefaultDict
from collections import defaultdict, deque
import asyncio

from extensional_agent.message_consumer import MessageConsumer, AsyncCallback
from extensional_agent.schemas import AgentEvent


class VirtualConsumer(MessageConsumer):
    """
    轻量级"虚拟消费者"实现

    基于内存的消息消费者实现，适合开发和轻量级部署场景：
    - 为每个 runId 维护一个限长的事件队列（环形缓冲）
    - 支持按 runId 级别的订阅，实时回调事件
    - 支持基于 after_seq 的增量读取
    - 进程重启后数据丢失（纯内存实现）

    适用场景：
    - 开发和测试环境
    - 单机部署
    - 对数据持久化要求不高的场景

    不适用场景：
    - 生产环境需要数据持久化
    - 分布式部署
    - 高可用性要求
    """

    def __init__(self, max_per_run: int = 5000) -> None:
        self._events: DefaultDict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_per_run)
        )
        # 维护订阅者表：run_id -> {token: callback}
        self._subscribers: DefaultDict[str, Dict[int, AsyncCallback]] = defaultdict(
            dict
        )
        self._next_token: int = 1

    async def publish(self, event: AgentEvent) -> None:
        # 从 AgentEvent 对象获取 run_id
        run_id = event.run_id
        self._events[run_id].append(event)

        # 异步通知所有订阅者
        tasks = []
        for token, cb in list(self._subscribers[run_id].items()):
            tasks.append(self._safe_callback(cb, event))

        # 并行执行所有回调，但不等待完成（避免阻塞发布）
        if tasks:
            # 使用 create_task 确保所有回调都被安排执行
            for task in tasks:
                asyncio.create_task(task)

    async def subscribe(self, run_id: str, callback: AsyncCallback) -> int:
        token = self._next_token
        self._next_token += 1
        self._subscribers[run_id][token] = callback
        return token

    async def unsubscribe(self, run_id: str, token: int) -> None:
        try:
            self._subscribers[run_id].pop(token, None)
        except Exception:
            pass

    async def get_events(
        self, run_id: str, after_seq: int = 0, callback: AsyncCallback | None = None
    ) -> List[AgentEvent]:
        return [
            e for e in self._events.get(run_id, []) if e.seq > after_seq
        ]

    async def cleanup(self, run_id: str) -> None:
        """异步清理指定 runId 的资源"""
        try:
            self._events.pop(run_id, None)
            self._subscribers.pop(run_id, None)
        except Exception:
            pass
