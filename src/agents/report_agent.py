from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class ReportAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="ReportAgent",
            description="聚焦投研报告生成，整合数据和分析结果生成专业报告，不可调用工具但可请求返回其他Agent",
            tool_categories=[]
        )
        self.max_iterations = 1
        
        self.report_system_prompt = """你是 {name}，{description}

【重要】你不能调用任何工具！

【数据能力范围】:
- 支持: A股股票、A股新闻、A股公司信息、市场指数
- 不支持: 港股、美股、期货、外汇、加密货币

【当前状态】:
data_unavailable: {data_unavailable}
analysis_unavailable: {analysis_unavailable}

【对话历史】:
{conversation_history}

【判断规则】:
1. 如果 data_unavailable 包含需要的数据 → 直接生成报告，说明限制
2. 如果 analysis_unavailable 包含需要的分析 → 直接生成报告，说明限制
3. 如果信息足够 → 生成完整报告
4. 如果信息不足但数据可获取 → 请求返回 DataAgent/AnalysisAgent

【数据来源】（按优先级排序）:
1. collected_data: 已收集的数据（最高优先级）
2. analysis_results: 分析结果（次高优先级）
3. 对话历史（理解上下文）
4. 大模型自身知识（最低优先级，仅在其他来源都没有时使用）

【输出格式】:
直接输出完整报告，或请求返回其他Agent获取更多信息。

如果信息足够，输出完整报告（使用Markdown格式）。

如果信息不足且数据可获取，输出以下格式请求返回：
NEED_MORE: Agent名称

【重要规则】:
1. 优先使用已有信息生成报告
2. 如果 data_unavailable 包含需要的数据，不要再请求 DataAgent
3. 如果 analysis_unavailable 包含需要的分析，不要再请求 AnalysisAgent
4. 只有在确实无法生成报告且数据可获取时才请求返回其他Agent
5. 报告要结构清晰、内容专业
6. 注意理解对话历史中的代词指代"""

    def _format_conversation_history(self, history: list) -> str:
        if not history:
            return "无"
        parts = []
        for i, h in enumerate(history[-5:]):
            q = h.get("question", "")
            a = h.get("answer", "")[:300] if h.get("answer") else ""
            parts.append(f"第{i+1}轮:\n用户: {q}\n系统: {a}")
        return "\n\n".join(parts)
    
    def _format_context(self, state: AgentState, is_deep_mode: bool = False) -> str:
        parts = []
        
        if is_deep_mode:
            deep_analysis_done = state.get("deep_analysis_done", False)
            analysis_results = state.get("analysis_results", [])
            
            if deep_analysis_done and analysis_results:
                for result in analysis_results:
                    if isinstance(result, dict) and result.get("type") == "deep_analysis":
                        parts.append("【深度分析结果】:")
                        parts.append(str(result.get("content", ""))[:5000])
                        break
            else:
                if analysis_results:
                    parts.append("\n【分析结果】:")
                    for i, result in enumerate(analysis_results[-5:]):
                        parts.append(f"{i+1}. {str(result)[:500]}")
        else:
            rag_context = state.get("rag_context", [])
            if rag_context:
                parts.append("\n【向量库检索结果】:")
                for i, ctx in enumerate(rag_context[:5]):
                    parts.append(f"{i+1}. {str(ctx)[:300]}")
            
            memory_context = state.get("memory_context", [])
            if memory_context:
                parts.append("\n【历史记忆】:")
                for i, mem in enumerate(memory_context[:3]):
                    parts.append(f"{i+1}. {str(mem)[:300]}")
            
            conversation_history = state.get("conversation_history", [])
            if conversation_history:
                parts.append("\n【对话历史】:")
                for i, h in enumerate(conversation_history[-3:]):
                    parts.append(f"{i+1}. {str(h)[:200]}")
            
            collected_data = state.get("collected_data", [])
            if collected_data:
                parts.append("\n【已收集数据】:")
                for i, data in enumerate(collected_data[-5:]):
                    parts.append(f"{i+1}. {str(data)[:300]}")
            
            analysis_results = state.get("analysis_results", [])
            if analysis_results:
                parts.append("\n【分析结果】:")
                for i, result in enumerate(analysis_results[-3:]):
                    parts.append(f"{i+1}. {str(result)[:300]}")
        
        data_unavailable = state.get("data_unavailable", [])
        if data_unavailable:
            parts.append(f"\n【数据不可获取】: {', '.join(data_unavailable)}")
        
        analysis_unavailable = state.get("analysis_unavailable", [])
        if analysis_unavailable:
            parts.append(f"\n【分析不可获取】: {', '.join(analysis_unavailable)}")
        
        return "\n".join(parts) if parts else "无额外上下文信息"
    
    def _parse_response(self, response: str) -> dict:
        if "NEED_MORE:" in response:
            lines = response.strip().split("\n")
            agent_name = None
            
            for line in lines:
                if line.startswith("NEED_MORE:"):
                    agent_name = line.replace("NEED_MORE:", "").strip()
            
            if agent_name:
                return {
                    "type": "need_more",
                    "agent": agent_name
                }
        
        return {
            "type": "report",
            "content": response
        }
    
    def _load_skill_template(self, template_name: str) -> str:
        import os
        template_path = os.path.join(os.path.dirname(__file__), "..", "skills", "report_skill", f"{template_name}.md")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    
    def _select_template(self, report_type: str, report_domain: str) -> str:
        if report_type == "简单":
            return "template_short"
        
        if report_type == "复杂":
            if report_domain == "公司":
                return "template_full_company"
            elif report_domain == "行业":
                return "template_full_industry"
            elif report_domain == "策略":
                return "template_full_strategy"
            else:
                return "template_deep_common"
        
        return "template_deep_common"
    
    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        self._log_message(state, "开始生成投研报告...")
        
        report_type = state.get("report_type")
        report_domain = state.get("report_domain")
        output_type = state.get("output_type", "qa")
        
        self._log_message(state, f"Dispatcher 参数 - output_type: {output_type}, report_type: {report_type}, report_domain: {report_domain}")
        
        if report_type is None:
            report_type = "简单"
            self._log_message(state, "report_type 未设置，使用默认值: 简单")
        
        rag_context = state.get("rag_context", [])
        collected_data = state.get("collected_data", [])
        analysis_results = state.get("analysis_results", [])
        data_unavailable = state.get("data_unavailable", [])
        analysis_unavailable = state.get("analysis_unavailable", [])
        conversation_history = state.get("conversation_history", [])
        
        if rag_context:
            self._log_message(state, f"向量库已有 {len(rag_context)} 条相关内容")
        if collected_data:
            self._log_message(state, f"已收集数据: {len(collected_data)} 条")
        if analysis_results:
            self._log_message(state, f"分析结果: {len(analysis_results)} 条")
        if data_unavailable:
            self._log_message(state, f"数据不可获取: {data_unavailable}")
        if analysis_unavailable:
            self._log_message(state, f"分析不可获取: {analysis_unavailable}")
        if conversation_history:
            self._log_message(state, f"对话历史: {len(conversation_history)} 轮")
        
        selected_template_name = self._select_template(report_type, report_domain)
        self._log_message(state, f"选择模板: {selected_template_name}")
        
        template = self._load_skill_template(selected_template_name)
        
        instruction = """
1. 不修改分析内容
2. 严格按模板结构排版
3. 生成标准化报告
"""
        
        llm = self._get_llm()
        
        system_prompt = f"""{self.report_system_prompt.format(
    name=self.name,
    description=self.description,
    data_unavailable=data_unavailable,
    analysis_unavailable=analysis_unavailable,
    conversation_history=self._format_conversation_history(conversation_history)
)}

【报告模板参考】:
{template}

【格式要求】:
{instruction}"""
        
        prompt = f"""用户问题: {state.get('query', '')}

{self._format_context(state, is_deep_mode=(report_type == "复杂"))}

请生成投研报告，或请求返回其他Agent获取更多信息。"""
        
        messages = [
            self._create_system_message(system_prompt),
            self._create_human_message(prompt)
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            parsed = self._parse_response(response.content)
            
            if parsed["type"] == "need_more":
                state["need_more_agent"] = parsed["agent"]
                state["thought"] = f"需要返回 {parsed['agent']}"
                state["action"] = f"return_to({parsed['agent']})"
                self._log_message(state, f"请求返回: {parsed['agent']}")
            else:
                state["report"] = parsed["content"]
                state["is_finished"] = True
                self._log_message(state, "报告生成完成")
            
            state["iteration_logs"].append({
                "iteration": 1,
                "thought": state.get("thought", ""),
                "action": state.get("action", ""),
                "observation": None
            })
            
        except Exception as e:
            state["report"] = f"生成报告时出错: {str(e)}"
            state["is_finished"] = True
        
        return state


report_agent = ReportAgent()
