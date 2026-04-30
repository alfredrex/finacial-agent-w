from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings


class DispatcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="DispatcherAgent",
            description="任务调度Agent，负责查询改写、意图识别并选择最合适的专业Agent来处理",
            tool_categories=[]
        )
        self._agents: Dict[str, Dict[str, Any]] = {}
        self.max_iterations = 1
        
        self.rewrite_prompt = """你是一个查询改写专家。根据对话历史，将用户的当前问题改写为完整、独立的问题。

对话历史:
{history}

当前问题: {query}

【改写规则】:
1. 将代词（它、这个、那个）替换为具体指代对象
2. 补充省略的信息
3. 如果问题已经完整，保持原样
4. 只输出改写后的问题，不要其他内容

【示例】:
历史: Q: "茅台股价多少" A: "1445元"
当前: "分析它"
改写: "分析茅台"

历史: Q: "比亚迪怎么样" A: "..."
当前: "继续分析"
改写: "继续分析比亚迪"

历史: 无
当前: "茅台股价多少"
改写: "茅台股价多少"
"""
        
        self.dispatch_prompt = """你是 {name}，{description}

你的任务是全局调度，决定整个任务流程：
1. 分析用户问题的意图
2. 判断是否需要文件处理（上传文件、存储知识）
3. 判断是否需要记忆检索（查找历史信息）
4. 选择第一个执行的 Agent
5. 判断是否需要数据收集
6. 判断是否需要数据分析（指标计算）
7. 判断是否需要深度分析（综合分析、投资建议等）
8. 判断是否需要可视化（生成图表、K线图、趋势图等）
9. 决定最终输出类型和模板参数

可用 Agent 列表:
{agents_desc}

【执行优先级】:
1. FileProcessingAgent (最高): 有文件上传时，先处理文件存入向量库
2. MemoryAgent: 需要历史上下文时，先检索记忆
3. 其他Agent: 正常业务流程

【输出类型判断】首先判断用户需要哪种输出:
- QA问答: 用户询问问题，需要回答
- Report报告: 用户需要生成结构化报告

【意图识别】请分析以下维度:
- needs_file_processing: 是否需要文件处理（有上传文件、需要存储知识）
- needs_memory_retrieval: 是否需要记忆检索（用户提到"之前"、"历史"、"上次"、需要上下文）
- selected_agent: 第一个执行的 Agent
- needs_coordination: 是否需要协调器介入（任务涉及多个Agent协作或多步复杂流程时设为true）
- needs_data_collection: 整体任务是否需要数据收集
- needs_analysis: 整体任务是否需要数据分析（指标计算）
- needs_deep_analysis: 整体任务是否需要深度分析（综合分析、投资建议、风险评估等）
- needs_visualization: 整体任务是否需要可视化（用户要求画图、K线图、趋势图、对比图、表格等）
- output_type: 输出类型，"qa" 或 "report"

【可视化触发词】当用户查询包含以下关键词时，需要设置 needs_visualization=true:
1. 图表类: "画图"、"图表"、"图形"、"可视化"、"展示图"、"显示图"
2. K线图: "K线图"、"k线图"、"蜡烛图"、"股票走势图"、"股价图"、"行情图"
3. 趋势图: "趋势图"、"折线图"、"走势图"、"变化图"、"波动图"
4. 对比图: "对比图"、"柱状图"、"条形图"、"比较图"、"分布图"
5. 表格: "表格"、"数据表"、"列表"、"明细表"
6. 其他: "饼图"、"散点图"、"热力图"、"雷达图"、"面积图"
7. 报告类: "深度报告"、"分析报告"、"研究报告"、"投资报告"、"投研报告" - 复杂报告默认需要可视化图表

【QA参数】(仅当 output_type="qa" 时设置):
- is_deep_qa: 是否深度问答（详细解释、多维度分析）

【Report参数】(仅当 output_type="report" 时设置):
- report_type: "简单"(简短报告) 或 "复杂"(深度报告)
- report_domain: "公司"(个股分析)、"行业"(行业分析)、"策略"(投资策略)

【输出格式】必须是有效的JSON:
```json
{{
    "thought": "分析过程",
    "needs_file_processing": true/false,
    "needs_memory_retrieval": true/false,
    "selected_agent": "Agent名称",
    "needs_data_collection": true/false,
    "needs_analysis": true/false,
    "needs_deep_analysis": true/false,
    "needs_visualization": true/false,
    "needs_coordination": true/false,
    "output_type": "qa"/"report",
    "is_deep_qa": true/false,
    "report_type": "简单"/"复杂"/null,
    "report_domain": "公司"/"行业"/"策略"/null
}}
```

【示例1】用户问: "茅台股价多少"
→ QA路径，简单问答，不需要记忆检索
```json
{{
    "thought": "用户询问实时股价，简单问答即可，不需要历史上下文",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": false,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例2】用户问: "画茅台K线图"
→ QA路径，需要可视化
```json
{{
    "thought": "用户需要K线图，需要获取数据后生成可视化图表",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": true,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例2.1】用户问: "展示茅台近一个月的趋势图"
→ QA路径，需要可视化
```json
{{
    "thought": "用户需要趋势图，需要获取历史数据后生成趋势图表",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": true,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例2.2】用户问: "对比茅台和五粮液的股价走势"
→ QA路径，需要可视化
```json
{{
    "thought": "用户需要对比图，需要获取两支股票数据后生成对比图表",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": true,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例2.3】用户问: "显示茅台财务数据表格"
→ QA路径，需要可视化
```json
{{
    "thought": "用户需要表格，需要获取财务数据后生成表格",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": true,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例3】用户问: "之前分析过茅台吗？"
→ QA路径，需要记忆检索
```json
{{
    "thought": "用户询问历史分析记录，需要检索记忆",
    "needs_file_processing": false,
    "needs_memory_retrieval": true,
    "selected_agent": "DataAgent",
    "needs_data_collection": false,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "needs_visualization": false,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例4】用户问: "上传这个文件并分析"
→ 有文件上传，先处理文件
```json
{{
    "thought": "用户上传文件，需要先处理文件存入向量库",
    "needs_file_processing": true,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": true,
    "needs_deep_analysis": false,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例4】用户问: "分析茅台投资价值"
→ Report路径，复杂公司报告，需要深度分析和可视化
```json
{{
    "thought": "用户需要投资价值分析，需要数据收集、指标计算、深度分析和可视化图表",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": true,
    "needs_deep_analysis": true,
    "needs_visualization": true,
    "output_type": "report",
    "is_deep_qa": false,
    "report_type": "复杂",
    "report_domain": "公司"
}}
```

【示例4.1】用户问: "茅台深度报告"
→ Report路径，复杂公司报告，需要深度分析和可视化
```json
{{
    "thought": "用户需要深度报告，需要数据收集、指标计算、深度分析和可视化图表（趋势图、财务数据表格等）",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "DataAgent",
    "needs_data_collection": true,
    "needs_analysis": true,
    "needs_deep_analysis": true,
    "needs_visualization": true,
    "output_type": "report",
    "is_deep_qa": false,
    "report_type": "复杂",
    "report_domain": "公司"
}}
```

【示例4.2】用户问: "全面分析白酒板块，对比茅台、五粮液、汾酒的财务数据和估值，生成深度报告"
→ 多步复杂任务，需要多个Agent协作
```json
{{
    "thought": "多股票多维度分析和对比报告，需要协调器统筹",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "CoordinatorAgent",
    "needs_data_collection": true,
    "needs_analysis": true,
    "needs_deep_analysis": true,
    "needs_visualization": true,
    "needs_coordination": true,
    "output_type": "report",
    "is_deep_qa": false,
    "report_type": "复杂",
    "report_domain": "行业"
}}
```

【示例5】用户问: "上次茅台分析结果怎么样？"
→ 需要记忆检索
```json
{{
    "thought": "用户询问上次分析结果，需要检索任务记忆",
    "needs_file_processing": false,
    "needs_memory_retrieval": true,
    "selected_agent": "QAAgent",
    "needs_data_collection": false,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【示例6】用户问: "数据库情况如何"
→ QA路径，简单问答
```json
{{
    "thought": "用户询问知识库统计，简单回答",
    "needs_file_processing": false,
    "needs_memory_retrieval": false,
    "selected_agent": "FileProcessingAgent",
    "needs_data_collection": false,
    "needs_analysis": false,
    "needs_deep_analysis": false,
    "output_type": "qa",
    "is_deep_qa": false,
    "report_type": null,
    "report_domain": null
}}
```

【重要规则】:
1. 有文件上传时，needs_file_processing 必须为 true，selected_agent 必须是 FileProcessingAgent
2. 用户提到"之前"、"历史"、"上次"、"之前分析过"等词时，needs_memory_retrieval 为 true
3. needs_memory_retrieval 为 true 时，会先走 MemoryAgent 检索记忆
4. needs_deep_analysis 仅在需要综合分析、投资建议、风险评估时设为 true
5. output_type 决定最终走 QAAgent 还是 ReportAgent
6. QA路径: 只设置 is_deep_qa，report_type/report_domain 为 null
7. Report路径: 只设置 report_type/report_domain，is_deep_qa 为 false
8. 后续路由由调度系统根据完成状态决定
9. needs_coordination 设为 true 的场景: 多股票/多标的对比分析、需多方数据+多维度分析的复杂任务
10. 如果用户问题不明确，输出: NEED_USER: 问题内容"""
    
    def register_agent(self, name: str, description: str, capabilities: List[str]):
        self._agents[name] = {
            "name": name,
            "description": description,
            "capabilities": capabilities
        }
    
    def _get_agents_description(self) -> str:
        lines = []
        for name, info in self._agents.items():
            caps = ", ".join(info["capabilities"])
            lines.append(f"- {name}: {info['description']} (能力: {caps})")
        return "\n".join(lines)
    
    def _get_react_prompt(self) -> str:
        return self.dispatch_prompt.format(
            name=self.name,
            description=self.description,
            agents_desc=self._get_agents_description()
        )
    
    def _parse_json_response(self, content: str) -> dict:
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        selected_agent = "QAAgent"
        for name in self._agents.keys():
            if name.lower() in content.lower():
                selected_agent = name
                break
        
        return {
            "thought": "解析失败，使用默认值",
            "selected_agent": selected_agent
        }
    
    async def _rewrite_query(self, state: AgentState) -> str:
        """查询改写：将多轮对话中的代词指代改写为完整问题"""
        query = state.get("query", "")
        history = state.get("conversation_history", [])
        
        if not history:
            return query
        
        history_text = []
        for h in history[-3:]:
            history_text.append(f"Q: {h.get('question', '')}")
            history_text.append(f"A: {h.get('answer', '')[:200]}...")
        
        prompt = self.rewrite_prompt.format(
            history="\n".join(history_text),
            query=query
        )
        
        llm = self._get_llm()
        messages = [
            self._create_system_message("你是一个查询改写专家。"),
            self._create_human_message(prompt)
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            rewritten = response.content.strip()
            if rewritten and len(rewritten) > 0:
                self._log_message(state, f"查询改写: '{query}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            self._log_message(state, f"查询改写失败: {str(e)}")
        
        return query
    
    async def think(self, state: AgentState) -> Dict[str, Any]:
        llm = self._get_llm()
        
        query = state.get("rewritten_query", state.get("query", ""))
        context_parts = [f"用户问题: {query}"]
        
        user_memory_summary = state.get("user_memory_summary", "")
        if user_memory_summary and user_memory_summary != "暂无用户偏好信息":
            context_parts.append(f"\n【用户偏好记忆】:\n{user_memory_summary}")
        
        if state.get("file_paths"):
            context_parts.append(f"上传文件: {state['file_paths']}")
        
        messages = [
            self._create_system_message(self._get_react_prompt()),
            self._create_human_message("\n".join(context_parts))
        ]
        
        try:
            response = await llm.ainvoke(messages)
            self._update_token_usage(response, state)
            
            print(f"\n[DEBUG] Dispatcher LLM 原始响应:\n{response.content}\n")
            
            parsed = self._parse_json_response(response.content)
            
            print(f"[DEBUG] 解析后的 needs_visualization: {parsed.get('needs_visualization', False)}")
            
            return {
                "thought": parsed.get("thought", ""),
                "needs_file_processing": parsed.get("needs_file_processing", False),
                "needs_memory_retrieval": parsed.get("needs_memory_retrieval", False),
                "selected_agent": parsed.get("selected_agent", "QAAgent"),
                "needs_data_collection": parsed.get("needs_data_collection", False),
                "needs_analysis": parsed.get("needs_analysis", False),
                "needs_deep_analysis": parsed.get("needs_deep_analysis", False),
                "needs_visualization": parsed.get("needs_visualization", False),
                "needs_coordination": parsed.get("needs_coordination", False),
                "output_type": parsed.get("output_type", "qa"),
                "is_deep_qa": parsed.get("is_deep_qa", False),
                "report_type": parsed.get("report_type"),
                "report_domain": parsed.get("report_domain"),
                "raw_response": response.content
            }
            
        except Exception as e:
            # API出错时，使用基于关键词的fallback判断
            query_lower = query.lower()
            
            # 可视化关键词检测
            viz_keywords = ['k线', 'kline', '趋势图', '折线图', '走势图', '对比图', '柱状图', 
                           '画图', '图表', '可视化', '展示图', '显示图', '蜡烛图', '股价图',
                           '行情图', '饼图', '散点图', '热力图', '雷达图']
            needs_viz = any(kw in query_lower for kw in viz_keywords)
            
            # 数据收集关键词检测
            data_keywords = ['股价', '价格', '行情', '财务', '利润', '营收', '股东', '市值',
                            '市盈率', 'pe', 'pb', 'roe', '报告', '分析', '走势']
            needs_data = any(kw in query_lower for kw in data_keywords) or needs_viz
            
            # 报告关键词检测
            report_keywords = ['报告', '研究', '分析', '深度']
            is_report = any(kw in query_lower for kw in report_keywords)
            
            # 协调触发检测：多标的或多维度复杂任务
            needs_coordination = is_report and needs_data

            return {
                "thought": f"调度分析出错(使用关键词fallback): {str(e)}",
                "needs_file_processing": False,
                "needs_memory_retrieval": False,
                "selected_agent": "DataAgent" if needs_data else "QAAgent",
                "needs_data_collection": needs_data,
                "needs_analysis": needs_data,
                "needs_deep_analysis": is_report,
                "needs_visualization": needs_viz,
                "needs_coordination": needs_coordination,
                "output_type": "report" if is_report else "qa",
                "is_deep_qa": False,
                "report_type": "复杂" if is_report else None,
                "report_domain": "公司" if is_report else None,
                "error": str(e)
            }
    
    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["is_finished"] = False
        state["need_user_input"] = None
        state["need_more_agent"] = None
        state["needs_data_collection"] = False
        state["needs_analysis"] = False
        state["needs_deep_analysis"] = False
        state["deep_analysis_done"] = False
        state["data_collection_finished"] = False
        state["analysis_finished"] = False
        state["exception_info"] = None
        state["exception_handled"] = False
        state["output_type"] = "qa"
        state["report_type"] = None
        state["report_domain"] = None
        state["is_deep_qa"] = False
        state["needs_file_processing"] = False
        state["file_processing_done"] = False
        state["needs_coordination"] = False
        state["needs_memory_retrieval"] = False
        state["memory_retrieval_done"] = False
        state["memory_context"] = []
        state["memory_sources"] = []
        self._log_message(state, "开始调度分析...")
        
        rewritten_query = await self._rewrite_query(state)
        state["rewritten_query"] = rewritten_query
        
        think_result = await self.think(state)
        
        special_parsed = self.parse_special_output(think_result.get("raw_response", ""))
        
        if special_parsed["type"] == "need_user":
            state["need_user_input"] = special_parsed["need_user"]
            state["thought"] = f"需要用户输入: {special_parsed['need_user']}"
            state["action"] = "wait_for_user"
            state["is_finished"] = False
            self._log_message(state, f"需要用户输入: {special_parsed['need_user']}")
        else:
            state["thought"] = think_result["thought"]
            state["action"] = f"select_agent({think_result['selected_agent']})"
            state["selected_agent"] = think_result["selected_agent"]
            state["needs_file_processing"] = think_result.get("needs_file_processing", False)
            state["needs_memory_retrieval"] = think_result.get("needs_memory_retrieval", False)
            state["needs_data_collection"] = think_result.get("needs_data_collection", False)
            state["needs_analysis"] = think_result.get("needs_analysis", False)
            state["needs_deep_analysis"] = think_result.get("needs_deep_analysis", False)
            state["needs_visualization"] = think_result.get("needs_visualization", False)
            state["needs_coordination"] = think_result.get("needs_coordination", False)

            print(f"[DEBUG] state['needs_visualization'] = {state['needs_visualization']}")

            state["output_type"] = think_result.get("output_type", "qa")
            state["is_deep_qa"] = think_result.get("is_deep_qa", False)
            state["report_type"] = think_result.get("report_type")
            state["report_domain"] = think_result.get("report_domain")
            state["agent_visit_count"] = {}
            
            self._log_message(state, f"调度到: {state['selected_agent']}")
            self._log_message(state, f"全局规划 - 文件处理: {state['needs_file_processing']}, 记忆检索: {state['needs_memory_retrieval']}")
            self._log_message(state, f"全局规划 - 数据收集: {state['needs_data_collection']}, 分析: {state['needs_analysis']}, 深度分析: {state['needs_deep_analysis']}")
            self._log_message(state, f"全局规划 - 可视化: {state['needs_visualization']}")
            
            if state["output_type"] == "report":
                self._log_message(state, f"输出类型: Report - 报告类型: {state['report_type']}, 报告领域: {state['report_domain']}")
            else:
                self._log_message(state, f"输出类型: QA - 深度问答: {state['is_deep_qa']}")
            
            state["is_finished"] = True
        
        return state


dispatcher_agent = DispatcherAgent()
