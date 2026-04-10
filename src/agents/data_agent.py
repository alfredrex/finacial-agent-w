from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class DataAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="DataAgent",
            description="负责采集金融相关数据，包括股票行情、新闻资讯、公司信息、市场指数等",
            tool_categories=[
                ToolCategory.DATA_STOCK,
                ToolCategory.DATA_NEWS, 
                ToolCategory.DATA_COMPANY
            ]
        )
        self.max_iterations = 3
        
        self.data_system_prompt = """你是 {name}，{description}

可用工具:
{tools}

【重要】数据优先级:
1. rag_context: 向量库检索结果（优先使用，如果有就不用调用工具）
2. 工具调用: 如果 rag_context 没有相关内容，再调用工具收集数据

【数据能力范围】:
- 支持: A股股票(600519, 000001等)、A股新闻、A股公司信息、市场指数
- 不支持: 港股、美股、期货、外汇、加密货币

【数据收集范围】:
- 股票行情：get_stock_realtime, get_stock_history
- 新闻资讯：search_news
- 公司信息：get_company_info（公司概况、主营业务等）, get_top_shareholders（十大股东）
- 市场指数：get_market_index

输出格式:
Thought: 分析已经有什么数据，是否还需要收集更多数据
Action: 工具名称(参数)  [可以一次列出多个工具，用逗号分隔]

【重要】批量调用支持:
- 可以一次输出多个工具调用，格式: Action: tool1(params), tool2(params), tool3(params)
- 系统会批量执行所有工具，然后返回结果

【工作流程】:
1. 判断需要的数据是否在能力范围内
2. 如果在范围内，调用工具收集数据（尽量一次列出所有需要的工具）
3. 如果不在范围内，标记 DATA_UNAVAILABLE
4. 数据收集完成后，调用 finish() 结束

【工具失败处理】:
如果工具返回错误信息（如 "获取失败"、"不可用" 等）:
- 不要反复重试同一个失败的工具
- 在 finish() 时输出 DATA_UNAVAILABLE 标记失败的数据类型
- 示例: 
  Action: finish()
  DATA_UNAVAILABLE: 股东信息

【数据不可获取时的处理】:
如果用户请求的数据不在能力范围内，或工具多次失败，输出:
DATA_UNAVAILABLE: 数据类型
然后调用 finish() 结束

示例 - 批量调用:
Thought: 用户询问茅台股价和新闻，需要获取实时行情和相关新闻
Action: get_stock_realtime(600519), search_news(茅台)
Observation: [批量执行结果]
Thought: 已获取股价和新闻数据，任务完成
Action: finish()

示例 - 工具失败:
Thought: 用户询问茅台股东信息。尝试获取但工具返回错误
Action: get_top_shareholders(600519)
Observation: [{{'error': '获取股东信息失败'}}]
Thought: 工具返回错误，无法获取股东信息。标记数据不可获取并结束
Action: finish()
DATA_UNAVAILABLE: 股东信息

示例 - 数据不可获取:
Thought: 用户询问港股腾讯股价，但港股不在支持范围内
Action: finish()
DATA_UNAVAILABLE: 港股

【数据不足时的处理】:
如果收集的数据需要进一步分析处理，输出以下格式请求返回：
NEED_MORE: AnalysisAgent

【重要规则】:
- 尽量一次列出所有需要的工具，减少交互次数
- 数据收集完成后必须调用 finish()
- 如果工具返回错误，不要反复重试，直接标记 DATA_UNAVAILABLE
- 如果数据源报错，也调用 finish() 结束
- 不要尝试回答用户问题
- 港股代码格式: 0700.HK, 9988.HK 等
- 美股代码格式: AAPL, TSLA 等
- 如果缺少必要参数（如股票代码），输出:
  NEED_USER: 问题内容
  例如: NEED_USER: 请提供股票代码，例如 600519"""

    def _get_react_prompt(self) -> str:
        return self.data_system_prompt.format(
            name=self.name,
            description=self.description,
            tools=self._get_tools_description()
        )
    
    def _parse_response(self, response: str) -> dict:
        result = {
            "type": "normal",
            "content": response,
            "data_unavailable": [],
            "need_more_agent": None
        }
        
        if "DATA_UNAVAILABLE:" in response:
            lines = response.strip().split("\n")
            for line in lines:
                if line.startswith("DATA_UNAVAILABLE:"):
                    unavailable = line.replace("DATA_UNAVAILABLE:", "").strip()
                    result["data_unavailable"] = [x.strip() for x in unavailable.split("/")]
        
        if "NEED_MORE:" in response:
            lines = response.strip().split("\n")
            agent_name = None
            
            for line in lines:
                if line.startswith("NEED_MORE:"):
                    agent_name = line.replace("NEED_MORE:", "").strip()
            
            if agent_name:
                result["type"] = "need_more"
                result["need_more_agent"] = agent_name
        
        return result
    
    def _is_similar_unavailable(self, item1: str, item2: str) -> bool:
        """判断两个不可获取项是否相似"""
        item1_lower = item1.lower()
        item2_lower = item2.lower()
        
        if item1_lower == item2_lower:
            return True
        
        if item1_lower in item2_lower or item2_lower in item1_lower:
            return True
        
        similar_groups = [
            ["股东", "股东信息", "十大股东", "股东数据"],
            ["新闻", "新闻资讯", "新闻数据"],
            ["行情", "实时行情", "股价", "价格"],
            ["公司", "公司信息", "公司资料"],
            ["财务", "财务数据", "财务信息"],
            ["港股", "港股数据"],
            ["美股", "美股数据"],
        ]
        
        for group in similar_groups:
            if item1_lower in group and item2_lower in group:
                return True
        
        return False
    
    def _merge_unavailable(self, existing: list, new_items: list) -> list:
        """合并不可获取项，去重"""
        result = list(existing)
        
        for new_item in new_items:
            is_duplicate = False
            for existing_item in result:
                if self._is_similar_unavailable(new_item, existing_item):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                result.append(new_item)
        
        return result
    
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
        self._log_message(state, "开始数据采集任务...")
        
        rag_context = state.get("rag_context", [])
        if rag_context:
            self._log_message(state, f"向量库已有 {len(rag_context)} 条相关内容")
        
        state = await self.react_loop(state)
        
        action_str = state.get("action", "") or state.get("thought", "") or ""
        special_parsed = self.parse_special_output(action_str)
        
        if special_parsed["type"] == "need_user":
            state["need_user_input"] = special_parsed["need_user"]
            state["thought"] = f"需要用户输入: {special_parsed['need_user']}"
            state["is_finished"] = False
            self._log_message(state, f"需要用户输入: {special_parsed['need_user']}")
        else:
            if special_parsed.get("data_unavailable"):
                existing = state.get("data_unavailable", [])
                state["data_unavailable"] = self._merge_unavailable(existing, special_parsed["data_unavailable"])
                self._log_message(state, f"数据不可获取: {state['data_unavailable']}")
            
            if special_parsed.get("need_more_agent"):
                state["need_more_agent"] = special_parsed["need_more_agent"]
                state["thought"] = f"需要返回 {special_parsed['need_more_agent']}"
                state["is_finished"] = False
                self._log_message(state, f"请求返回: {special_parsed['need_more_agent']}")
            else:
                state["data_collection_finished"] = True
                self._log_message(state, "数据收集完成")
        
        return state


data_agent = DataAgent()

from src.tools.registry import tool_registry
data_agent.set_tool_registry(tool_registry)
