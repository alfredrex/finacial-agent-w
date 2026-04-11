import os
import json
from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class VisualizationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="VisualizationAgent",
            description="负责金融数据可视化，生成K线图、趋势图、对比图、表格等",
            tool_categories=[
                ToolCategory.KNOWLEDGE
            ]
        )
        self.max_iterations = 3
        
        self.skill_template = self._load_skill_template()
        self.reference_template = self._load_reference_template()
        
        self.visualization_prompt = """你是 {name}，{description}

【当前任务】数据可视化 - 将数据转换为专业图表

{skill_template}

【分析方法参考】:
{reference_template}

用户问题: {query}

【可用数据】:
{structured_data}

可用工具:
{tools}

输出格式:
Thought: 分析当前数据，决定生成什么类型的图表
Action: 工具名称(参数)

【重要规则】:
- 根据数据类型选择合适的图表
- **必须先调用图表生成工具（generate_kline_chart等），然后再调用finish()**
- 不要直接调用finish()，除非已经生成了图表
- 图表保存到 output/charts/ 目录
- 调用finish()时，content参数应包含图表路径信息

【示例】:
用户问: "茅台K线图"
Thought: 用户需要茅台K线图，我有茅台的历史数据，应该调用generate_kline_chart工具
Action: generate_kline_chart(symbol=600519, days=60)

Observation: K线图已生成: output/charts/kline_600519_20260410_123456.png

Thought: K线图已成功生成，现在可以调用finish输出结果
Action: finish(content=K线图已生成，路径: output/charts/kline_600519_20260410_123456.png)"""

    def _load_skill_template(self) -> str:
        skill_path = os.path.join(os.path.dirname(__file__), "..", "skills", "visualization_skill", "SKILL.md")
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    
    def _load_reference_template(self) -> str:
        ref_path = os.path.join(os.path.dirname(__file__), "..", "skills", "visualization_skill", "references", "financial_charts.md")
        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""

    def _get_tools_description(self) -> str:
        """重写工具描述，返回可视化工具"""
        return """- generate_kline_chart: 生成K线图（蜡烛图），参数: symbol(股票代码), days(天数,默认60)
- generate_trend_chart: 生成趋势图（折线图），参数: data(数据字典，包含dates/values/title/ylabel)
- generate_comparison_chart: 生成对比图（柱状图），参数: data(数据字典，包含labels/values/title)
- generate_table: 生成表格，参数: data(数据列表), title(表格标题)
- finish: 完成可视化任务，参数: content(输出内容)"""

    def _get_react_prompt(self) -> str:
        return self.visualization_prompt.format(
            name=self.name,
            description=self.description,
            tools=self._get_tools_description(),
            skill_template=self.skill_template[:2000] if self.skill_template else "",
            reference_template=self.reference_template[:2000] if self.reference_template else "",
            query="",
            structured_data=""
        )

    def _format_data_for_visualization(self, state: AgentState) -> str:
        collected_data = state.get("collected_data", [])
        analysis_results = state.get("analysis_results", [])
        
        def _format(data, max_len=300):
            if not data:
                return "暂无"
            if isinstance(data, list):
                return "\n".join([str(d)[:max_len] for d in data[:5]])
            return str(data)[:max_len]
        
        return f"""【已收集数据】:
{_format(collected_data)}

【分析结果】:
{_format(analysis_results)}"""

    async def process(self, state: AgentState) -> AgentState:
        print(f"[DEBUG] VisualizationAgent.process() 开始执行")
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_more_agent"] = None
        state["need_user_input"] = None
        
        self._log_message(state, "开始数据可视化...")
        print(f"[DEBUG] VisualizationAgent: 准备格式化数据")
        
        structured_data = self._format_data_for_visualization(state)
        print(f"[DEBUG] VisualizationAgent: 数据格式化完成，长度: {len(structured_data)}")
        
        visualization_prompt = self.visualization_prompt.format(
            name=self.name,
            description=self.description,
            tools=self._get_tools_description(),
            skill_template=self.skill_template[:2000] if self.skill_template else "",
            reference_template=self.reference_template[:2000] if self.reference_template else "",
            query=state.get("query", ""),
            structured_data=structured_data
        )
        
        state["_visualization_prompt"] = visualization_prompt
        print(f"[DEBUG] VisualizationAgent: 准备进入react循环")
        
        state = await self._visualization_react_loop(state)
        print(f"[DEBUG] VisualizationAgent: react循环结束，charts数量: {len(state.get('charts', []))}")
        
        state["visualization_done"] = True
        state["is_finished"] = True
        self._log_message(state, "数据可视化完成")
        
        return state

    async def _visualization_react_loop(self, state: AgentState) -> AgentState:
        import re
        iteration = state.get("agent_iteration", 0)
        if "iteration_logs" not in state:
            state["iteration_logs"] = []
        
        visualization_prompt = state.get("_visualization_prompt", "")
        print(f"[DEBUG] _visualization_react_loop: 开始，max_iterations={self.max_iterations}")
        
        while iteration < self.max_iterations:
            iteration += 1
            state["agent_iteration"] = iteration
            print(f"[DEBUG] _visualization_react_loop: 迭代 {iteration}/{self.max_iterations}")
            
            try:
                think_result = await self._visualization_think(state, visualization_prompt)
                state["thought"] = think_result["thought"]
                state["action"] = think_result["action"]
                
                print(f"[DEBUG] 思考: {think_result['thought'][:100]}")
                print(f"[DEBUG] 行动: {think_result['action'][:100]}")
                self._log_message(state, f"思考: {think_result['thought']}")
                
                parsed = self.parse_action(think_result["action"])
                tool_name = parsed["tool"]
                params = parsed["params"]
                
                print(f"[DEBUG] 解析工具: {tool_name}, 参数: {params}")
                
                log_entry = {
                    "iteration": iteration,
                    "thought": think_result["thought"],
                    "action": think_result["action"],
                    "observation": None
                }
                
                if tool_name == "finish":
                    print(f"[DEBUG] 调用finish工具")
                    state["answer"] = params.get("content", "可视化完成")
                    state["is_finished"] = True
                    state["observation"] = None
                    
                    self._log_message(state, "可视化完成")
                    state["iteration_logs"].append(log_entry)
                    break
                
                elif tool_name == "__batch__":
                    tools = parsed.get("tools", [])
                    print(f"[DEBUG] 批量执行 {len(tools)} 个工具")
                    observations = []
                    for t in tools:
                        t_name = t.get("tool", "")
                        t_params = t.get("params", {})
                        print(f"[DEBUG] 批量工具: {t_name}, 参数: {t_params}")
                        if t_name == "generate_trend_chart":
                            result = await self._generate_trend_chart(state, t_params)
                        elif t_name == "generate_comparison_chart":
                            result = await self._generate_comparison_chart(state, t_params)
                        elif t_name == "generate_kline_chart":
                            result = await self._generate_kline_chart(state, t_params)
                        elif t_name == "generate_table":
                            result = await self._generate_table(state, t_params)
                        else:
                            result = f"未知工具: {t_name}"
                        observations.append(result)
                    state["observation"] = "\n".join(observations)
                    log_entry["observation"] = state["observation"]
                
                elif tool_name == "generate_kline_chart":
                    print(f"[DEBUG] 调用generate_kline_chart工具")
                    self._log_message(state, f"生成K线图: {params}")
                    result = await self._generate_kline_chart(state, params)
                    state["observation"] = result
                    log_entry["observation"] = result
                
                elif tool_name == "generate_trend_chart":
                    print(f"[DEBUG] 调用generate_trend_chart工具")
                    self._log_message(state, f"生成趋势图: {params}")
                    result = await self._generate_trend_chart(state, params)
                    state["observation"] = result
                    log_entry["observation"] = result
                
                elif tool_name == "generate_comparison_chart":
                    print(f"[DEBUG] 调用generate_comparison_chart工具")
                    self._log_message(state, f"生成对比图: {params}")
                    result = await self._generate_comparison_chart(state, params)
                    state["observation"] = result
                    log_entry["observation"] = result
                
                elif tool_name == "generate_table":
                    print(f"[DEBUG] 调用generate_table工具")
                    self._log_message(state, f"生成表格: {params}")
                    result = await self._generate_table(state, params)
                    state["observation"] = result
                    log_entry["observation"] = result
                
                else:
                    self._log_message(state, f"行动: {tool_name}({params})")
                    result = await self._execute_single_tool(state, tool_name, params)
                    state["observation"] = str(result)[:1000]
                    log_entry["observation"] = state["observation"]
                
                state["iteration_logs"].append(log_entry)
                    
            except Exception as e:
                self._log_message(state, f"错误: {str(e)}")
                state["error"] = str(e)
                state["observation"] = f"执行出错: {str(e)}"
                
                if iteration >= 3:
                    state["answer"] = f"可视化执行中多次出错: {str(e)}"
                    state["is_finished"] = True
                    break
        
        if iteration >= self.max_iterations and not state.get("is_finished"):
            state["answer"] = "可视化完成（达到最大迭代次数）"
            state["is_finished"] = True
        
        return state

    async def _visualization_think(self, state: AgentState, system_prompt: str) -> dict:
        import re
        llm = self._get_llm()
        
        context_parts = []
        context_parts.append(f"用户问题: {state.get('query', '')}")
        
        iteration_logs = state.get("iteration_logs", [])
        if iteration_logs:
            history_parts = []
            for log in iteration_logs[-3:]:
                if log.get("thought"):
                    history_parts.append(f"Thought: {log['thought']}")
                if log.get("action"):
                    history_parts.append(f"Action: {log['action']}")
                if log.get("observation"):
                    history_parts.append(f"Observation: {log['observation'][:300]}")
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
                    "action": "finish(抱歉，网络连接出现问题)",
                    "error": error_msg
                }

    async def _generate_kline_chart(self, state: AgentState, params: dict) -> str:
        from src.skills.visualization_skill.scripts.chart_generator import generate_kline_chart
        
        symbol = params.get("symbol", params.get("arg", ""))
        days = params.get("days", 60)
        
        # 从collected_data中获取K线数据
        collected_data = state.get("collected_data", [])
        kline_data = None
        
        print(f"[DEBUG] _generate_kline_chart: symbol={symbol}, days={days}")
        print(f"[DEBUG] collected_data长度: {len(collected_data)}")
        
        # collected_data可能直接是K线数据列表
        if collected_data and isinstance(collected_data[0], dict):
            # 检查是否包含K线数据字段
            if "date" in collected_data[0] and "open" in collected_data[0]:
                kline_data = collected_data
                print(f"[DEBUG] 找到K线数据，长度: {len(kline_data)}")
        
        try:
            image_path = generate_kline_chart(symbol=symbol, days=days, data=kline_data)
            
            print(f"[DEBUG] 图片生成成功: {image_path}")
            
            if "charts" not in state:
                state["charts"] = []
            state["charts"].append({
                "type": "kline",
                "path": image_path,
                "symbol": symbol
            })
            
            return f"K线图已生成: {image_path}"
        except Exception as e:
            print(f"[DEBUG] 生成K线图失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"生成K线图失败: {str(e)}"

    async def _generate_trend_chart(self, state: AgentState, params: dict) -> str:
        print(f"[DEBUG] _generate_trend_chart 开始执行，params: {params}")
        try:
            from src.skills.visualization_skill.scripts.chart_generator import generate_trend_chart
            
            data = params.get("data", {})
            print(f"[DEBUG] 提取的data参数: {data}")
            
            if not data:
                data = {
                    "dates": params.get("dates", []),
                    "values": params.get("values", []),
                    "title": params.get("title", "趋势图"),
                    "ylabel": params.get("ylabel", "值")
                }
                print(f"[DEBUG] 构造的data: {data}")
            
            print(f"[DEBUG] 准备调用generate_trend_chart...")
            image_path = generate_trend_chart(data)
            print(f"[DEBUG] generate_trend_chart返回: {image_path}")
            
            if "charts" not in state:
                state["charts"] = []
            state["charts"].append({
                "type": "trend",
                "path": image_path
            })
            print(f"[DEBUG] charts已更新，数量: {len(state['charts'])}")
            
            return f"趋势图已生成: {image_path}"
        except Exception as e:
            print(f"[DEBUG] 生成趋势图失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return f"生成趋势图失败: {str(e)}"

    async def _generate_comparison_chart(self, state: AgentState, params: dict) -> str:
        from src.skills.visualization_skill.scripts.chart_generator import generate_comparison_chart
        
        data = params.get("data", {})
        if not data:
            data = {
                "categories": params.get("categories", []),
                "series": params.get("series", {}),
                "title": params.get("title", "对比图"),
                "ylabel": params.get("ylabel", "值")
            }
        
        try:
            image_path = generate_comparison_chart(data)
            
            if "charts" not in state:
                state["charts"] = []
            state["charts"].append({
                "type": "comparison",
                "path": image_path
            })
            
            return f"对比图已生成: {image_path}"
        except Exception as e:
            return f"生成对比图失败: {str(e)}"

    async def _generate_table(self, state: AgentState, params: dict) -> str:
        from src.skills.visualization_skill.scripts.chart_generator import generate_table
        
        data = params.get("data", params.get("arg", []))
        title = params.get("title", "数据表格")
        
        try:
            table_md = generate_table(data, title)
            
            if "tables" not in state:
                state["tables"] = []
            state["tables"].append({
                "type": "table",
                "content": table_md,
                "title": title
            })
            
            return f"表格已生成:\n{table_md[:500]}"
        except Exception as e:
            return f"生成表格失败: {str(e)}"


visualization_agent = VisualizationAgent()

from src.tools.registry import tool_registry
visualization_agent.set_tool_registry(tool_registry)
