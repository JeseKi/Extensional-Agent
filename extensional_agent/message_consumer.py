"""
消息消费者抽象基类和具体实现

该模块定义了原子化 Agent 系统中消息处理的核心接口，支持：
- 事件发布和订阅
- 实时消息推送
- 历史消息查询
- 可插拔的存储后端
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, List, Awaitable, Union
import asyncio


# 导入 AgentEvent 类型
from .schemas import AgentEvent

# 异步回调函数类型 - 接收 AgentEvent 对象
AsyncCallback = Callable[[AgentEvent], Union[None, Awaitable[None]]]


class MessageConsumer(ABC):
    """
    消息消费者抽象基类

    定义了原子化 Agent 系统中消息处理的核心接口，支持：
    - 事件的异步发布和订阅
    - 按 run_id 级别的消息隔离
    - 实时回调和异步历史查询
    - 更好的并发性能和资源利用

    具体实现可以选择不同的存储策略：
    - 内存实现：适合轻量级场景，快速异步操作
    - 持久化实现：适合生产环境，支持异步 I/O
    - 分布式实现：支持异步网络通信
    - 混合实现：兼顾性能和可靠性
    """

    @abstractmethod
    async def publish(self, event: AgentEvent) -> None:
        """
        异步发布事件到消息队列

        Args:
            event: AgentEvent 对象，包含完整的执行记录和元数据
        """
        pass

    @abstractmethod
    async def subscribe(self, run_id: str, callback: AsyncCallback) -> int:
        """
        异步订阅指定 run_id 的实时事件

        Args:
            run_id: 运行ID
            callback: 异步事件回调函数，支持同步和异步回调

        Returns:
            订阅令牌，用于后续取消订阅
        """
        pass

    @abstractmethod
    async def unsubscribe(self, run_id: str, token: int) -> None:
        """
        异步取消订阅

        Args:
            run_id: 运行ID
            token: 订阅令牌
        """
        pass

    @abstractmethod
    async def get_events(
        self, run_id: str, after_seq: int = 0, callback: AsyncCallback | None = None
    ) -> List[AgentEvent]:
        """
        异步获取历史事件（用于首帧回放等场景）

        Args:
            run_id: 运行ID
            after_seq: 起始序号，返回大于该序号的事件
            callback: 异步事件回调函数，支持同步和异步回调

        Returns:
            AgentEvent 对象列表
        """
        pass

    async def cleanup(self, run_id: str) -> None:
        """
        异步清理指定 run_id 的资源（可选实现）

        Args:
            run_id: 运行ID
        """
        pass

    async def _safe_callback(
        self, callback: AsyncCallback, event: AgentEvent
    ) -> None:
        """
        安全执行回调函数，支持同步和异步回调
        """
        try:
            result = callback(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            # 忽略回调异常，避免影响主流程
            pass
