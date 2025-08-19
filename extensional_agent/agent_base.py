from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar

class ITanWeAIAgent(ABC):
    """
    抽象 Agent 基类：
    - 约定：仅暴露一个 `run(input) -> output` 接口（异步）
    - 通过类属性 `AGENT_NAME` 指定唯一注册名
    插件需继承该类并实现 `run`。
    """

    AGENT_NAME: ClassVar[str] = "agent"

    @abstractmethod
    async def run(self, agent_input: Any) -> Any:
        raise NotImplementedError
