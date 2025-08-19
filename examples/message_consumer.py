#!/usr/bin/env python3
"""
消息消费者使用示例

展示如何在不同场景下选择和使用不同的异步消息消费者实现，
包括 VirtualConsumer、PersistentConsumer 和自定义消费者的用法。
"""

import asyncio
import tempfile
import shutil
from typing import Dict, Any

from extensional_agent.agent_sdk import ExecutionContext, set_execution_context, clear_execution_context
from .virtual_consumer import VirtualConsumer
from .persistent_consumer import PersistentConsumer
from extensional_agent.registry import AgentRegistry
from extensional_agent.schemas import AgentEvent


class AsyncExampleAgentRunner:
    """
    异步示例 AgentRunner，展示如何支持可配置的异步消息消费者
    """

    def __init__(self, registry: AgentRegistry, message_consumer=None):
        self.registry = registry
        # 默认使用轻量级实现，也可以通过参数注入其他实现
        self.message_consumer = message_consumer or VirtualConsumer()

    async def run(self, agent_name: str, agent_input: Any) -> Dict[str, Any]:
        """异步运行 Agent，使用注入的消息消费者处理事件"""
        run_id = f"example-{agent_name}-001"

        # 创建执行上下文，注入消息消费者
        ctx = ExecutionContext(
            run_id=run_id,
            agent_name=agent_name,
            seq=iter(range(1, 1000)),
            vc=self.message_consumer,  # 使用注入的消息消费者
        )

        await set_execution_context(ctx)
        try:
            # 模拟 Agent 执行过程中的事件（emit_event 会异步处理）
            from extensional_agent.agent_sdk import emit_event
            from extensional_agent.schemas import ExecutionRecord, Role
            from uuid import uuid4

            # 创建执行记录并发送事件
            stream_1_uuid = uuid4()
            record1 = ExecutionRecord(
                id=stream_1_uuid,
                index=0,
                role=Role.ASSISTANT,
                reasoning_content=f"开始执行 {agent_name} Agent",
                content=f"正在查询 {agent_input.city} 的天气信息",
                is_stop=False,
            )
            await emit_event(execution_record=record1)

            # 添加一些延迟来模拟真实的异步操作
            await asyncio.sleep(0.1)

            record2 = ExecutionRecord(
                id=stream_1_uuid,
                index=1,
                role=Role.TOOL,
                reasoning_content="调用天气 API 获取基础天气数据",
                content={"tool": "weather_api", "args": {"city": agent_input.city}},
                is_stop=True,
            )
            await emit_event(execution_record=record2)

            await asyncio.sleep(0.1)

            stream_2_uuid = uuid4()
            record3 = ExecutionRecord(
                id=stream_2_uuid,
                index=0,
                role=Role.TOOL,
                reasoning_content="获取空气质量数据",
                content={"status": "success", "aqi": 45, "pm25": 12},
                is_stop=True,
            )
            await emit_event(execution_record=record3)

            await asyncio.sleep(0.1)

            stream_3_uuid = uuid4()
            record4 = ExecutionRecord(
                id=stream_3_uuid,
                index=0,
                role=Role.ASSISTANT,
                reasoning_content="分析天气趋势",
                content={"forecast": "rainy", "confidence": 0.85},
                is_stop=False,
            )
            await emit_event(execution_record=record4)

            await asyncio.sleep(0.1)

            record5 = ExecutionRecord(
                id=stream_3_uuid,
                index=1,
                role=Role.ASSISTANT,
                reasoning_content="生成天气建议",
                content={
                    "advice": "建议携带雨具",
                    "temperature": "22°C",
                },
                is_stop=True,
            )
            await emit_event(execution_record=record5)

            # 给异步事件处理一些时间
            await asyncio.sleep(0.2)

            # 模拟返回结果
            return {"run_id": run_id, "weather_status": "completed", "advice": "建议携带雨具"}

        finally:
            await clear_execution_context()


async def demonstrate_virtual_consumer():
    """演示轻量级 VirtualConsumer 的异步使用"""
    print("=== 演示 VirtualConsumer（轻量级异步内存实现）===")

    # 创建轻量级消息消费者
    vc = VirtualConsumer(max_per_run=1000)

    # 异步订阅事件
    async def event_listener(event: AgentEvent):
        execution_record = event.execution_record
        role = execution_record.role
        reasoning = execution_record.reasoning_content if execution_record.reasoning_content else ""
        content = execution_record.content

        # 如果 content 是字典，提取关键信息
        content_display = ""
        if isinstance(content, dict):
            if "tool" in content:
                content_display = f"调用工具: {content['tool']}"
            elif "status" in content:
                content_display = f"状态: {content['status']}"
            elif "advice" in content:
                content_display = f"天气建议: {content['advice']}"
            else:
                content_display = (
                    str(content)[:50] + "..."
                    if len(str(content)) > 50
                    else str(content)
                )
        else:
            content_display = (
                str(content)[:50] + "..." if len(str(content)) > 50 else str(content)
            )

        print(
            f"  📡 实时事件: [{event.seq}] {role} - {reasoning[:30]}... | {content_display}"
        )

    token = await vc.subscribe("example-weather-001", event_listener)

    # 创建 Runner 并异步运行
    registry = AgentRegistry()  # 空注册表，仅用于演示
    runner = AsyncExampleAgentRunner(registry, vc)

    agent_input = {"city": "北京", "apis": None}
    result = await runner.run("weather", agent_input)

    print(f"  ✅ 执行完成: {result}")

    # 异步查看历史事件
    events = await vc.get_events("example-weather-001")
    print(f"  📚 历史事件总数: {len(events)}")

    # 异步取消订阅
    await vc.unsubscribe("example-weather-001", token)
    print()


