"""
ExtensionalAgent SDK - 基于 Agent 的可扩展渗透测试框架

该 SDK 提供了完整的 Agent 生命周期管理和事件流处理能力，
包括 Agent 注册、运行、消息传递和状态管理等核心功能。

核心功能：
- Agent 抽象基类和生命周期管理
- 事件驱动的消息传递系统
- 插件式的消息消费者实现
- 完整的数据模型和类型定义

快速开始：
    from extensional_agent import ITanWeAIAgent, emit_event, AgentRunner
    from extensional_agent.registry import discover_plugins
    from extensional_agent.examples.virtual_consumer import VirtualConsumer
    
    # 创建 AgentRunner 实例
    registry = await discover_plugins("./plugins")
    consumer = VirtualConsumer()
    runner = AgentRunner(registry, consumer)
    
    # 运行 Agent
    result = await runner.run("agent_name", agent_input)
"""

# 核心组件导入
from .agent_base import ITanWeAIAgent
from .agent_sdk import emit_event, current_run_id, current_agent_name
from .runner import AgentRunner
from .registry import AgentRegistry, AgentRecord, discover_plugins
from .message_consumer import MessageConsumer

# 数据模型导入
from .schemas import (
    # 执行记录相关
    ExecutionRecord, Role, ToolCall,
    # SDK 相关
    AgentEvent, AgentExecutionContext, EmitEventWarning,
)

# 版本信息
__version__ = "0.1.0"
__author__ = "Jese__Ki"
__email__ = "2094901072@example.com"

# 公开接口
__all__ = [
    # 核心类和函数
    "ITanWeAIAgent",
    "AgentRunner",
    "MessageConsumer",
    "emit_event",
    "current_run_id", 
    "current_agent_name",
    
    # 注册表相关
    "AgentRegistry",
    "AgentRecord", 
    "discover_plugins",
    
    # 数据模型 - Agent 相关
    # 数据模型 - 执行相关
    "ExecutionRecord",
    "Role",
    "ToolCall",
    
    # 数据模型 - SDK 相关
    "AgentEvent",
    "AgentExecutionContext",
    "EmitEventWarning",
    
    # 版本信息
    "__version__",
    "__author__",
    "__email__",
]
