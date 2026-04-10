from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory
from typing import Dict, Any, List, Optional
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings


class MemoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MemoryAgent",
            description="负责记忆检索，包括向量库检索、实体记忆检索、任务记忆检索等",
            tool_categories=[]
        )
        self.max_iterations = 1
        
        self.memory_retrieval_prompt = """你是 {name}，{description}

你的任务是从多个记忆源中检索相关信息，为后续处理提供上下文。

【记忆源类型】:
1. 向量库记忆 (RAG): 已上传的文档、报告等知识库内容
2. 实体记忆: 之前分析过的股票、公司等实体的相关信息
3. 任务记忆: 之前执行过的类似任务及其结果

【检索策略】:
- 根据用户问题判断需要检索哪些记忆源
- 合并多个记忆源的结果
- 去重并按相关性排序

【输出格式】:
直接输出检索到的相关内容摘要，或说明未找到相关记忆。

【重要规则】:
1. 优先检索最相关的记忆源
2. 如果找到相关记忆，简要总结内容
3. 如果未找到相关记忆，说明"未找到相关历史记忆"
4. 不要编造不存在的记忆内容"""

    def _get_llm(self, temperature: float = None) -> ChatOpenAI:
        if self._llm is None:
            llm_kwargs = {
                "model": settings.OPENAI_MODEL,
                "max_tokens": settings.MAX_TOKENS,
            }
            if temperature is not None:
                llm_kwargs["temperature"] = temperature
            else:
                llm_kwargs["temperature"] = settings.TEMPERATURE
            self._llm = ChatOpenAI(**llm_kwargs)
        return self._llm

    def _create_system_message(self, content: str) -> SystemMessage:
        return SystemMessage(content=content)

    def _create_human_message(self, content: str) -> HumanMessage:
        return HumanMessage(content=content)

    def _update_token_usage(self, response, state: AgentState):
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            state.setdefault("metadata", {})
            state["metadata"]["token_usage"] = {
                "prompt_tokens": response.usage_metadata.get("input_tokens", 0),
                "completion_tokens": response.usage_metadata.get("output_tokens", 0),
                "total_tokens": response.usage_metadata.get("total_tokens", 0)
            }

    def _log_message(self, state: AgentState, message: str):
        state.setdefault("messages", [])
        state["messages"].append({
            "agent": self.name,
            "message": message
        })

    def _format_entity_memory(self, entity_memory: dict) -> str:
        if not entity_memory:
            return "暂无实体记忆"
        
        parts = []
        for entity, info in list(entity_memory.items())[:5]:
            parts.append(f"- {entity}: {str(info)[:200]}")
        return "\n".join(parts) if parts else "暂无实体记忆"

    def _format_task_memory(self, task_memory: dict) -> str:
        if not task_memory:
            return "暂无任务记忆"
        
        parts = []
        for task_key, result in list(task_memory.items())[:5]:
            parts.append(f"- 任务: {task_key}\n  结果摘要: {str(result)[:200]}")
        return "\n".join(parts) if parts else "暂无任务记忆"

    def _format_rag_context(self, rag_context: List[str]) -> str:
        if not rag_context:
            return "暂无向量库内容"
        
        parts = []
        for i, ctx in enumerate(rag_context[:5]):
            parts.append(f"{i+1}. {str(ctx)[:300]}")
        return "\n".join(parts) if parts else "暂无向量库内容"

    async def _retrieve_from_rag(self, state: AgentState, query: str) -> List[str]:
        rag_context = state.get("rag_context", [])
        if not rag_context:
            return []
        
        llm = self._get_llm()
        
        prompt = f"""从以下向量库内容中，找出与用户问题最相关的内容：

用户问题: {query}

向量库内容:
{self._format_rag_context(rag_context)}

请输出最相关的内容摘要，如果没有相关内容，输出"无相关内容"。"""

        messages = [
            self._create_system_message("你是信息检索专家。"),
            self._create_human_message(prompt)
        ]

        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            content = response.content.strip()
            if content != "无相关内容":
                return [content]
        except Exception as e:
            self._log_message(state, f"RAG检索失败: {str(e)}")
        
        return []

    async def _retrieve_from_entity_memory(self, state: AgentState, query: str) -> List[str]:
        entity_memory = state.get("entity_memory", {})
        if not entity_memory:
            return []
        
        llm = self._get_llm()
        
        prompt = f"""从以下实体记忆中，找出与用户问题最相关的内容：

用户问题: {query}

实体记忆:
{self._format_entity_memory(entity_memory)}

请输出最相关的实体及其信息，如果没有相关内容，输出"无相关内容"。"""

        messages = [
            self._create_system_message("你是信息检索专家。"),
            self._create_human_message(prompt)
        ]

        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            content = response.content.strip()
            if content != "无相关内容":
                return [content]
        except Exception as e:
            self._log_message(state, f"实体记忆检索失败: {str(e)}")
        
        return []

    async def _retrieve_from_task_memory(self, state: AgentState, query: str) -> List[str]:
        task_memory = state.get("task_memory", {})
        if not task_memory:
            return []
        
        llm = self._get_llm()
        
        prompt = f"""从以下任务记忆中，找出与用户问题最相关的内容：

用户问题: {query}

任务记忆:
{self._format_task_memory(task_memory)}

请输出最相关的任务及其结果，如果没有相关内容，输出"无相关内容"。"""

        messages = [
            self._create_system_message("你是信息检索专家。"),
            self._create_human_message(prompt)
        ]

        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            content = response.content.strip()
            if content != "无相关内容":
                return [content]
        except Exception as e:
            self._log_message(state, f"任务记忆检索失败: {str(e)}")
        
        return []

    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        self._log_message(state, "开始记忆检索...")

        query = state.get("rewritten_query", state.get("query", ""))
        
        memory_context = []
        memory_sources = []

        rag_context = state.get("rag_context", [])
        if rag_context:
            self._log_message(state, f"向量库已有 {len(rag_context)} 条内容，开始检索...")
            rag_results = await self._retrieve_from_rag(state, query)
            if rag_results:
                memory_context.extend(rag_results)
                memory_sources.append({"type": "rag", "count": len(rag_results)})
                self._log_message(state, f"向量库检索完成，找到 {len(rag_results)} 条相关内容")

        entity_memory = state.get("entity_memory", {})
        if entity_memory:
            self._log_message(state, f"实体记忆已有 {len(entity_memory)} 个实体，开始检索...")
            entity_results = await self._retrieve_from_entity_memory(state, query)
            if entity_results:
                memory_context.extend(entity_results)
                memory_sources.append({"type": "entity_memory", "count": len(entity_results)})
                self._log_message(state, f"实体记忆检索完成，找到 {len(entity_results)} 条相关内容")

        task_memory = state.get("task_memory", {})
        if task_memory:
            self._log_message(state, f"任务记忆已有 {len(task_memory)} 个任务，开始检索...")
            task_results = await self._retrieve_from_task_memory(state, query)
            if task_results:
                memory_context.extend(task_results)
                memory_sources.append({"type": "task_memory", "count": len(task_results)})
                self._log_message(state, f"任务记忆检索完成，找到 {len(task_results)} 条相关内容")

        if memory_context:
            state["memory_context"] = memory_context
            state["memory_sources"] = memory_sources
            state["thought"] = f"从 {len(memory_sources)} 个记忆源检索到 {len(memory_context)} 条相关内容"
            self._log_message(state, f"记忆检索完成，共找到 {len(memory_context)} 条相关内容")
        else:
            state["memory_context"] = []
            state["memory_sources"] = []
            state["thought"] = "未找到相关历史记忆"
            self._log_message(state, "未找到相关历史记忆")

        state["memory_retrieval_done"] = True
        state["is_finished"] = True

        state["iteration_logs"].append({
            "iteration": 1,
            "thought": state.get("thought", ""),
            "action": "memory_retrieval",
            "observation": f"检索结果: {len(memory_context)} 条"
        })

        return state


memory_agent = MemoryAgent()
