# ExtensionalAgent SDK

基于 Agent 的可扩展测试框架 SDK，提供完整的 Agent 生命周期管理和流式事件处理能力。

## 特性

- **Agent 抽象基类**: 标准化的 Agent 接口定义
- **流式事件系统**: 将 OpenAI 标准格式流式响应包装为 ExecutionRecord 进行传输
- **类型安全**: 订阅者接收完整的 AgentEvent 对象，支持直接属性访问
- **插件化架构**: 支持动态发现和注册 Agent 插件
- **消息消费者**: 灵活的消息存储和订阅机制
- **完整的数据模型**: 基于 Pydantic 的类型安全数据定义

## 安装

您可以通过我的 github 来进行安装。
```
pip install git+https://github.com/JeseKi/Extensional-Agent.git
```

clone 到本地后，在源码根目录下进行安装：

```bash
pip install .
```

## 核心概念

### 数据流设计

整个 SDK 的数据流设计遵循以下模式：

1. **输入**: 一个字符串输入
2. **处理**: Agent 调用 LLM（如 OpenAI）获得流式响应
3. **包装**: 将 OpenAI ChatCompletion 的流式数据包装到 `ExecutionRecord` 中
4. **传输**: 调用 `emit_event`，该函数内部会创建包含 `ExecutionRecord` 的 `AgentEvent` 对象
5. **消费**: `MessageConsumer` 接收 `AgentEvent` 并将其分发给订阅者
6. **订阅**: 外部系统接收完整的 `AgentEvent` 对象，可直接访问属性
7. **输出**: 返回最终的字符串结果

```
Input → Agent → OpenAI API → ExecutionRecord → emit_event(creates AgentEvent) → MessageConsumer → 订阅者
                ↓
              Result
```

### AgentEvent 结构

订阅者接收到的是完整的 `AgentEvent` 对象：

```python
event = AgentEvent(
    v=1,                          # 事件版本号
    run_id="uuid-string",         # 运行ID
    seq=1,                        # 序列号
    timestamp="2024-01-01T12:00:00Z",  # ISO时间戳
    agent="agent_name",           # Agent名称
    execution_record=ExecutionRecord(
        id=stream_id,             # 流ID（同一流使用相同UUID）
        index=chunk_index,        # 当前块在流中的位置
        role=Role.ASSISTANT,      # 角色
        reasoning_content="推理过程", # Agent的思考过程
        content=delta.content,    # OpenAI返回的实际内容
        tool_call=tool_call_info, # 工具调用信息（如果有）
        is_stop=finish_reason_exists # 是否为流的结束块
    )
)
```

## 快速开始

### 1. 创建一个流式 Agent

正确的实现方式是在同一次流式响应中共享同一个 `stream_id`，并通过 `ExecutionRecord` 的内容来区分文本和工具调用。

```python
from extensional_agent import ITanWeAIAgent, emit_event
from extensional_agent.schemas import ExecutionRecord, Role, ToolCall
from typing import List
from uuid import uuid4
import openai

class StreamingSecurityAgent(ITanWeAIAgent):
    AGENT_NAME = "weather_assistant"
    
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI()
    
    async def run(self, agent_input: Any) -> Any:
        
        # 构建提示词和工具定义
        messages = [
            {"role": "system", "content": "你是一个专业的助手"},
            {"role": "user", "content": "北京是一个怎么样的地方？"}
        ]
        tools = [{
            "type": "function",
            "function": {
                "name": "weather",
                "description": "获取指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "目标城市"}},
                    "required": ["city"]
                }
            }
        }]
        
        # 单次流式响应中的所有事件共享同一个 stream_id
        stream_id = str(uuid4())
        chunk_index = 0
        
        async for chunk in await self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            stream=True
        ):
            choice = chunk.choices[0]
            delta = choice.delta
            is_stop = choice.finish_reason is not None

            # 1. 处理流式文本内容
            if delta.content:
                record = ExecutionRecord(
                    id=stream_id,
                    index=chunk_index,
                    role=Role.ASSISTANT,
                    reasoning_content=None, # 若为推理模型应当放置其推理内容
                    content=delta.content,
                    is_stop=is_stop
                )
                await emit_event(execution_record=record)
                chunk_index += 1

            # 2. 处理流式工具调用
            if delta.tool_calls:
                for tool_call in delta.tool_calls:
                    # 角色是 ASSISTANT，因为它在“请求”调用工具
                    record = ExecutionRecord(
                        id=stream_id,
                        index=chunk_index,
                        role=Role.ASSISTANT,
                        reasoning_content=None, # 若为推理模型则应当放置其推理内容
                        tool_call=ToolCall(name=tool_call.function.name, args=tool_call.function.arguments),
                        is_stop=is_stop
                    )
                    await emit_event(execution_record=record)
                    chunk_index += 1
            
            # 3. 在流结束时，发送一个最终事件以确保消费者能正确关闭流
            if is_stop:
                final_record = ExecutionRecord(id=stream_id, index=chunk_index, role=Role.ASSISTANT, is_stop=True)
                await emit_event(execution_record=final_record)

        # 在这里可以根据收集到的工具调用信息，执行工具，并将结果返回给LLM继续下一轮对话
        # ...
        
        return "最终的答案"
```

