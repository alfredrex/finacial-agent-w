"""
用户长期记忆管理器
使用 mem0 存储用户自身的长期固定信息

只存储 4 类信息：
1. 用户展示偏好 (display_preference)
2. 用户风险属性 (risk_profile)
3. 用户关注标的/行业 (watchlist)
4. 用户交易约束 (trading_constraints)

不存储：
- 用户提问原文/问句
- Agent 执行结果
- 临时任务数据
- 行情、计算结果、分析内容
"""
import os
import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings


MEMORY_CATEGORIES = {
    "display_preference": {
        "description": "用户展示偏好",
        "keywords": ["展示", "显示", "偏好", "格式", "样式", "图表类型", "输出方式"],
        "examples": ["喜欢表格展示", "偏好简洁输出", "喜欢详细分析"]
    },
    "risk_profile": {
        "description": "用户风险属性",
        "keywords": ["风险", "保守", "激进", "稳健", "风险承受", "投资风格"],
        "examples": ["保守型投资者", "风险承受能力低", "偏好稳健投资"]
    },
    "watchlist": {
        "description": "用户关注标的/行业",
        "keywords": ["关注", "持仓", "自选", "股票池", "行业偏好", "板块"],
        "examples": ["持有茅台", "关注白酒板块", "自选股包括"]
    },
    "trading_constraints": {
        "description": "用户交易约束",
        "keywords": ["资金", "仓位", "止损", "止盈", "交易时间", "交易规则", "限制"],
        "examples": ["资金量10万", "最大仓位50%", "止损线5%"]
    }
}

EXCLUDED_PATTERNS = [
    r"股价.*多少",
    r".*行情.*",
    r".*分析.*",
    r".*走势.*",
    r"什么.*",
    r"怎么.*",
    r"如何.*",
    r"为什么.*",
    r"帮我.*",
    r"请.*",
]


