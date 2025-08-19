"""
带思考的Agent实现

本文件实现了一个支持推理思考的Agent，核心功能是从Qwen3-32B模型的响应中
解析reasoning_content字段并通过extensional_agent框架进行传输。

公开接口:
- ThinkingDemoAgent: 带思考的演示Agent类

内部方法:
- run(): 主要的Agent执行方法
- _execute_tool_call(): 工具调用执行方法

工具函数:
- get_weather(): 模拟天气查询
- get_temperature(): 模拟温度查询

数据模型:
Agent处理的核心是将LLM的reasoning_content字段提取并封装到ExecutionRecord中，
通过emit_event发送给订阅者。

实现重点:
这是一个纯粹的Agent实现，只负责LLM输出解析和reasoning_content提取。
"""

import asyncio
import os
import json
import random
from typing import Dict, Any
from uuid import UUID, uuid4

import openai
from dotenv import load_dotenv

from extensional_agent import ITanWeAIAgent, emit_event, ExecutionRecord, Role, ToolCall

# 加载 .env 文件中的环境变量
load_dotenv()


# 演示工具函数
def get_weather(city: str) -> str:
    """获取指定城市的天气情况（模拟）"""
    weather_conditions = ["晴天", "多云", "小雨", "中雨", "阴天", "雷阵雨"]
    return random.choice(weather_conditions)


def get_temperature(city: str) -> int:
    """获取指定城市的温度（模拟）"""
    return random.randint(-10, 40)  # 模拟温度范围 -10°C 到 40°C