### 2. 运行流式 Agent

运行 Agent 的方式保持不变，但订阅者 `stream_handler` 会接收到更丰富的事件类型（文本或工具调用）。

```python
import asyncio
from extensional_agent import AgentRunner, AgentRegistry, AgentEvent
from extensional_agent.registry import AgentRecord
from extensional_agent.examples.virtual_consumer import VirtualConsumer

async def main():
    # (注册表和 Agent 的创建同上)
    registry = AgentRegistry()
    registry.register(AgentRecord(
        name="weather_assistant",
        module_name="my_agent",
        agent_cls=StreamingSecurityAgent
    ))
    consumer = VirtualConsumer()
    
    # 订阅者现在需要能区分文本和工具调用
    async def stream_handler(event: AgentEvent):
        record = event.execution_record
        
        print(f"[流 {str(record.id)[:8]}#{record.index}] ", end="")
        
        if record.content:
            print(f"内容: {record.content}")
        
        if record.tool_call:
            print(f"工具调用: {record.tool_call.name} 参数: {record.tool_call.args}")
            
        if record.is_stop:
            print(f"--- 流 {str(record.id)[:8]} 结束 ---")
    
    token = await consumer.subscribe("example_run", stream_handler)
    
    runner = AgentRunner(registry, consumer)
    agent_input = "北京的天气怎么样？"
    
    await runner.run("weather_assistant", agent_input)
    
    await consumer.unsubscribe("example_run", token)

if __name__ == "__main__":
    asyncio.run(main())
```

### 3. 流式事件重组

`StreamReassembler` 需要更新，使其能够在一个流中同时处理文本和工具调用。

```python
from extensional_agent.schemas import AgentEvent, ExecutionRecord, ToolCall

class StreamReassembler:
    def __init__(self):
        # 每个流需要能存储文本、工具调用和推理过程
        self.streams = {}  # stream_id -> {"content": {}, "tool_calls": [], "reasoning": ""}
    
    async def handle_agent_event(self, event: AgentEvent):
        """处理 AgentEvent 对象，支持文本和工具调用"""
        record = event.execution_record
        stream_id = record.id
        
        # 初始化流存储
        if stream_id not in self.streams:
            self.streams[stream_id] = {"content": {}, "tool_calls": [], "reasoning": ""}
        
        # 存储文本内容
        if record.content:
            self.streams[stream_id]["content"][record.index] = record.content
        
        # 存储工具调用
        if record.tool_call:
            self.streams[stream_id]["tool_calls"].append(record.tool_call)
        
        # 更新推理过程 (通常取最新的)
        if record.reasoning_content:
            self.streams[stream_id]["reasoning"] = record.reasoning_content
        
        # 如果流结束，重组并输出完整结果
        if record.is_stop:
            stream_data = self.streams.pop(stream_id, None)
            if not stream_data:
                return

            # 重组文本
            sorted_chunks = sorted(stream_data.get("content", {}).items())
            full_content = ''.join([chunk[1] for chunk in sorted_chunks])
            
            tool_calls = stream_data.get("tool_calls", [])
            reasoning = stream_data.get("reasoning", "")
            
            print(f"--- Stream {str(stream_id)[:8]} Finalized ---")
            print(f"Agent: {event.agent}, Run ID: {event.run_id}")
            if reasoning:
                print(f"Reasoning: {reasoning}")
            if full_content:
                print(f"Full Content: {full_content}")
            if tool_calls:
                print(f"Tool Calls: {tool_calls}")
            print("--------------------------------------")

# 使用示例
async def monitor_agent_execution():
    consumer = VirtualConsumer()
    reassembler = StreamReassembler()
    
    token = await consumer.subscribe("run_id_123", reassembler.handle_agent_event)
    
    # (此处应有 Agent 运行的逻辑)
    
    await consumer.unsubscribe("run_id_123", token)
```

