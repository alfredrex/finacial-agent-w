from src.agents.base_agent import BaseAgent
from src.state import AgentState
from src.tools.registry import ToolCategory


class FileProcessingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="FileProcessingAgent",
            description="负责文件处理和向量库操作，支持PDF、DOCX、TXT、XLSX、CSV等格式",
            tool_categories=[ToolCategory.FILE, ToolCategory.KNOWLEDGE]
        )
        
        self.file_system_prompt = """你是 {name}，{description}

可用工具:
{tools}

【工作流程】:
1. 如果只上传文件无 query，直接 finish()
2. 其他情况都路由到其他 Agent

输出格式:
Thought: 分析用户需求
Action: 工具名称(参数)

【需要其他 Agent 协助时】:
输出 NEED_MORE: Agent名称

例如:
- 需要回答问题 → NEED_MORE: QAAgent
- 需要数据分析 → NEED_MORE: AnalysisAgent
- 需要收集更多数据 → NEED_MORE: DataAgent

示例1 - 只上传文件无 query:
Thought: 用户只上传文件，无问题
Action: finish(文件已处理完成)

示例2 - 数据库统计:
Thought: 用户询问知识库统计，交给 QAAgent 回答
NEED_MORE: QAAgent
Action: finish(文件已处理，交给 QAAgent)

示例3 - 文件内容问题:
Thought: 用户询问文件内容，交给 QAAgent 回答
NEED_MORE: QAAgent
Action: finish(文件已处理，交给 QAAgent 回答)

示例4 - 需要分析:
Thought: 用户上传文件并要求分析股价数据，需要 AnalysisAgent
NEED_MORE: AnalysisAgent
Action: finish(文件已处理，请 AnalysisAgent 进行分析)

【重要规则】:
1. 文件已在入口处处理，无需重复处理
2. 只有"只上传文件无 query"才直接 finish
3. 其他情况都通过 NEED_MORE 路由到其他 Agent"""

    def _get_react_prompt(self) -> str:
        return self.file_system_prompt.format(
            name=self.name,
            description=self.description,
            tools=self._get_tools_description()
        )
    
    async def process(self, state: AgentState) -> AgentState:
        state["current_agent"] = self.name
        state["thought"] = None
        state["action"] = None
        state["observation"] = None
        state["agent_iteration"] = 0
        state["is_finished"] = False
        state["iteration_logs"] = []
        state["need_user_input"] = None
        state["need_more_agent"] = None
        self._log_message(state, "开始文件处理任务...")
        
        file_paths = state.get("file_paths", [])
        query = state.get("query", "")
        
        if file_paths:
            self._log_message(state, f"检测到文件上传: {len(file_paths)} 个")
        
        if not query:
            self._log_message(state, "无 query，直接完成")
            state["is_finished"] = True
            state["answer"] = "文件已处理完成"
            return state
        
        state = await self.react_loop(state)
        
        action_str = state.get("action", "") or state.get("thought", "") or ""
        special_parsed = self.parse_special_output(action_str)
        
        if special_parsed.get("need_more_agent"):
            state["need_more_agent"] = special_parsed["need_more_agent"]
            state["thought"] = f"需要路由到: {special_parsed['need_more_agent']}"
            state["is_finished"] = False
            self._log_message(state, f"路由到: {special_parsed['need_more_agent']}")
        
        return state


file_processing_agent = FileProcessingAgent()

from src.tools.registry import tool_registry
file_processing_agent.set_tool_registry(tool_registry)