async def demonstrate_persistent_consumer():
    """演示持久化 PersistentConsumer 的异步使用"""
    print("=== 演示 PersistentConsumer（持久化异步实现）===")

    temp_dir = tempfile.mkdtemp()
    print(f"  💾 使用临时存储目录: {temp_dir}")

    try:
        # 创建持久化消息消费者
        pc = PersistentConsumer(
            storage_path=temp_dir,
            max_memory_events=100,
            batch_size=10,
            flush_interval=2,
            retention_days=7,
        )

        # 异步订阅事件
        async def event_listener(event: AgentEvent):
            execution_record = event.execution_record
            role = execution_record.role
            reasoning = (
                execution_record.reasoning_content[:30] + "..."
                if execution_record.reasoning_content
                else "无推理内容"
            )
            print(f"  📡 实时事件: [{event.seq}] {role} - {reasoning}")

        token = await pc.subscribe("example-weather-001", event_listener)

        # 创建 Runner 并异步运行
        registry = AgentRegistry()
        runner = AsyncExampleAgentRunner(registry, pc)

        agent_input = {"city": "上海", "apis": None}
        result = await runner.run("weather", agent_input)

        print(f"  ✅ 执行完成: {result}")

        # 异步显示统计信息
        stats = await pc.get_stats()
        print("  📊 统计信息:")
        print(f"     - 内存事件数: {stats['memory_events']}")
        print(f"     - 磁盘文件数: {stats['disk_files']}")
        print(f"     - 缓冲区大小: {stats['buffer_size']}")
        print(f"     - 活跃订阅者: {stats['subscribers']}")

        # 异步取消订阅并清理
        await pc.unsubscribe("example-weather-001", token)
        await pc.cleanup("example-weather-001")

    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)

    print()


async def demonstrate_custom_consumer():
    """演示如何创建自定义异步消息消费者"""
    print("=== 演示自定义异步 MessageConsumer（天气数据处理实现）===")

    from extensional_agent.message_consumer import MessageConsumer, AsyncCallback

    class AsyncWeatherDataConsumer(MessageConsumer):
        """专门处理天气数据的异步消息消费者（用于演示继承）"""

        def __init__(self):
            self._subscribers = {}
            self._next_token = 1
            self._events = {}

        async def publish(self, event):
            run_id = event.run_id
            execution_record = event.execution_record
            role = execution_record.role
            print(f"  🌤️ 异步天气数据处理: {run_id} - {role}({event.seq})")

            # 保存到内存（简化实现）
            if run_id not in self._events:
                self._events[run_id] = []
            self._events[run_id].append(event)

            # 异步通知订阅者
            for cb in self._subscribers.get(run_id, {}).values():
                await self._safe_callback(cb, event)

        async def subscribe(self, run_id, callback):
            if run_id not in self._subscribers:
                self._subscribers[run_id] = {}
            token = self._next_token
            self._next_token += 1
            self._subscribers[run_id][token] = callback
            return token

        async def unsubscribe(self, run_id, token):
            self._subscribers.get(run_id, {}).pop(token, None)

        async def get_events(
            self, run_id, after_seq=0, callback: AsyncCallback | None = None
        ):
            events = self._events.get(run_id, [])
            return [e for e in events if e.get("seq", 0) > after_seq]

        async def get_weather_summary(self, run_id):
            """自定义异步方法：获取天气数据摘要"""
            events = self._events.get(run_id, [])
            weather_data = {}
            for event in events:
                content = event.get("content", {})
                if isinstance(content, dict):
                    # 合并天气数据
                    weather_data.update(content)
            return weather_data

    # 使用自定义异步消费者
    wc = AsyncWeatherDataConsumer()
    registry = AgentRegistry()
    runner = AsyncExampleAgentRunner(registry, wc)

    agent_input = {"city": "深圳", "apis": None}
    result = await runner.run("weather", agent_input)

    print(f"  ✅ 执行完成: {result}")

    # 使用自定义异步方法
    summary = await wc.get_weather_summary("example-weather-001")
    print(f"  📈 天气数据摘要: {summary}")
    print()


async def main():
    """主异步函数"""
    print("🚀 异步消息消费者使用示例")
    print("展示如何在不同场景下选择合适的异步消息消费者实现\n")

    # 演示不同的异步消息消费者实现
    await demonstrate_virtual_consumer()
    await demonstrate_persistent_consumer()
    await demonstrate_custom_consumer()

    print("💡 总结:")
    print("- VirtualConsumer: 适合开发测试天气应用，异步内存实现，轻量快速")
    print("- PersistentConsumer: 适合生产环境天气服务，异步持久化，功能完整")
    print("- 自定义 WeatherConsumer: 继承 MessageConsumer 实现天气数据特殊处理需求")
    print("- AgentRunner 通过依赖注入支持不同异步实现，无需修改核心代码")


if __name__ == "__main__":
    asyncio.run(main())
