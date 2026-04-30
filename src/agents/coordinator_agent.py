"""
协调器 Agent (CoordinatorAgent)
复杂任务分解为子任务DAG → 分配 Specialist Agent 执行 → 收集结果 → 合成输出
"""
import json
import asyncio
import copy
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory
from src.communication import (
    message_bus, blackboard, agent_registry,
    MessageType, AgentMessage,
)

# 所有 Specialist Agent（惰性导入避免循环依赖）
_agents_cache = None


def _get_specialist_agents():
    global _agents_cache
    if _agents_cache is None:
        from src.agents.data_agent import data_agent
        from src.agents.analysis_agent import analysis_agent
        from src.agents.qa_agent import qa_agent
        from src.agents.report_agent import report_agent
        from src.agents.memory_agent import memory_agent
        from src.agents.visualization_agent import visualization_agent
        _agents_cache = {
            "DataAgent": data_agent,
            "AnalysisAgent": analysis_agent,
            "QAAgent": qa_agent,
            "ReportAgent": report_agent,
            "MemoryAgent": memory_agent,
            "VisualizationAgent": visualization_agent,
        }
    return _agents_cache


class SubTask:
    """单个子任务"""
    def __init__(self, task_id: str, description: str, target_agent: str,
                 depends_on: List[str] = None, params: dict = None):
        self.task_id = task_id
        self.description = description
        self.target_agent = target_agent
        self.depends_on = depends_on or []
        self.params = params or {}
        self.status = "pending"  # pending | running | completed | failed
        self.result = None
        self.error = None


