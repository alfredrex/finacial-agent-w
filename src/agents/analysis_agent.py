import os
import json
from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class AnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="AnalysisAgent",
            description="负责金融指标计算和分析，包括技术分析、趋势判断、风险评估、深度分析等",
            tool_categories=[
                ToolCategory.ANALYSIS,
                ToolCategory.DATA_STOCK,
                ToolCategory.KNOWLEDGE
            ]
        )
        self.max_iterations = 10
        
        self.indicator_calculation_prompt = """你是 {name}，{description}

【当前任务】指标计算 - 使用工具获取数据并进行技术分析

可用工具:
{tools}

【重要】数据优先级:
1. rag_context: 向量库检索结果（优先使用，如果有就不用调用工具）
2. collected_data: 已收集的数据（优先使用）
3. 工具调用: 如果以上都没有，再调用工具

输出格式:
Thought: 分析当前情况，决定下一步行动
Action: 工具名称(参数)  [可以一次列出多个工具，用逗号分隔]

【重要】批量调用支持:
- 可以一次输出多个工具调用，格式: Action: tool1(params), tool2(params), tool3(params)
- 系统会批量执行所有工具，然后返回结果

【分析能力】:
- comprehensive_analysis(symbol): 综合技术分析（MA、MACD、RSI、趋势判断）
- get_stock_realtime(symbol): 获取实时行情
- get_stock_history(symbol, days): 获取历史K线
- get_market_index(): 获取市场指数
- search_knowledge(query, k): 查询知识库

【数据不足时的处理】:
如果需要更多数据（如新闻、公司信息），输出:
NEED_MORE: DataAgent
missing_data: ["新闻", "公司信息"]

【分析对象不支持时的处理】:
如果分析对象不在能力范围内（港股、美股等），输出:
ANALYSIS_UNAVAILABLE: 港股/美股/期货/外汇/加密货币

示例 - 批量调用:
Thought: 用户需要分析茅台，需要获取实时行情和历史K线进行技术分析
Action: get_stock_realtime(600519), get_stock_history(600519, 60)
Observation: [批量执行结果]
Thought: 已获取数据，进行综合技术分析
Action: comprehensive_analysis(600519)
Observation: {{...}}
Thought: 分析完成
Action: finish(分析结果)

【重要规则】:
- 尽量一次列出所有需要的工具，减少交互次数
- 优先使用已有数据
- 分析完成后调用 finish() 输出结论"""

        self.deep_analysis_skill = self._load_skill_template("skill_deep_analysis")
        
        self.reference_map = {
            "基本面": "reference_basic_fundamental",
            "财务": "reference_financial_metrics",
            "技术面": "reference_technical_analysis",
            "新闻": "reference_event_driven",
            "量价": "reference_price_volume",
            "同业": "reference_peer_comparison",
            "趋势": "reference_trend_cycle",
            "风险": "reference_risk_quantify"
        }

    def _get_react_prompt(self) -> str:
        return self.indicator_calculation_prompt.format(
            name=self.name,
            description=self.description,
            tools=self._get_tools_description()
        )
    
    def _load_skill_template(self, template_name: str) -> str:
        template_path = os.path.join(os.path.dirname(__file__), "..", "skills", "analysis_skill", f"{template_name}.md")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    
    def _check_deep_analysis_prerequisites(self, state: AgentState) -> bool:
        data_collection_finished = state.get("data_collection_finished", False)
        analysis_finished = state.get("analysis_finished", False)
        
        if not data_collection_finished:
            self._log_message(state, "深度分析前置条件不满足: data_collection_finished=False")
            return False
        
        if not analysis_finished:
            self._log_message(state, "深度分析前置条件不满足: analysis_finished=False")
            return False
        
        self._log_message(state, "深度分析前置条件满足: data_collection_finished=True, analysis_finished=True")
        return True

    def _get_deep_analysis_prompt(self, state: AgentState, references: str) -> str:
        rag_context = state.get("rag_context", [])
        collected_data = state.get("collected_data", [])
        analysis_results = state.get("analysis_results", [])
        memory_context = state.get("memory_context", [])
        conversation_history = state.get("conversation_history", [])
        
        def _format_data(data, max_len=500):
            if not data:
                return "暂无"
            if isinstance(data, list):
                return "\n".join([str(d)[:max_len] for d in data[:5]])
            return str(data)[:max_len]
        
        structured_data = f"""【向量库检索结果】:
{_format_data(rag_context)}

【已收集数据】:
{_format_data(collected_data)}

【分析结果】:
{_format_data(analysis_results)}

【历史记忆】:
{_format_data(memory_context)}

【对话历史】:
{_format_data(conversation_history, 300)}"""
        
        return f"""你是 {self.name}，{self.description}

【当前任务】深度分析 - 综合所有数据进行深度分析

{self.deep_analysis_skill[:3000] if self.deep_analysis_skill else ""}

【分析方法参考】:
{references}

用户问题: {state.get('query', '')}

【全部可用数据】:
{structured_data[:5000]}

可用工具:
{self._get_tools_description()}

输出格式:
Thought: 分析当前情况，决定下一步行动
Action: 工具名称(参数)

【重要规则】:
- 可以调用 search_knowledge 查询知识库获取补充信息
- 综合所有数据按照分析方法框架进行深度分析
- 分析完成后调用 finish() 输出结论"""

    async def _select_analysis_types(self, state: AgentState) -> list:
        llm = self._get_llm()
        
        rag_context = state.get("rag_context", [])
        collected_data = state.get("collected_data", [])
        analysis_results = state.get("analysis_results", [])
        
        def _format_data(data, max_len=300):
            if not data:
                return "暂无"
            if isinstance(data, list):
                return "\n".join([str(d)[:max_len] for d in data[:3]])
            return str(data)[:max_len]
        
        structured_data = f"""【向量库检索结果】:
{_format_data(rag_context)}

【已收集数据】:
{_format_data(collected_data)}

【分析结果】:
{_format_data(analysis_results)}"""
        
        analysis_type_prompt = f"""基于以下数据，判断用户需要哪种分析方法：

用户问题: {state.get('query', '')}

已有数据:
{structured_data[:2000]}

可选分析方法:
1. 基本面分析 - 适合公司深度研究
2. 财务分析 - 适合财务指标解读
3. 技术面分析 - 适合走势判断
4. 新闻分析 - 适合事件解读
5. 量价分析 - 适合趋势确认
6. 同业对比 - 适合竞争力评估
7. 趋势周期 - 适合长期判断
8. 风险量化 - 适合风险评估

请输出一个JSON，包含:
- analysis_types: 数组，选择的分析方法（可以多个）
- reason: 选择理由

```json
{{"analysis_types": ["方法1", "方法2"], "reason": "理由"}}
```"""
        
        messages = [
            self._create_system_message("你是金融分析专家，擅长选择合适的分析方法。"),
            self._create_human_message(analysis_type_prompt)
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            choice = json.loads(content.strip())
            analysis_types = choice.get("analysis_types", ["基本面"])
        except Exception:
            analysis_types = ["基本面"]
        
        self._log_message(state, f"选择分析方法: {analysis_types}")
        return analysis_types

    def _load_references(self, analysis_types: list) -> str:
        references = []
        for at in analysis_types:
            ref_name = self.reference_map.get(at, "reference_basic_fundamental")
            ref_content = self._load_skill_template(ref_name)
            if ref_content:
                references.append(f"### {at}分析参考\n{ref_content}")
        
        return "\n\n---\n\n".join(references)

    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        state["need_user_input"] = None
        state["analysis_results"] = state.get("analysis_results", [])
        
        indicator_calculation_done = state.get("indicator_calculation_done", False)
        needs_deep_analysis = state.get("needs_deep_analysis", False)
        
        if not indicator_calculation_done:
            return await self._execute_indicator_calculation(state)
        elif needs_deep_analysis and not state.get("deep_analysis_done", False):
            return await self._execute_deep_analysis(state)
        else:
            state["is_finished"] = True
            return state

    async def _execute_indicator_calculation(self, state: AgentState) -> AgentState:
        self._log_message(state, "开始指标计算...")
        
        rag_context = state.get("rag_context", [])
        collected_data = state.get("collected_data", [])
        data_unavailable = state.get("data_unavailable", [])
        
        if rag_context:
            self._log_message(state, f"向量库已有 {len(rag_context)} 条相关内容")
        if collected_data:
            self._log_message(state, f"已收集数据: {len(collected_data)} 条")
        if data_unavailable:
            self._log_message(state, f"数据不可获取: {data_unavailable}")
        
        state = await self.react_loop(state)
        
        action_str = state.get("action", "") or state.get("thought", "") or ""
        special_parsed = self.parse_special_output(action_str)
        
        if special_parsed.get("need_more_agent"):
            state["need_more_agent"] = special_parsed["need_more_agent"]
            state["thought"] = f"需要返回 {special_parsed['need_more_agent']}"
            state["is_finished"] = False
            self._log_message(state, f"请求返回: {special_parsed['need_more_agent']}")
            return state
        
        if special_parsed.get("analysis_unavailable"):
            state["analysis_unavailable"] = special_parsed["analysis_unavailable"]
            self._log_message(state, f"分析不可获取: {special_parsed['analysis_unavailable']}")
        
        state["indicator_calculation_done"] = True
        state["analysis_finished"] = True
        self._log_message(state, "指标计算完成")
        
        return state

    async def _execute_deep_analysis(self, state: AgentState) -> AgentState:
        self._log_message(state, "开始深度分析...")
        
        if not self._check_deep_analysis_prerequisites(state):
            self._log_message(state, "深度分析前置条件不满足，跳过")
            state["is_finished"] = True
            return state
        
        analysis_types = await self._select_analysis_types(state)
        references = self._load_references(analysis_types)
        
        state["_deep_analysis_references"] = references
        state["_deep_analysis_prompt"] = self._get_deep_analysis_prompt(state, references)
        
        state = await self._deep_analysis_react_loop(state)
        
        state["deep_analysis_done"] = True
        state["is_finished"] = True
        self._log_message(state, "深度分析完成")
        
        return state

    async def _deep_analysis_react_loop(self, state: AgentState) -> AgentState:
        iteration = state.get("agent_iteration", 0)
        if "iteration_logs" not in state:
            state["iteration_logs"] = []
        
        deep_analysis_prompt = state.get("_deep_analysis_prompt", "")
        
        while iteration < self.max_iterations:
            iteration += 1
            state["agent_iteration"] = iteration
            
            try:
                think_result = await self._deep_analysis_think(state, deep_analysis_prompt)
                state["thought"] = think_result["thought"]
                state["action"] = think_result["action"]
                
                self._log_message(state, f"思考: {think_result['thought']}")
                
                parsed = self.parse_action(think_result["action"])
                tool_name = parsed["tool"]
                params = parsed["params"]
                
                log_entry = {
                    "iteration": iteration,
                    "thought": think_result["thought"],
                    "action": think_result["action"],
                    "observation": None
                }
                
                if tool_name == "finish":
                    state["answer"] = params.get("content", "任务完成")
                    state["is_finished"] = True
                    state["observation"] = None
                    
                    state["analysis_results"].append({
                        "type": "deep_analysis",
                        "content": state["answer"]
                    })
                    
                    self._log_message(state, "深度分析完成")
                    state["iteration_logs"].append(log_entry)
                    break
                
                elif tool_name == "__batch__":
                    tools = parsed.get("tools", [])
                    self._log_message(state, f"批量行动: {len(tools)} 个工具")
                    observations = await self._execute_batch_tools(state, tools)
                    state["observation"] = "\n".join(observations)
                    self._log_message(state, f"批量观察: {state['observation'][:300]}")
                    log_entry["observation"] = state["observation"]
                
                elif tool_name == "unknown":
                    state["observation"] = f"未知工具: {parsed.get('raw', '')}"
                    self._log_message(state, f"观察: {state['observation']}")
                    log_entry["observation"] = state["observation"]
                
                else:
                    self._log_message(state, f"行动: {tool_name}({params})")
                    result = await self._execute_single_tool(state, tool_name, params)
                    
                    if isinstance(result, str):
                        state["observation"] = result[:1000]
                    elif isinstance(result, dict):
                        state["observation"] = str(result)[:1000]
                        self._add_to_collected_data(state, result)
                    elif isinstance(result, list):
                        state["observation"] = str(result)[:1000]
                        self._add_to_collected_data(state, result)
                    else:
                        state["observation"] = str(result)[:1000]
                    
                    self._log_message(state, f"观察: {state['observation'][:200]}")
                    log_entry["observation"] = state["observation"]
                
                state["iteration_logs"].append(log_entry)
                    
            except Exception as e:
                self._log_message(state, f"错误: {str(e)}")
                state["error"] = str(e)
                state["observation"] = f"执行出错: {str(e)}"
                
                if iteration >= 3:
                    state["answer"] = f"深度分析执行中多次出错: {str(e)}"
                    state["is_finished"] = True
                    break
        
        if iteration >= self.max_iterations and not state.get("is_finished"):
            state["answer"] = "深度分析完成（达到最大迭代次数）"
            state["is_finished"] = True
            state["analysis_results"].append({
                "type": "deep_analysis",
                "content": state["answer"]
            })
        
        return state

    async def _deep_analysis_think(self, state: AgentState, system_prompt: str) -> dict:
        import re
        llm = self._get_llm()
        
        context_parts = []
        context_parts.append(f"用户问题: {state.get('query', '')}")
        
        iteration_logs = state.get("iteration_logs", [])
        if iteration_logs:
            history_parts = []
            for log in iteration_logs[-5:]:
                if log.get("thought"):
                    history_parts.append(f"Thought: {log['thought']}")
                if log.get("action"):
                    history_parts.append(f"Action: {log['action']}")
                if log.get("observation"):
                    history_parts.append(f"Observation: {log['observation'][:500]}")
            if history_parts:
                context_parts.append(f"历史推理记录:\n" + "\n".join(history_parts))
        
        context_parts.append(f"当前迭代: {state.get('agent_iteration', 0)}/{self.max_iterations}")
        
        messages = [
            self._create_system_message(system_prompt),
            self._create_human_message("\n\n".join(context_parts))
        ]
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await llm.ainvoke(messages)
                self._update_token_usage(state, response)
                
                content = response.content
                
                thought_match = re.search(r'Thought:\s*(.+?)(?=\n\s*Action:|Action:|$)', content, re.DOTALL)
                action_match = re.search(r'Action:\s*(.+)$', content, re.DOTALL)
                
                thought = thought_match.group(1).strip() if thought_match else "分析中..."
                action = action_match.group(1).strip() if action_match else "finish(继续)"
                
                return {
                    "thought": thought,
                    "action": action,
                    "raw_response": content
                }
                
            except Exception as e:
                error_msg = str(e)
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                return {
                    "thought": f"思考过程出错: {error_msg}",
                    "action": "finish(抱歉，网络连接出现问题，请稍后重试)",
                    "error": error_msg
                }


analysis_agent = AnalysisAgent()

from src.tools.registry import tool_registry
analysis_agent.set_tool_registry(tool_registry)
