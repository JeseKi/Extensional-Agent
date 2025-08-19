"""
ExtensionalAgent SDK 示例模块

包含不同类型的消息消费者实现示例：
- VirtualConsumer: 轻量级内存实现
- PersistentConsumer: 持久化实现  
- 使用示例和演示代码
"""

from .virtual_consumer import VirtualConsumer
from .persistent_consumer import PersistentConsumer

__all__ = ["VirtualConsumer", "PersistentConsumer"]