### 4. 消息消费者选择

#### VirtualConsumer（开发测试）

```python
from extensional_agent.examples.virtual_consumer import VirtualConsumer

# 轻量级内存实现，直接存储 AgentEvent 对象
consumer = VirtualConsumer(max_per_run=5000)
```

#### PersistentConsumer（生产环境）

```python
from extensional_agent.examples.persistent_consumer import PersistentConsumer  

# 持久化实现，内存中存储 AgentEvent 对象，磁盘存储字典格式
consumer = PersistentConsumer(
    storage_path="./agent_events", 
    max_memory_events=1000,
    batch_size=100,           # 批量写入流式数据
    flush_interval=10,        # 定期刷新缓冲区
    retention_days=30
)
```

## 公开接口

### 核心类

- **ITanWeAIAgent**: Agent 抽象基类
- **AgentRunner**: Agent 运行器，管理执行上下文
- **MessageConsumer**: 消息消费者抽象基类
- **AgentRegistry**: Agent 注册表

### 工具函数

- **emit_event()**: 发送 ExecutionRecord，自动封装为 AgentEvent
- **current_run_id()**: 获取当前运行ID
- **current_agent_name()**: 获取当前Agent名称
- **discover_plugins()**: 自动发现插件

### 数据模型

#### 事件相关

- **AgentEvent**: 完整的 Agent 事件对象（订阅者接收的类型）
- **ExecutionRecord**: 执行记录，包装 OpenAI 流式响应
- **Role**: 角色枚举（ASSISTANT, TOOL）
- **ToolCall**: 工具调用信息

## 设计模式

### 类型安全的事件传递

订阅者接收完整的 `AgentEvent` 对象，支持直接属性访问：

```python
# 订阅回调函数
async def event_handler(event: AgentEvent):
    # 类型安全的属性访问
    print(f"Agent: {event.agent}")
    print(f"序列号: {event.seq}")
    print(f"时间戳: {event.timestamp}")
    
    # 访问执行记录
    record = event.execution_record
    print(f"角色: {record.role}")
    print(f"内容: {record.content}")
    print(f"推理: {record.reasoning_content}")
```

### 流式数据包装模式

将标准的 LLM API 响应包装到统一的 `ExecutionRecord` 结构中，再封装到 `AgentEvent` 中：

```python
# OpenAI 原始响应
chunk = {
    "choices": [{"delta": {"content": "这是一个"}}],
    "finish_reason": None
}

# 包装为 ExecutionRecord
record = ExecutionRecord(
    id=stream_id,
    index=chunk_index,
    role=Role.ASSISTANT, 
    reasoning_content="Agent 推理过程",
    content=chunk["choices"][0]["delta"]["content"],
    is_stop=chunk["finish_reason"] is not None
)

# emit_event 自动封装为 AgentEvent
await emit_event(execution_record=record)
```

### 事件驱动架构

通过 `emit_event` 发送流式事件，支持多个订阅者实时接收 `AgentEvent` 对象：

```python
# Agent 内部
await emit_event(execution_record=record)

# 外部系统
async def handler(event: AgentEvent):
    # 直接访问属性
    content = event.execution_record.content
    
await consumer.subscribe(run_id, handler)
```

### 插件化扩展

```python
# 自动发现插件
registry = await discover_plugins("./plugins")
