from typing import Any, Dict, Optional
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

# Agent 流式传回数据相关的数据模型
class Role(str, Enum):
    ASSISTANT = "assistant"
    TOOL = "tool"
    # 至于为什么没有 user, system 等角色，因为外部系统不需要关心这些东西，一个 Agent 应当根据自己收到的输入的上下文来完成整个任务，因此 Agent 需要传出的内容中也只会有 ASSISTANT 和 TOOL 这两种角色。


class ToolCall(BaseModel):
    name: str = Field(..., description="工具名称")
    args: Dict[str, Any] = Field(
        ..., description="工具调用的参数，通常是一个字典，包含工具调用的相关信息"
    )


class ExecutionRecord(BaseModel):
    id: UUID = Field(
        ...,
        description='用于标记在流式消息中是否为同一条消息，方便在保存到数据库中的时候进行对多个 "content" 或 "reasoning_content" 进行拼接',
        examples=[
            "50404950-f8cf-4dc6-9d09-04d293039bc0",
            "f377beb9-d8da-4b39-b3d5-be30562608de",
        ],
    )
    index: int = Field(..., description="当前块在整个流式响应中的位置")
    role: Role = Field(..., description="角色")
    reasoning_content: Optional[str] = Field(
        default=None,
        description="推理内容，通常是一个字符串，描述了 Agent 在执行任务时的思考过程",
    )
    content: Optional[str | Dict[str, Any]] = Field(
        default=None,
        description="内容，可以是字符串、字典等，具体取决于角色的类型，例如 ASSISTANT 可能是字符串，TOOL 可能是字典",
    )
    tool_call: Optional[ToolCall] = Field(
        default=None,
        description="工具调用参数，通常是一个字典，包含工具调用的相关信息，例如工具名称、参数等",
    )
    is_stop: bool = Field(
        ...,
        description="当前块是否为结束块，一般来说在 Agent 响应的过程中会设置为 False，直到响应结束才为 True，Tool 角色一般都为 True",
    )
    

# Agent SDK 相关的 BaseModel
class AgentEvent(BaseModel):
    """Agent 执行事件模型"""

    v: int = Field(default=1, description="事件版本号")
    run_id: str = Field(..., description="运行ID")
    seq: int = Field(..., description="序列号")
    timestamp: str = Field(..., description="ISO格式时间戳")
    agent: str = Field(..., description="Agent名称")
    execution_record: ExecutionRecord = Field(..., description="执行记录")


class AgentExecutionContext(BaseModel):
    """Agent 执行上下文模型"""

    run_id: str = Field(..., description="运行ID")
    agent_name: str = Field(..., description="Agent名称")
    first_seq: Optional[int] = Field(default=None, description="第一个序列号")
    last_seq: Optional[int] = Field(default=None, description="最后一个序列号")

    model_config = {"arbitrary_types_allowed": True}  # 允许 Iterator 等非标准类型


class EmitEventWarning(BaseModel):
    """emit_event 警告响应"""

    warning: str = Field(..., description="警告信息")