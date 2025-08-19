from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional, List, Type
import pkgutil
import importlib
import os

from .agent_base import ITanWeAIAgent


@dataclass
class AgentRecord:
    name: str
    module_name: str
    agent_cls: Type[ITanWeAIAgent]


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, AgentRecord] = {}

    def register(self, rec: AgentRecord) -> None:
        self._agents[rec.name] = rec

    def get(self, name: str) -> Optional[AgentRecord]:
        return self._agents.get(name)

    def all(self) -> List[AgentRecord]:
        return list(self._agents.values())


async def discover_plugins(
    plugins_dir: str, package_prefix: str = "plugins"
) -> AgentRegistry:
    """
    发现位于 plugins_dir 下、定义了 Agent 子类的包。
    规则：模块内存在继承自 agent_base.Agent 的具体子类，且定义了 AGENT_NAME。
    """
    reg = AgentRegistry()
    if not os.path.isdir(plugins_dir):
        return reg

    for module_info in pkgutil.iter_modules([plugins_dir]):
        # 目录以下划线开头视为禁用，跳过注册
        if module_info.name.startswith("_"):
            continue
        module_name = f"{package_prefix}.{module_info.name}"
        mod = importlib.import_module(module_name)
        # 扫描模块内的 Agent 子类
        for attr in dir(mod):
            obj = getattr(mod, attr)
            try:
                is_agent_subclass = (
                    isinstance(obj, type)
                    and issubclass(obj, ITanWeAIAgent)
                    and obj is not ITanWeAIAgent
                )
            except Exception:
                is_agent_subclass = False
            if is_agent_subclass:
                agent_cls: Type[ITanWeAIAgent] = obj
                # 检查是否显式定义了自己的 AGENT_NAME (不是继承的默认值)
                if "AGENT_NAME" not in agent_cls.__dict__:
                    continue
                agent_name = agent_cls.AGENT_NAME
                if not agent_name or agent_name == "agent":  # 跳过默认值
                    continue
                rec = AgentRecord(
                    name=agent_name, module_name=module_name, agent_cls=agent_cls
                )
                reg.register(rec)
    return reg