class ThinkingDemoAgent(ITanWeAIAgent):
    """
    带思考的演示Agent
    
    该Agent用于演示：
    1. 如何解析和展示reasoning_content字段
    2. 工具调用的完整流程（天气、温度查询）
    3. 流式事件处理和思考内容传输
    4. 实时推理过程监控
    """
    AGENT_NAME = "thinking_demo_agent"

    def __init__(self):
        """初始化Agent，配置OpenAI客户端"""
        # 从环境变量获取 OpenAI API 配置
        base_url = os.getenv("OPENAI_BASE_URL")
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not base_url or not api_key:
            raise ValueError("请确保设置了OPENAI_BASE_URL和OPENAI_API_KEY环境变量")
        
        # 初始化 OpenAI 客户端
        self.openai_client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key
        )

    async def run(self, agent_input: str) -> str:
        """
        运行带思考的演示Agent
        
        Args:
            agent_input: Agent 的输入
            
        Returns:
            最终的输出
            
        数据流:
        1. 构建包含工具定义的提示词
        2. 调用Qwen3-32B模型获取流式响应
        3. 解析reasoning_content字段获取思考过程
        4. 处理工具调用并返回结果
        5. 通过emit_event发送事件给订阅者
        """
        print("🔍 [调试] ThinkingDemoAgent.run() 被调用")
        print(f"🔍 [调试] agent_input: {agent_input}")
        print(f"🔍 [调试] OpenAI client 配置 - base_url: {self.openai_client.base_url}")
        print(f"🔍 [调试] OpenAI client 配置 - api_key: {self.openai_client.api_key[:10]}...")
        # 构建用于演示工具调用和思考的提示词
        messages = [
            {
                "role": "system", 
                "content": """你是一个智能助手，可以帮助用户查询天气和温度信息。

在回答问题时，请详细展示你的思考过程，包括：
1. 对用户问题的理解
2. 需要调用哪些工具来获取信息
3. 如何处理和分析获取到的数据
4. 最终如何组织答案

请先思考，然后根据需要调用相应的工具。"""
            },
            {
                "role": "user", 
                "content": f"请帮我查询一下 {agent_input} 这个地方的天气情况和温度。请详细说明你的思考过程。"
            }
        ]
        
        # 定义可用的工具
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取指定城市的天气情况",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "城市名称"
                            }
                        },
                        "required": ["city"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_temperature",
                    "description": "获取指定城市的温度",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "城市名称"
                            }
                        },
                        "required": ["city"]
                    }
                }
            }
        ]
        
        # 为这次流式响应生成唯一的 stream_id
        stream_id = uuid4()
        chunk_index = 0
        
        # 用于积累流式工具调用的数据结构
        tool_calls_buffer = {}  # tool_call_index -> {id, name, arguments}

        try:
            print("🔍 [调试] 开始调用 OpenAI API...")
            print("🔍 [调试] 使用模型: Qwen3-32B")
            print(f"🔍 [调试] 消息内容: {messages[-1]['content']}")
            
            # 调用 Qwen3-32B 模型获取流式响应
            stream = await self.openai_client.chat.completions.create(
                model="Qwen3-32B",  # 使用指定的Qwen3-32B模型
                messages=messages, # type: ignore
                tools=tools,  # 提供工具定义 # type: ignore
                stream=True,
                temperature=0.7,  # 适度的创造性，保持推理的多样性
                max_tokens=2000   # 确保有足够空间进行详细推理
            )
            
            print("🔍 [调试] OpenAI API 调用成功，开始处理流式响应...")
            chunk_count = 0
            
            async for chunk in stream:
                chunk_count += 1
                print(f"🔍 [调试] 收到第 {chunk_count} 个 chunk")
                
                choice = chunk.choices[0]
                delta = choice.delta
                is_stop = choice.finish_reason is not None
                
                print(f"🔍 [调试] chunk 详情: is_stop={is_stop}, finish_reason={choice.finish_reason}")
                if hasattr(delta, 'content') and delta.content:
                    print(f"🔍 [调试] delta.content: {delta.content}")
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    print(f"🔍 [调试] delta.reasoning_content: {delta.reasoning_content}")
                if hasattr(delta, 'tool_calls') and delta.tool_calls:
                    print(f"🔍 [调试] delta.tool_calls: {delta.tool_calls}")

                # 处理推理思考内容 - 从reasoning_content字段提取
                reasoning_content = None
                if hasattr(choice, 'message') and hasattr(choice.message, 'reasoning_content'):
                    reasoning_content = choice.message.reasoning_content
                elif hasattr(delta, 'reasoning_content'):
                    reasoning_content = delta.reasoning_content
                
                # 如果有思考内容，优先发送思考过程
                if reasoning_content:
                    thinking_record = ExecutionRecord(
                        id=stream_id,
                        index=chunk_index,
                        role=Role.ASSISTANT,
                        reasoning_content=reasoning_content,  # 设置思考内容
                        content=None,  # 思考阶段不设置常规内容
                        tool_call=None,
                        is_stop=False  # 思考阶段不是结束
                    )
                    await emit_event(execution_record=thinking_record)
                    chunk_index += 1

                # 处理流式文本内容 - 最终答案
                if delta.content:
                    content_record = ExecutionRecord(
                        id=stream_id,
                        index=chunk_index,
                        role=Role.ASSISTANT,
                        reasoning_content=None,  # 内容阶段不重复思考内容
                        content=delta.content,
                        tool_call=None,
                        is_stop=is_stop
                    )
                    await emit_event(execution_record=content_record)
                    chunk_index += 1

                # 处理工具调用 - 流式积累模式
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        # 使用 index 作为工具调用的标识，因为 id 在后续 chunk 中可能为 None
                        tool_call_index = tool_call.index
                        tool_call_id = tool_call.id
                        
                        print(f"🔍 [调试] 处理工具调用 index={tool_call_index}, id={tool_call_id}: name={tool_call.function.name}, args='{tool_call.function.arguments}'")
                        
                        # 初始化或更新工具调用缓冲区
                        if tool_call_index not in tool_calls_buffer:
                            tool_calls_buffer[tool_call_index] = {
                                'id': tool_call_id,  # 保存第一次出现时的 ID
                                'name': '',
                                'arguments': ''
                            }
                        
                        # 积累工具名称（通常在第一个chunk中完整传输）
                        if tool_call.function.name:
                            tool_calls_buffer[tool_call_index]['name'] = tool_call.function.name
                        
                        # 积累工具参数（可能分多个chunk传输）
                        if tool_call.function.arguments:
                            tool_calls_buffer[tool_call_index]['arguments'] += tool_call.function.arguments
                        
                        print(f"🔍 [调试] 当前积累状态 index={tool_call_index}: {tool_calls_buffer[tool_call_index]}")
                        
                        # 尝试检查是否为完整的JSON（简单检查：开始和结束括号匹配）
                        current_args = tool_calls_buffer[tool_call_index]['arguments']
                        if current_args and current_args.strip().startswith('{') and current_args.strip().endswith('}'):
                            # 尝试解析完整的工具调用
                            try:
                                args_dict = json.loads(current_args)
                                tool_name = tool_calls_buffer[tool_call_index]['name']
                                
                                if tool_name:  # 确保工具名称也已完整接收
                                    print(f"🔍 [调试] 工具调用完整，准备执行: {tool_name}({args_dict})")
                                    
                                    # 发送工具调用事件
                                    tool_record = ExecutionRecord(
                                        id=stream_id,
                                        index=chunk_index,
                                        role=Role.ASSISTANT,
                                        tool_call=ToolCall(
                                            name=tool_name,
                                            args=args_dict
                                        ),
                                        is_stop=False
                                    )
                                    await emit_event(execution_record=tool_record)
                                    chunk_index += 1
                                    
                                    # 执行工具调用并发送结果
                                    await self._execute_tool_call(
                                        stream_id, chunk_index, tool_name, args_dict
                                    )
                                    chunk_index += 1
                                    
                                    # 清除已处理的工具调用
                                    del tool_calls_buffer[tool_call_index]
                                    
                            except json.JSONDecodeError:
                                print(f"🔍 [调试] JSON 尚未完整，继续积累: {current_args}")
                                # 继续积累，等待更多数据

                # 如果流结束，处理任何剩余的工具调用并发送最终事件
                if is_stop:
                    print(f"🔍 [调试] 流结束，总共处理了 {chunk_count} 个 chunk")
                    
                    # 处理任何剩余的未完成工具调用
                    for tool_call_index, tool_data in tool_calls_buffer.items():
                        print(f"🔍 [调试] 处理剩余工具调用 index={tool_call_index}: {tool_data}")
                        try:
                            if tool_data['arguments']:
                                args_dict = json.loads(tool_data['arguments'])
                            else:
                                args_dict = {}
                            
                            if tool_data['name']:
                                print(f"🔍 [调试] 执行剩余工具调用: {tool_data['name']}({args_dict})")
                                
                                # 发送工具调用事件
                                tool_record = ExecutionRecord(
                                    id=stream_id,
                                    index=chunk_index,
                                    role=Role.ASSISTANT,
                                    tool_call=ToolCall(
                                        name=tool_data['name'],
                                        args=args_dict
                                    ),
                                    is_stop=False
                                )
                                await emit_event(execution_record=tool_record)
                                chunk_index += 1
                                
                                # 执行工具调用
                                await self._execute_tool_call(
                                    stream_id, chunk_index, tool_data['name'], args_dict
                                )
                                chunk_index += 1
                                
                        except Exception as e:
                            print(f"🔍 [调试] 处理剩余工具调用时出错: {e}")
                    
                    # 清空缓冲区
                    tool_calls_buffer.clear()
                    
                    final_record = ExecutionRecord(
                        id=stream_id,
                        index=chunk_index,
                        role=Role.ASSISTANT,
                        reasoning_content=None,
                        content=None,
                        is_stop=True
                    )
                    await emit_event(execution_record=final_record)
                    break
            
            print(f"🔍 [调试] 流式处理完成，总共处理了 {chunk_count} 个 chunk")

        except Exception as e:
            print(f"🔍 [调试] OpenAI API 调用出错: {str(e)}")
            import traceback
            traceback.print_exc()
            # 发送错误事件
            error_record = ExecutionRecord(
                id=stream_id,
                index=chunk_index,
                role=Role.ASSISTANT,
                content=f"分析过程中出现错误: {str(e)}",
                is_stop=True
            )
            await emit_event(execution_record=error_record)

        # 返回最终的答案
        return "最终的答案"

    async def _execute_tool_call(self, stream_id: UUID, chunk_index: int, function_name: str, arguments: Dict[str, Any]):
        """
        执行工具调用并发送结果事件
        
        Args:
            stream_id: 流ID
            chunk_index: 当前块索引
            function_name: 函数名称
            arguments: 函数参数（字典）
        """
        try:
            # 使用传入的参数字典
            args = arguments
            
            # 根据函数名称执行相应的工具
            if function_name == "get_weather":
                result = get_weather(args.get("city", ""))
                result_text = f"天气查询结果：{args.get('city')} 的天气是 {result}"
            elif function_name == "get_temperature":
                result = get_temperature(args.get("city", ""))
                result_text = f"温度查询结果：{args.get('city')} 的温度是 {result}°C"
            else:
                result_text = f"未知工具：{function_name}"
            
            # 发送工具执行结果事件
            result_record = ExecutionRecord(
                id=stream_id,
                index=chunk_index,
                role=Role.TOOL,
                content=result_text,
                is_stop=False
            )
            await emit_event(execution_record=result_record)
            
        except Exception as e:
            # 发送错误事件
            error_record = ExecutionRecord(
                id=stream_id,
                index=chunk_index,
                role=Role.TOOL,
                content=f"工具执行错误: {str(e)}",
                is_stop=False
            )
            await emit_event(execution_record=error_record)
            
async def main():
    agent = ThinkingDemoAgent()
    await agent.run("北京")

if __name__ == "__main__":
    asyncio.run(main())