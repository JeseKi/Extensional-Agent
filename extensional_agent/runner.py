from __future__ import annotations
import uuid

from pydantic import BaseModel

from .message_consumer import MessageConsumer
from .agent_sdk import ExecutionContext, set_execution_context, clear_execution_context
from .registry import AgentRegistry
from .agent_base import ITanWeAIAgent


def _new_run_id() -> str:
    return str(uuid.uuid4())


class AgentRunner:
    def __init__(
        self, registry: AgentRegistry, message_consumer: MessageConsumer
    ) -> None:
        self.registry = registry
        self.message_consumer = message_consumer
        self.task2run_id = {}

    async def run(
        self, agent_name: str, agent_input: str, task_id: str | None = None
    ) -> BaseModel:
        rec = self.registry.get(agent_name)
        if not rec:
            raise ValueError(f"Agent '{agent_name}' not found")

        run_id = _new_run_id()
        if task_id:
            self.task2run_id[task_id] = run_id

        # 通过 contextvars 注入执行上下文，使插件在不改变签名的情况下自动上报事件
        ctx = ExecutionContext(
            run_id=run_id,
            agent_name=agent_name,
            seq=iter(range(1, 10**9)),
            vc=self.message_consumer,
        )
        await set_execution_context(ctx)
        try:
            # 实例化 Agent 并调用其 run 方法
            agent_instance: ITanWeAIAgent = rec.agent_cls()
            agent_output = await agent_instance.run(agent_input=agent_input)
        finally:
            await clear_execution_context()
            if task_id:
                del self.task2run_id[task_id]

        return agent_output
