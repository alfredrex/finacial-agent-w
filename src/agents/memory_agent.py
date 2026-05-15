"""MemoryAgent - 四层混合记忆检索

接入 kvstore (L1/L2/L3) + ChromaDB (L4) 的混合记忆系统。
检索结果注入 AgentState，供后续 DataAgent/AnalysisAgent 使用。
"""

from typing import Dict, Any, List, Optional

from src.agents.base_agent import BaseAgent
from src.state import AgentState


class MemoryAgent(BaseAgent):
    """负责从四层混合记忆系统中检索相关信息。

    检索流程:
      L1 瞬时 → L2 用户 → L3 股票 → L4 语义 (短路)
      结果注入 state["memory_context"] / state["hybrid_memory"]
    """

    def __init__(self, hybrid_memory=None, fact_store=None, query_router=None):
        super().__init__(
            name="MemoryAgent",
            description="从 L1/L2/L3/L4 混合记忆中检索历史上下文和结构化信息",
            tool_categories=[],
        )
        self.max_iterations = 1
        self._hybrid_memory = hybrid_memory  # 由 workflow 注入
        self._fact_store = fact_store        # SQL FactStore
        self._query_router = query_router    # Query Router

    def set_hybrid_memory(self, hms):
        """注入 HybridMemorySystem 实例。"""
        self._hybrid_memory = hms

    def set_fact_store(self, fact_store, query_router=None):
        """注入 SQL FactStore 和 Query Router。"""
        self._fact_store = fact_store
        self._query_router = query_router

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
        self._log_message(state, "开始四层混合记忆检索...")

        query = state.get("rewritten_query") or state.get("query", "")
        user_id = state.get("user_id", "default")

        if self._hybrid_memory is None:
            # Fallback: 纯 ChromaDB (兼容旧模式)
            return await self._process_fallback(state, query)

        try:
            # 确保 user_id 同步
            self._hybrid_memory.user_id = user_id

            # 四层检索
            ctx = await self._hybrid_memory.retrieve(query)

            # ── V4: DataSourcePipeline 多级数据获取链 ──
            sql_results = []
            state["conflict_info"] = None
            if self._fact_store and self._query_router:
                try:
                    plan = self._query_router.route(query)
                    state["query_plan"] = plan.to_dict()

                    # 运行多级链
                    from src.memory.data_source_pipeline import DataSourcePipeline
                    pipeline = DataSourcePipeline(self._fact_store)
                    pipe_result = pipeline.execute(
                        priority_chain=plan.data_source_priority,
                        ticker=plan.ticker or "",
                        company_name=plan.company_name or "",
                        report_period=plan.report_period or "2026Q1",
                        metrics=plan.metrics,
                        query=query,
                    )

                    # 提取 SQL 结果
                    if pipe_result.sql_result:
                        for d in pipe_result.sql_result.get("data", []):
                            val = d["value"]
                            if abs(val) >= 1e8:
                                display = f"{val/1e8:.2f}亿元"
                            elif abs(val) >= 1e4:
                                display = f"{val/1e4:.2f}万元"
                            else:
                                display = f"{val:.4f}{d.get('unit','元')}"
                            sql_results.append({
                                "metric_code": d["metric_code"],
                                "metric_name": d.get("metric_name", d["metric_code"]),
                                "value": val,
                                "display": display,
                                "unit": d.get("unit", "元"),
                                "report_period": d.get("report_period", ""),
                                "source_doc_id": d.get("source_doc_id", ""),
                                "source_page": d.get("source_page"),
                                "data_source": "sql_factstore",
                            })

                    # APi 结果 (作为参考)
                    if pipe_result.api_result:
                        api_metrics = pipe_result.api_result.get("data", [])
                        if api_metrics and not sql_results:
                            # 仅有 API 结果时，作为答案
                            for d in api_metrics:
                                val = d["value"]
                                display = f"{val/1e8:.2f}亿元" if abs(val) >= 1e8 else f"{val:.4f}{d.get('unit','')}"
                                sql_results.append({
                                    "metric_code": d["metric_code"],
                                    "metric_name": d.get("metric_name", ""),
                                    "value": val,
                                    "display": display,
                                    "unit": d.get("unit", ""),
                                    "report_period": d.get("report_period", ""),
                                    "data_source": "api_eastmoney",
                                })

                    # 冲突信息
                    if pipe_result.conflict:
                        state["conflict_info"] = pipe_result.conflict
                        self._log_message(state, f"数据冲突检测: {pipe_result.conflict[:100]}...")

                    # Web discovery → 标记需要入库
                    if pipe_result.needs_ingestion:
                        state["needs_on_demand_fetch"] = True
                        state["on_demand_info"] = {
                            "ticker": plan.ticker,
                            "company_name": plan.company_name or plan.ticker,
                            "report_period": plan.report_period or "2026Q1",
                            "metrics": plan.metrics,
                            "query_type": plan.query_type.value,
                        }
                        self._log_message(state,
                            f"Web发现 {plan.company_name} 财报信息，标记需要入库验证")

                    if sql_results:
                        self._log_message(state,
                            f"数据获取完成: {len(sql_results)} 指标 "
                            f"(来源: {[s['source'] for s in pipe_result.sources]})")

                    # 计算派生指标
                    if plan.needs_sql and plan.ticker:
                        derived = self._fact_store.compute_derived_metrics(
                            plan.ticker, plan.report_period or "2026Q1"
                        )
                        for d in derived:
                            sql_results.append({
                                "metric_code": d["metric_code"],
                                "metric_name": d["metric_name"],
                                "value": d["value"],
                                "display": f"{d['value']:.2f}{d['unit']}",
                                "unit": d["unit"],
                                "report_period": plan.report_period or "2026Q1",
                                "source_doc_id": d.get("source_doc_id", ""),
                                "source_page": d.get("source_page"),
                                "data_source": "sql_factstore_computed",
                                "formula": d.get("formula", ""),
                            })
                except Exception as e:
                    self._log_message(state, f"SQL FactStore 查询异常: {e}")
                    state.setdefault("query_plan", {})

            # ── 注入 state ──
            # memory_context: 向后兼容的文本列表
            combined = ctx.get_combined_context()
            state["memory_context"] = [combined] if combined else []

            # memory_sources: 标记哪些层命中
            memory_sources_list = []
            for layer in ctx.layers_hit:
                memory_sources_list.append({
                    "type": f"kvstore_{layer.lower()}",
                    "layer": layer,
                })
            if ctx.rag_doc_ids:
                memory_sources_list.append({
                    "type": "chromadb_l4",
                    "doc_count": len(ctx.rag_doc_ids),
                })
            state["memory_sources"] = memory_sources_list

            # hybrid_memory: 结构化结果 (供后续 Agent 按字段读取)
            state["hybrid_memory"] = ctx.to_dict()

            # ── 注入 SQL 结果到 collected_data (最高优先级) ──
            if sql_results:
                existing = state.get("collected_data", [])
                if not isinstance(existing, list):
                    existing = []
                state["collected_data"] = sql_results + existing
                state["sql_factstore_results"] = sql_results

            # 向 collected_data 注入 L3 股票数据 (DataAgent 可直接使用)
            stock_data = []
            for code, info in ctx.stock_info.items():
                base = info.get("base", {})
                quote = info.get("quote", {})
                if base or quote:
                    stock_data.append({
                        "code": code,
                        "name": base.get("name", ""),
                        "sector": base.get("sector", ""),
                        "pe_ttm": base.get("pe_ttm", ""),
                        "price": quote.get("price", ""),
                        "change_pct": quote.get("change_pct", ""),
                        "source": "kvstore_l3",
                    })
            if stock_data:
                existing = state.get("collected_data", [])
                if not isinstance(existing, list):
                    existing = []
                state["collected_data"] = existing + stock_data

            # 注入 RAG doc_id 列表 (供后续精确 ChromaDB 检索)
            if ctx.rag_doc_ids:
                existing_rag = state.get("rag_context", [])
                if not isinstance(existing_rag, list):
                    existing_rag = []
                state["rag_context"] = existing_rag + ctx.rag_doc_ids

            # 注入 L4 语义检索内容到 collected_data (QAAgent 可直接读取)
            if ctx.semantic_results:
                l4_data = []
                for r in ctx.semantic_results[:5]:
                    content = r.get("content", "") or r.get("page_content", "")
                    meta = r.get("metadata", {})
                    l4_data.append({
                        "content": content[:800],
                        "title": meta.get("title", ""),
                        "source": meta.get("source", ""),
                        "date": meta.get("date", ""),
                        "data_source": "chromadb_l4",
                    })
                existing = state.get("collected_data", [])
                if not isinstance(existing, list):
                    existing = []
                state["collected_data"] = existing + l4_data

            # 用户画像摘要
            state["user_memory_summary"] = ctx.user_summary or "暂无用户偏好信息"

            # 思考日志
            hit_desc = " → ".join(ctx.layers_hit)
            state["thought"] = (
                f"四层记忆检索完成: {hit_desc} | "
                f"命中 {len(ctx.stock_info)} 只股票, "
                f"{len(ctx.rag_doc_ids)} 个RAG文档, "
                f"{len(ctx.semantic_results)} 条语义结果"
            )
            self._log_message(state, state["thought"])

        except Exception as e:
            self._log_message(state, f"混合记忆检索失败: {e}")
            state["memory_context"] = [f"记忆检索异常: {str(e)}"]
            state["memory_sources"] = [{"type": "error", "error": str(e)}]
            state["hybrid_memory"] = {}
            state["user_memory_summary"] = "暂无用户偏好信息"
            state["thought"] = f"记忆检索失败: {e}"

        state["memory_retrieval_done"] = True
        state["is_finished"] = True
        state["iteration_logs"].append({
            "iteration": 1,
            "thought": state.get("thought", ""),
            "action": "hybrid_memory_retrieval",
            "observation": (
                f"Layers: {state.get('hybrid_memory', {}).get('layers_hit', [])}"
            ),
        })

        return state

    async def _process_fallback(self, state: AgentState, query: str) -> AgentState:
        """无 kvstore 时的降级方案 (纯 ChromaDB)。"""
        try:
            from src.memory import memory_system
            mem_results = await memory_system.retrieve(query_text=query, limit=5)
            memory_context_str = memory_system.get_context_string(mem_results, top_k=5)
        except Exception:
            memory_context_str = "暂无相关历史记忆"
            mem_results = {}

        state["memory_context"] = [memory_context_str] if memory_context_str != "暂无相关历史记忆" else []
        state["memory_sources"] = [{"type": "chromadb_fallback"}]
        state["hybrid_memory"] = {"layers_hit": ["L4_fallback"]}
        state["memory_retrieval_done"] = True
        state["is_finished"] = True
        state["thought"] = "降级模式: 仅 ChromaDB 检索"
        return state


# 全局实例 (由 workflow 注入 hybrid_memory)
memory_agent = MemoryAgent()
