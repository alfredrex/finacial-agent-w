"""记忆Agent - 接入真实持久化记忆系统"""
from typing import Dict, Any, List, Optional

from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.memory import memory_system


class MemoryAgent(BaseAgent):
    """负责从持久化记忆系统中检索相关信息，为后续 Agent 提供上下文"""

    def __init__(self):
        super().__init__(
            name="MemoryAgent",
            description="负责从长期/短期记忆中检索历史相关信息",
            tool_categories=[],
        )
        self.max_iterations = 1

    def _log_message(self, state: AgentState, message: str):
        state.setdefault("messages", [])
        state["messages"].append({
            "agent": self.name,
            "message": message,
        })

    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        self._log_message(state, "开始从记忆系统检索...")

        query = state.get("rewritten_query", state.get("query", ""))
        limit = 5

        # 从统一记忆系统检索
        try:
            mem_results = await memory_system.retrieve(query_text=query, limit=limit)
            memory_context_str = memory_system.get_context_string(mem_results, top_k=limit)
        except Exception as e:
            self._log_message(state, f"记忆检索失败: {e}")
            memory_context_str = "暂无相关历史记忆"
            mem_results = {}

        # 存储检索结果到 state
        state["memory_context"] = [memory_context_str] if memory_context_str != "暂无相关历史记忆" else []

        memory_sources_list = []
        for source, items in mem_results.items():
            if items:
                memory_sources_list.append({"type": source, "count": len(items)})
        state["memory_sources"] = memory_sources_list

        # 补充用户记忆摘要
        try:
            state["user_memory_summary"] = memory_system.user.get_memory_summary()
        except Exception:
            pass

        if state["memory_context"]:
            state["thought"] = f"从 {len(memory_sources_list)} 个记忆源检索到 {len(state['memory_context'])} 条相关内容"
            self._log_message(state, state["thought"])
        else:
            state["thought"] = "未找到相关历史记忆"
            state["memory_context"] = []
            self._log_message(state, state["thought"])

        state["memory_retrieval_done"] = True
        state["is_finished"] = True
        state["iteration_logs"].append({
            "iteration": 1,
            "thought": state.get("thought", ""),
            "action": "memory_retrieval",
            "observation": f"检索结果: {len(state['memory_context'])} 条",
        })

        return state


memory_agent = MemoryAgent()
