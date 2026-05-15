from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class QAAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="QAAgent",
            description="专注问答输出，整合已收集的信息并回答用户问题，不可调用工具但可请求返回其他Agent",
            tool_categories=[]
        )
        self.max_iterations = 1
        
        self.qa_system_prompt = """你是 {name}，{description}

【重要】你不能调用任何工具！

【当前状态】:
visualization_done: {visualization_done}
data_unavailable: {data_unavailable}
analysis_unavailable: {analysis_unavailable}
charts: {charts}
tables: {tables}

【对话历史】:
{conversation_history}

【判断规则】:
1. 如果 visualization_done=True 且有 charts/tables → 直接输出答案，包含图表信息
2. 如果某些数据无法获取 → 用友好的语言向用户说明，**不要提及系统内部状态或技术术语**
3. 如果信息足够 → 直接回答
4. 只有在确实无法回答时才请求返回其他Agent

【重要】防止无限循环:
- 如果 visualization_done=True，说明可视化已完成，直接输出答案
- 如果 collected_data 已有相关数据，直接使用
- 如果某些数据无法获取，用友好语言说明，直接回答
- 不要反复请求同一个 Agent

【数据来源】（按优先级排序）:
1. charts/tables: 可视化图表（最高优先级）
2. collected_data: 已收集的数据
3. analysis_results: 分析结果
4. 对话历史
5. 大模型自身知识（最低优先级）

【输出格式】:
直接输出你的回答。

如果需要展示图表，使用格式：
![图表描述](图片路径)

【重要规则】:
【绝对禁止】:
1. 没有数据时，不要编造理由（如"季度尚未结束"、"数据尚未公布"等）
2. 你无法判断数据是否存在——只能说"我目前没有获取到该数据"
3. 不知道就是不知道，不要猜测或推测
4. 绝对禁止向用户暴露系统内部状态（如data_unavailable、collected_data等技术术语）
5. 没有数据时，简洁告诉用户并建议：尝试其他公司、检查股票代码、或等待数据更新
6. 如果有收集到的数据，直接给出答案，带数字、单位、来源
"""

        self.exception_handling_prompt = """你是 {name}，现在需要处理系统异常。

【异常信息】:
- 出错Agent: {exception_agent}
- 错误类型: {exception_type}
- 错误详情: {exception_error}

【用户原始问题】: {query}

【已收集信息】:
{collected_info}

【处理选项】:
1. RETRY:Agent名称 - 重试某个Agent（例如: RETRY:DataAgent）
2. FALLBACK:备选方案 - 使用备选方案（例如: FALLBACK:使用通用知识回答）
3. END - 直接结束，向用户说明情况

【决策规则】:
1. 如果是临时性错误（网络超时、API限流等）→ 选择重试
2. 如果是数据源问题（数据不可用、格式错误等）→ 选择备选方案
3. 如果是严重错误或无法恢复 → 直接结束

【输出格式】:
必须是以下格式之一:
- RETRY:Agent名称
- FALLBACK:备选方案描述
- END

然后在新的一行说明你的决策理由。"""

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
        
        charts = state.get("charts", [])
        if charts:
            parts.append("\n【生成的图表】:")
            for i, chart in enumerate(charts):
                chart_type = chart.get("type", "未知类型")
                chart_path = chart.get("path", "")
                if chart_path:
                    parts.append(f"{i+1}. {chart_type}: {chart_path}")
        
        tables = state.get("tables", [])
        if tables:
            parts.append("\n【生成的表格】:")
            for i, table in enumerate(tables):
                table_content = table.get("content", "")[:500]
                parts.append(f"{i+1}. {table_content}")
        
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
        
        # 不向LLM暴露系统内部状态，只提供必要的数据信息
        # data_unavailable和analysis_unavailable不展示给LLM，避免技术术语暴露给用户
        
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
            "type": "answer",
            "content": response
        }
    
    def _parse_exception_response(self, response: str) -> dict:
        lines = response.strip().split("\n")
        first_line = lines[0].strip() if lines else ""
        
        if first_line.startswith("RETRY:"):
            agent_name = first_line.replace("RETRY:", "").strip()
            reason = "\n".join(lines[1:]) if len(lines) > 1 else ""
            return {
                "action": "retry",
                "agent": agent_name,
                "reason": reason
            }
        elif first_line.startswith("FALLBACK:"):
            fallback_plan = first_line.replace("FALLBACK:", "").strip()
            reason = "\n".join(lines[1:]) if len(lines) > 1 else ""
            return {
                "action": "fallback",
                "fallback_plan": fallback_plan,
                "reason": reason
            }
        elif first_line == "END":
            reason = "\n".join(lines[1:]) if len(lines) > 1 else ""
            return {
                "action": "end",
                "reason": reason
            }
        
        return {
            "action": "end",
            "reason": response
        }
    
    def _format_collected_info(self, state: AgentState) -> str:
        parts = []
        
        collected_data = state.get("collected_data", [])
        if collected_data:
            parts.append(f"已收集数据: {len(collected_data)} 条")
        
        analysis_results = state.get("analysis_results", [])
        if analysis_results:
            parts.append(f"分析结果: {len(analysis_results)} 条")
        
        return "\n".join(parts) if parts else "暂无已收集信息"
    
    def _load_skill_template(self, template_name: str) -> str:
        import os
        template_path = os.path.join(os.path.dirname(__file__), "..", "skills", "qa_skill", f"{template_name}.md")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    
    def _apply_skill_template(self, content: str, template: str) -> str:
        return f"""{template}

---

## 生成内容

{content}
"""
    
    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        self._log_message(state, "开始处理问答任务...")
        
        exception_info = state.get("exception_info")
        exception_handled = state.get("exception_handled", False)
        
        if exception_info and not exception_handled:
            return await self._handle_exception(state, exception_info)
        
        is_deep_qa = state.get("is_deep_qa", False)
        output_type = state.get("output_type", "qa")
        visualization_done = state.get("visualization_done", False)
        charts = state.get("charts", [])
        tables = state.get("tables", [])
        
        self._log_message(state, f"Dispatcher 参数 - output_type: {output_type}, is_deep_qa: {is_deep_qa}")
        self._log_message(state, f"可视化状态 - visualization_done: {visualization_done}, charts: {len(charts)}, tables: {len(tables)}")
        
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
        
        llm = self._get_llm()
        
        if is_deep_qa:
            self._log_message(state, "深度QA模式：使用 template_deep_qa 模板")
            template = self._load_skill_template("template_deep_qa")
            instruction = """
1. 保留分析核心结论
2. 按问答格式排版
3. 语言简洁专业
"""
            system_prompt = f"""{self.qa_system_prompt.format(
    name=self.name,
    description=self.description,
    visualization_done=visualization_done,
    data_unavailable=data_unavailable,
    analysis_unavailable=analysis_unavailable,
    charts=charts,
    tables=tables,
    conversation_history=self._format_conversation_history(conversation_history)
)}

【深度QA模板参考】:
{template}

【格式要求】:
{instruction}"""
        else:
            system_prompt = self.qa_system_prompt.format(
                name=self.name,
                description=self.description,
                visualization_done=visualization_done,
                data_unavailable=data_unavailable,
                analysis_unavailable=analysis_unavailable,
                charts=charts,
                tables=tables,
                conversation_history=self._format_conversation_history(conversation_history)
            )
        
        prompt = f"""用户问题: {state.get('query', '')}

{self._format_context(state, is_deep_mode=is_deep_qa)}

请回答用户问题，或请求返回其他Agent获取更多信息。"""
        
        messages = [
            self._create_system_message(system_prompt),
            self._create_human_message(prompt)
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            print(f"\n[DEBUG] QAAgent LLM 响应:\n{response.content[:500]}...\n")
            
            parsed = self._parse_response(response.content)
            
            print(f"[DEBUG] QAAgent 解析结果: type={parsed['type']}")
            
            if parsed["type"] == "need_more":
                state["need_more_agent"] = parsed["agent"]
                state["thought"] = f"需要返回 {parsed['agent']}"
                state["action"] = f"return_to({parsed['agent']})"
                self._log_message(state, f"请求返回: {parsed['agent']}")
            else:
                state["answer"] = parsed["content"]
                state["is_finished"] = True
                self._log_message(state, "问答完成")
                print(f"[DEBUG] QAAgent 答案: {parsed['content'][:200]}...")
            
            state["iteration_logs"].append({
                "iteration": 1,
                "thought": state.get("thought", ""),
                "action": state.get("action", ""),
                "observation": None
            })
            
        except Exception as e:
            state["answer"] = f"生成回答时出错: {str(e)}"
            state["is_finished"] = True
        
        return state
    
    async def _handle_exception(self, state: AgentState, exception_info: dict) -> AgentState:
        self._log_message(state, f"检测到异常，开始异常处理...")
        self._log_message(state, f"异常来源: {exception_info.get('agent')}, 类型: {exception_info.get('error_type')}")
        
        llm = self._get_llm()
        
        system_prompt = self.exception_handling_prompt.format(
            name=self.name,
            exception_agent=exception_info.get("agent", "unknown"),
            exception_type=exception_info.get("error_type", "unknown"),
            exception_error=exception_info.get("error", "unknown"),
            query=state.get("query", ""),
            collected_info=self._format_collected_info(state)
        )
        
        messages = [
            self._create_system_message(system_prompt),
            self._create_human_message("请决定如何处理这个异常。")
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            parsed = self._parse_exception_response(response.content)
            
            state["thought"] = f"异常处理决策: {parsed['action']}"
            state["action"] = f"exception_{parsed['action']}"
            
            if parsed["action"] == "retry":
                state["need_more_agent"] = parsed["agent"]
                state["exception_handled"] = True
                self._log_message(state, f"决定重试: {parsed['agent']}, 理由: {parsed.get('reason', '')}")
                
            elif parsed["action"] == "fallback":
                state["answer"] = f"由于系统异常，采用备选方案: {parsed['fallback_plan']}\n\n{parsed.get('reason', '')}"
                state["is_finished"] = True
                state["exception_handled"] = True
                self._log_message(state, f"采用备选方案: {parsed['fallback_plan']}")
                
            else:
                state["answer"] = f"处理过程中遇到异常，无法完成请求。\n\n异常信息: {exception_info.get('error', '')}\n\n处理建议: {parsed.get('reason', '请稍后重试或联系管理员')}"
                state["is_finished"] = True
                state["exception_handled"] = True
                self._log_message(state, f"异常处理结束: {parsed.get('reason', '')}")
            
            state["iteration_logs"].append({
                "iteration": 1,
                "thought": state.get("thought", ""),
                "action": state.get("action", ""),
                "observation": f"异常处理结果: {parsed['action']}"
            })
            
        except Exception as e:
            state["answer"] = f"异常处理失败: {str(e)}\n\n原始异常: {exception_info.get('error', '')}"
            state["is_finished"] = True
            state["exception_handled"] = True
            self._log_message(state, f"异常处理失败: {str(e)}")
        
        return state


qa_agent = QAAgent()