class UserMemoryManager:
    """
    用户长期记忆管理器
    基于 mem0 实现，只存储用户自身的长期固定信息
    """
    
    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self._memory_client = None
        self._use_mem0 = False
        self._local_memory: Dict[str, List[Dict]] = {
            "display_preference": [],
            "risk_profile": [],
            "watchlist": [],
            "trading_constraints": []
        }
        self._memory_file = os.path.join(settings.DATA_CACHE_DIR, "user_memory", f"{user_id}.json")
        self._init_memory()
    
    def _init_memory(self):
        self._load_local_memory()
        try:
            from mem0 import Memory
            import tempfile
            local_path = os.path.join(settings.DATA_CACHE_DIR, "mem0_storage")
            os.makedirs(local_path, exist_ok=True)
            self._memory_client = Memory()
            self._use_mem0 = True
        except Exception as e:
            print(f"[INFO] mem0 初始化失败，使用本地存储: {e}")
            self._use_mem0 = False
    
    def _load_local_memory(self):
        if os.path.exists(self._memory_file):
            try:
                with open(self._memory_file, "r", encoding="utf-8") as f:
                    self._local_memory = json.load(f)
            except Exception:
                pass
    
    def _save_local_memory(self):
        os.makedirs(os.path.dirname(self._memory_file), exist_ok=True)
        with open(self._memory_file, "w", encoding="utf-8") as f:
            json.dump(self._local_memory, f, ensure_ascii=False, indent=2)
    
    def _classify_content(self, content: str) -> Optional[str]:
        """
        分类内容，判断属于哪一类记忆
        返回类别名称或 None（不属于任何类别）
        """
        content_lower = content.lower()
        
        for pattern in EXCLUDED_PATTERNS:
            if re.search(pattern, content_lower):
                return None
        
        for category, info in MEMORY_CATEGORIES.items():
            for keyword in info["keywords"]:
                if keyword in content:
                    return category
        
        return None
    
    def _extract_memory_info(self, content: str, category: str) -> Optional[str]:
        """
        从内容中提取记忆信息
        使用 LLM 提取结构化信息
        """
        from src.llm.llm import get_llm
        
        llm = get_llm()
        
        category_info = MEMORY_CATEGORIES[category]
        
        prompt = f"""分析以下用户输入，提取与"{category_info['description']}"相关的信息。

用户输入: {content}

类别说明: {category_info['description']}
关键词: {', '.join(category_info['keywords'])}
示例: {', '.join(category_info['examples'])}

请提取用户表达的偏好/属性/约束信息，以简洁的陈述句形式输出。
如果输入与该类别无关，输出: 无关

输出格式: 直接输出提取的信息，不要有其他内容。"""

        try:
            response = llm.invoke([
                SystemMessage(content="你是一个信息提取专家，擅长从用户输入中提取结构化信息。"),
                HumanMessage(content=prompt)
            ])
            
            result = response.content.strip()
            
            if result == "无关" or len(result) < 3:
                return None
            
            return result
        except Exception:
            return None
    
    async def add_memory(self, content: str, llm=None) -> Dict[str, Any]:
        """
        添加记忆
        只存储 4 类用户自身的长期固定信息
        
        Args:
            content: 用户输入内容
            llm: LLM 实例（可选）
        
        Returns:
            添加结果
        """
        category = self._classify_content(content)
        
        if category is None:
            return {
                "success": False,
                "reason": "内容不属于可存储的 4 类信息"
            }
        
        memory_info = self._extract_memory_info(content, category)
        
        if memory_info is None:
            return {
                "success": False,
                "reason": "无法提取有效记忆信息"
            }
        
        memory_entry = {
            "content": memory_info,
            "category": category,
            "timestamp": datetime.now().isoformat(),
            "raw_input": content[:100]
        }
        
        if self._use_mem0:
            try:
                self._memory_client.add(
                    messages=[{"role": "user", "content": memory_info}],
                    user_id=self.user_id,
                    metadata={"category": category}
                )
            except Exception as e:
                self._local_memory[category].append(memory_entry)
                self._save_local_memory()
        else:
            self._local_memory[category].append(memory_entry)
            self._save_local_memory()
        
        return {
            "success": True,
            "category": category,
            "memory": memory_info
        }
    
    async def search_memory(self, query: str, category: Optional[str] = None) -> List[Dict]:
        """
        搜索记忆
        
        Args:
            query: 查询内容
            category: 限定类别（可选）
        
        Returns:
            匹配的记忆列表
        """
        results = []
        
        if self._use_mem0:
            try:
                search_results = self._memory_client.search(
                    query=query,
                    user_id=self.user_id,
                    limit=5
                )
                
                for item in search_results.get("results", []):
                    if category is None or item.get("metadata", {}).get("category") == category:
                        results.append({
                            "content": item.get("memory", ""),
                            "category": item.get("metadata", {}).get("category", ""),
                            "score": item.get("score", 0)
                        })
            except Exception:
                pass
        
        if not results:
            search_lower = query.lower()
            for cat, memories in self._local_memory.items():
                if category is None or cat == category:
                    for memory in memories:
                        if search_lower in memory["content"].lower():
                            results.append({
                                "content": memory["content"],
                                "category": cat,
                                "timestamp": memory.get("timestamp", "")
                            })
        
        return results
    
    def get_all_memory(self, category: Optional[str] = None) -> Dict[str, List[Dict]]:
        """
        获取所有记忆
        
        Args:
            category: 限定类别（可选）
        
        Returns:
            记忆字典
        """
        if category:
            return {category: self._local_memory.get(category, [])}
        return self._local_memory
    
    def get_memory_summary(self) -> str:
        """
        获取记忆摘要
        用于注入到 Agent 提示词中
        """
        summary_parts = []
        
        for category, info in MEMORY_CATEGORIES.items():
            memories = self._local_memory.get(category, [])
            if memories:
                items = [m["content"] for m in memories[-3:]]
                summary_parts.append(f"【{info['description']}】: {', '.join(items)}")
        
        if summary_parts:
            return "\n".join(summary_parts)
        return "暂无用户偏好信息"
    
    def clear_memory(self, category: Optional[str] = None):
        """
        清除记忆
        
        Args:
            category: 限定类别（可选），不传则清除所有
        """
        if category:
            self._local_memory[category] = []
        else:
            for cat in self._local_memory:
                self._local_memory[cat] = []
        
        self._save_local_memory()


user_memory_manager = UserMemoryManager()
