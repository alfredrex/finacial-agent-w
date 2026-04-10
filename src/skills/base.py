from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class SkillCategory(str, Enum):
    STOCK = "stock"
    NEWS = "news"
    COMPANY = "company"
    KNOWLEDGE = "knowledge"
    ANALYSIS = "analysis"
    COMPOSITE = "composite"


@dataclass
class SkillResult:
    success: bool
    data: Dict[str, Any]
    message: str
    tools_used: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BaseSkill(ABC):
    name: str
    description: str
    category: SkillCategory
    parameters: Dict[str, str]
    required_tools: List[str] = []
    
    @abstractmethod
    def execute(self, **kwargs) -> SkillResult:
        pass
    
    @abstractmethod
    def validate_params(self, **kwargs) -> bool:
        pass
    
    def get_description(self) -> str:
        params_desc = ", ".join([f"{k}: {v}" for k, v in self.parameters.items()])
        return f"{self.name}({params_desc}): {self.description}"
    
    def _call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        from src.tools.registry import tool_registry
        
        tool = tool_registry.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found"}
        
        try:
            return tool.func(**kwargs)
        except Exception as e:
            return {"error": str(e)}