class CoordinatorAgent(BaseAgent):
    """
    协调器：任务分解 → 分配 → 监控 → 结果聚合

    只在有复杂任务时介入（Dispatcher 判断需要协调时），
    简单任务仍走现有路由。
    """

    def __init__(self):
        super().__init__(
            name="CoordinatorAgent",
            description="负责任务分解、子任务分配和结果聚合的协调器",
            tool_categories=[],
        )
        self.max_iterations = 1

    def _log_message(self, state: AgentState, message: str):
        state.setdefault("messages", [])
        state["messages"].append({
            "agent": self.name,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })

    def _get_available_agents(self) -> List[dict]:
        """获取当前可用的 Agent 及其能力"""
        return [
            {"name": "DataAgent", "description": "金融数据采集",
             "capabilities": ["data_collection", "stock_data", "news", "company_info"]},
            {"name": "AnalysisAgent", "description": "技术分析与深度分析",
             "capabilities": ["analysis", "indicator_calculation", "deep_analysis"]},
            {"name": "VisualizationAgent", "description": "图表生成",
             "capabilities": ["visualization", "chart_generation"]},
            {"name": "QAAgent", "description": "问答回答生成",
             "capabilities": ["qa", "answer_generation"]},
            {"name": "ReportAgent", "description": "结构化报告生成",
             "capabilities": ["report", "report_generation"]},
            {"name": "MemoryAgent", "description": "记忆检索",
             "capabilities": ["memory_retrieval", "context_provision"]},
        ]

    async def _decompose_task(self, query: str, state: AgentState) -> List[SubTask]:
        """用 LLM 将复杂任务分解为子任务 DAG"""
        agents_info = self._get_available_agents()
        agents_desc = "\n".join(
            f"- {a['name']}: {a['description']} (能力: {', '.join(a['capabilities'])})"
            for a in agents_info
        )

        prompt = f"""分析以下用户查询，将其分解为可并行/串行执行的子任务列表。

可用 Agent:
{agents_desc}

用户查询: {query}

以 JSON 数组格式输出子任务，每个子任务包含:
- task_id: 唯一标识 (t1, t2, ...)
- description: 子任务描述
- target_agent: 最适合的 Agent 名称
- depends_on: 依赖的子任务ID列表 (无依赖填 [])
- params: 参数 (如 symbol, days 等，从查询中推断)

输出格式 (仅 JSON):
[
  {{"task_id":"t1","description":"...","target_agent":"DataAgent","depends_on":[],"params":{{"symbol":"600519"}}}},
  ...
]"""

        try:
            response = await self.invoke_llm(
                system_prompt="你是任务规划专家，擅长将复杂金融分析任务分解为子任务DAG。输出严格 JSON。",
                user_input=prompt,
                state=state,
            )

            # 解析 JSON
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            tasks_data = json.loads(response.strip())
            tasks = [SubTask(**t) for t in tasks_data]

            # 注册到黑板
            for t in tasks:
                blackboard.write("workflow", f"task.{t.task_id}", {
                    "description": t.description,
                    "status": t.status,
                    "target": t.target_agent,
                }, updated_by=self.name)

            self._log_message(state, f"任务分解完成: {len(tasks)} 个子任务")
            return tasks

        except Exception as e:
            self._log_message(state, f"任务分解失败，回退到简单模式: {e}")
            return []

    async def _execute_tasks(self, tasks: List[SubTask], state: AgentState) -> Dict[str, Any]:
        """按 DAG 依赖关系执行子任务（实际调用 Specialist Agent）"""
        agents = _get_specialist_agents()
        completed: Dict[str, Any] = {}
        pending = {t.task_id: t for t in tasks}

        # 注册所有 Agent 到消息总线
        for a in self._get_available_agents():
            message_bus.register_agent(a["name"])

        max_rounds = 20
        round_num = 0

        while pending and round_num < max_rounds:
            round_num += 1
            # 找可执行的任务（所有依赖已完成）
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.depends_on)
            ]

            if not ready:
                break

            # 并行执行所有 ready 的子任务
            async def execute_one(task: SubTask) -> Tuple[str, dict]:
                task.status = "running"
                blackboard.write("workflow", f"task.{task.task_id}.status", "running",
                                 updated_by=self.name)

                # 构造子任务 state（基于当前 state 但限制 scope）
                sub_state: AgentState = {
                    **copy.deepcopy(state),
                    "query": task.params.get("query", state.get("query", "")),
                    "rewritten_query": None,
                    "collected_data": [],
                    "analysis_results": [],
                    "answer": None,
                    "current_agent": task.target_agent,
                    "is_finished": False,
                    "agent_iteration": 0,
                    "iteration_logs": [],
                    "needs_data_collection": False,
                    "needs_analysis": False,
                    "needs_visualization": False,
                    "needs_deep_analysis": False,
                    "output_type": "qa",
                }

                try:
                    agent = agents.get(task.target_agent)
                    timeout = 120

                    if agent is None:
                        raise ValueError(f"未知 Agent: {task.target_agent}")

                    # 调用 Agent 的 process 方法
                    result = await asyncio.wait_for(
                        agent.process(sub_state),
                        timeout=timeout,
                    )

                    summary = (
                        result.get("answer", "") or
                        str(result.get("analysis_results", []))[:200] or
                        f"{task.target_agent} 已完成: {task.description}"
                    )

                    result_entry = {
                        "task": task.description,
                        "agent": task.target_agent,
                        "summary": str(summary)[:500],
                        "status": "completed",
                        "data": result.get("collected_data", []),
                        "analysis": result.get("analysis_results", []),
                    }

                    blackboard.write("workflow", f"task.{task.task_id}.result", result_entry,
                                     updated_by=self.name)
                    return task.task_id, result_entry

                except asyncio.TimeoutError:
                    err_entry = {
                        "task": task.description,
                        "agent": task.target_agent,
                        "summary": f"{task.target_agent} 执行超时",
                        "status": "failed",
                        "data": [],
                        "analysis": [],
                    }
                    blackboard.write("workflow", f"task.{task.task_id}.result", err_entry,
                                     updated_by=self.name)
                    return task.task_id, err_entry

                except Exception as e:
                    err_entry = {
                        "task": task.description,
                        "agent": task.target_agent,
                        "summary": f"执行失败: {str(e)}",
                        "status": "failed",
                        "data": [],
                        "analysis": [],
                    }
                    blackboard.write("workflow", f"task.{task.task_id}.result", err_entry,
                                     updated_by=self.name)
                    return task.task_id, err_entry

            # 并行执行所有 ready 任务
            results = await asyncio.gather(*[execute_one(t) for t in ready])

            for task_id, result_entry in results:
                del pending[task_id]
                completed[task_id] = result_entry

        return completed

    async def _synthesize_results(self, query: str, task_results: Dict[str, Any],
                                  state: AgentState) -> str:
        """合成所有子任务结果为综合回答"""
        parts = []
        all_data = []
        all_analysis = []
        failed_count = 0

        for tid, result in task_results.items():
            status_icon = "✅" if result.get("status") == "completed" else "❌"
            if result.get("status") != "completed":
                failed_count += 1
            parts.append(f"  {status_icon} {result['task']} (执行: {result['agent']})")
            all_data.extend(result.get("data", []))
            all_analysis.extend(result.get("analysis", []))

        task_summary = "\n".join(parts)

        # 将聚合结果和数据写回黑板
        blackboard.write("workflow", "coordinator.final_summary", {
            "query": query,
            "task_count": len(task_results),
            "failed_count": failed_count,
            "data_count": len(all_data),
            "analysis_count": len(all_analysis),
        }, updated_by=self.name)

        # 将 collected_data / analysis_results 合并回主 state
        if all_data:
            state.setdefault("collected_data", []).extend(all_data)
        if all_analysis:
            state.setdefault("analysis_results", []).extend(all_analysis)

        status = "全部成功" if failed_count == 0 else f"{failed_count} 个失败"
        return (f"\n[协调器] 任务执行摘要 ({status}):\n{task_summary}\n"
                f"  合计: {len(all_data)} 条数据, {len(all_analysis)} 条分析")

    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["agent_iteration"] = 0

        query = state.get("rewritten_query", state.get("query", ""))
        self._log_message(state, f"协调器开始处理: {query}")

        # 1. 任务分解
        tasks = await self._decompose_task(query, state)

        if not tasks:
            # 简单任务，直接标记完成
            state["is_finished"] = True
            state["thought"] = "无需协调，直接处理"
            self._log_message(state, "任务简单，无需分解")
            return state

        # 2. 执行子任务 DAG
        task_results = await self._execute_tasks(tasks, state)

        # 3. 合成结果
        summary = await self._synthesize_results(query, task_results, state)

        state["answer"] = state.get("answer", "") + summary
        state["is_finished"] = True
        state["thought"] = f"协调完成: {len(task_results)}/{len(tasks)} 个子任务完成"
        self._log_message(state, state["thought"])

        return state


coordinator_agent = CoordinatorAgent()
