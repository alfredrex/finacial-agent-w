from typing import Dict, Any, Callable, List, Optional
from dataclasses import dataclass
from enum import Enum


class ToolCategory(str, Enum):
    DATA = "data"
    DATA_NEWS = "data_news"
    DATA_STOCK = "data_stock"
    DATA_COMPANY = "data_company"
    ANALYSIS = "analysis"
    KNOWLEDGE = "knowledge"
    FILE = "file"
    SYSTEM = "system"


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    func: Callable


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
    
    def register(self, name: str, description: str, category: ToolCategory,
                 parameters: Dict[str, Any], func: Callable) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            category=category,
            parameters=parameters,
            func=func
        )
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)
    
    def list_tools(self) -> List[str]:
        return list(self._tools.keys())
    
    def get_tools_by_category(self, category: ToolCategory) -> List[ToolDefinition]:
        result = []
        for tool in self._tools.values():
            if tool.category == category:
                result.append(tool)
            elif category == ToolCategory.DATA and tool.category in [
                ToolCategory.DATA, ToolCategory.DATA_NEWS, 
                ToolCategory.DATA_STOCK, ToolCategory.DATA_COMPANY
            ]:
                result.append(tool)
        return result
    
    def get_tools_description(self, categories: List[ToolCategory] = None) -> str:
        tools_desc = []
        for tool in self._tools.values():
            if categories and tool.category not in categories:
                continue
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool.parameters.items()])
            tools_desc.append(f"- {tool.name}({params_desc}): {tool.description}")
        return "\n".join(tools_desc)
    
    def get_tools_by_parent_category(self, parent: ToolCategory) -> List[ToolDefinition]:
        result = []
        for tool in self._tools.values():
            if tool.category == parent:
                result.append(tool)
            elif parent == ToolCategory.DATA and tool.category in [
                ToolCategory.DATA, ToolCategory.DATA_NEWS, 
                ToolCategory.DATA_STOCK, ToolCategory.DATA_COMPANY
            ]:
                result.append(tool)
        return result


tool_registry = ToolRegistry()
