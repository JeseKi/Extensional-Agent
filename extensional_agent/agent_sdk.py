from __future__ import annotations
from typing import Optional, Union, Iterator
from datetime import datetime, timezone
import contextvars
import asyncio

from .message_consumer import MessageConsumer
from .schemas import (
    ExecutionRecord,
    AgentEvent,
    AgentExecutionContext,
    EmitEventWarning,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionContext:
    """
    Agent 执行上下文
    """

    def __init__(
        self,
        run_id: str,
        agent_name: str,
        seq: Iterator[int],
        vc: MessageConsumer,
        first_seq: Optional[int] = None,
        last_seq: Optional[int] = None,
    ):
        self.run_id = run_id
        self.agent_name = agent_name
        self.seq = seq
        self.vc = vc
        self.first_seq = first_seq
        self.last_seq = last_seq

    def to_model(self) -> AgentExecutionContext:
        """转换为 Pydantic 模型"""
        return AgentExecutionContext(
            run_id=self.run_id,
            agent_name=self.agent_name,
            first_seq=self.first_seq,
            last_seq=self.last_seq,
        )


# 运行时上下文（通过 contextvars 注入），使插件无需改变签名即可发事件
_current_ctx: contextvars.ContextVar[Optional[ExecutionContext]] = (
    contextvars.ContextVar("current_agent_execution_ctx", default=None)
)


async def set_execution_context(ctx: ExecutionContext) -> None:
    _current_ctx.set(ctx)


async def clear_execution_context() -> None:
    _current_ctx.set(None)


async def emit_event(
    *,
    execution_record: ExecutionRecord,
    version: int = 1,
) -> Union[AgentEvent, EmitEventWarning]:
    """
    由插件调用的极简事件发射 API。基于 contextvars 获取运行时注入的消息消费者，
    自动维护顺序号并发布事件。
    插件不需要也不应该关心具体的消息消费者实现（内存/数据库/分布式等）。

    Returns:
        AgentEvent: 成功发布的事件对象
        EmitEventWarning: 当没有执行上下文时返回的警告
    """
    ctx = _current_ctx.get()
    if ctx is None:
        # 允许在无上下文时调用，不打断主流程（便于本地测试）
        return EmitEventWarning(warning="no_execution_context")

    try:
        seq_value = next(ctx.seq)
    except StopIteration:
        # 极端情况下迭代器耗尽，重新开始（确保不中断执行）
        seq_value = (ctx.last_seq or 0) + 1

    # 创建结构化的事件对象
    event = AgentEvent(
        v=version,
        run_id=ctx.run_id,
        seq=seq_value,
        timestamp=_now_iso(),
        agent=ctx.agent_name,
        execution_record=execution_record
    )

    if ctx.first_seq is None:
        ctx.first_seq = seq_value
    ctx.last_seq = seq_value

    # 异步发布到消息消费者（由具体实现决定广播/持久化策略）
    # 使用 create_task 确保异步调用被正确安排，但不阻塞当前执行
    try:
        # 直接发布 AgentEvent 对象
        asyncio.create_task(ctx.vc.publish(event))
    except RuntimeError:
        # 如果没有运行的事件循环，创建一个新的来执行发布操作
        import threading

        def run_in_thread():
            asyncio.run(ctx.vc.publish(event))

        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()

    return event


def current_run_id() -> Optional[str]:
    ctx = _current_ctx.get()
    return ctx.run_id if ctx else None


def current_agent_name() -> Optional[str]:
    ctx = _current_ctx.get()
    return ctx.agent_name if ctx else None
