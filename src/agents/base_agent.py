from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import asyncio
import re
import copy
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.config import settings
from src.state import AgentState
from src.tools.registry import ToolRegistry, ToolCategory

# 通信模块 (惰性导入，避免循环依赖)
_communication = None
_memory_system = None


def _get_communication():
    global _communication
    if _communication is None:
        from src.communication import message_bus, blackboard
        _communication = (message_bus, blackboard)
    return _communication


def _get_memory_system():
    global _memory_system
    if _memory_system is None:
        from src.memory import memory_system
        _memory_system = memory_system
    return _memory_system


class StateSnapshot:
    def __init__(self, state: AgentState, step: str, agent: str):
        self.state = copy.deepcopy(state)
        self.step = step
        self.agent = agent
        self.timestamp = datetime.now().isoformat()
    
    def restore(self) -> AgentState:
        return copy.deepcopy(self.state)


class SnapshotManager:
    def __init__(self, max_snapshots: int = 10):
        self._snapshots: List[StateSnapshot] = []
        self._max_snapshots = max_snapshots
    
    def save(self, state: AgentState, step: str, agent: str) -> StateSnapshot:
        snapshot = StateSnapshot(state, step, agent)
        self._snapshots.append(snapshot)
        
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots.pop(0)
        
        return snapshot
    
    def restore_last(self) -> Optional[AgentState]:
        if self._snapshots:
            return self._snapshots.pop().restore()
        return None
    
    def restore_to_step(self, step: str) -> Optional[AgentState]:
        for i, snapshot in enumerate(reversed(self._snapshots)):
            if snapshot.step == step:
                self._snapshots = self._snapshots[:-i-1] if i > 0 else self._snapshots[:-1]
                return snapshot.restore()
        return None
    
    def clear(self):
        self._snapshots.clear()
    
    def get_history(self) -> List[Dict[str, Any]]:
        return [
            {"step": s.step, "agent": s.agent, "timestamp": s.timestamp}
            for s in self._snapshots
        ]


snapshot_manager = SnapshotManager()


class BaseAgent(ABC):
    def __init__(self, name: str, description: str, 
                 tool_categories: List[ToolCategory] = None,
                 skill_categories: List = None):
        self.name = name
        self.description = description
        self.tool_categories = tool_categories or []
        self.skill_categories = skill_categories or []
        self._llm: Optional[ChatOpenAI] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._skill_registry = None
        self.token_usage = {"prompt": 0, "completion": 0, "total": 0}
        self.max_iterations = 8
        self._tools_description_cache: Optional[str] = None
        self._skills_description_cache: Optional[str] = None
    
    def set_tool_registry(self, registry: ToolRegistry):
        self._tool_registry = registry
        self._tools_description_cache = None
    
    def set_skill_registry(self, registry):
        self._skill_registry = registry
        self._skills_description_cache = None
    
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
            
            if settings.OPENAI_BASE_URL:
                llm_kwargs["base_url"] = settings.OPENAI_BASE_URL
            
            self._llm = ChatOpenAI(
                openai_api_key=settings.OPENAI_API_KEY,
                **llm_kwargs
            )
        
        return self._llm
    
    def _get_tools_description(self) -> str:
        if self._tool_registry is None:
            return "无可用工具"
        
        if self._tools_description_cache:
            return self._tools_description_cache
        
        if self.tool_categories is None or len(self.tool_categories) == 0:
            return "无可用工具"
        
        tools_desc = []
        for cat in self.tool_categories:
            tools = self._tool_registry.get_tools_by_category(cat)
            tools_desc.extend([f"- {t.name}: {t.description}" for t in tools])
        
        self._tools_description_cache = "\n".join(tools_desc)
        return self._tools_description_cache
    
    def _get_skills_description(self) -> str:
        from src.skills import skill_registry as global_skill_registry
        
        if self.skill_categories is None or len(self.skill_categories) == 0:
            return "无可用技能"
        
        skills_desc = []
        for cat in self.skill_categories:
            skills = global_skill_registry.get_by_category(cat)
            for skill in skills:
                params_desc = ", ".join([f"{k}: {v}" for k, v in skill.parameters.items()])
                skills_desc.append(f"- {skill.name}({params_desc}): {skill.description}")
        
        return "\n".join(skills_desc) if skills_desc else "无可用技能"
    
    def _get_capabilities_description(self) -> str:
        parts = []
        
        if self.skill_categories and len(self.skill_categories) > 0:
            parts.append("【可用技能】(高级能力，组合多个工具):")
            parts.append(self._get_skills_description())
        
        if self.tool_categories and len(self.tool_categories) > 0:
            parts.append("\n【可用工具】(原子能力):")
            parts.append(self._get_tools_description())
        
        return "\n".join(parts) if parts else "无可用能力"
    
    def _get_react_prompt(self) -> str:
        return f"""你是 {self.name}，{self.description}

你使用 ReAct 模式工作: Thought -> Action -> Observation

可用工具:
{self._get_tools_description()}

输出格式:
Thought: 分析当前情况，决定下一步行动
Action: 工具名称(参数)

示例:
Thought: 需要获取股票实时行情
Action: get_stock_realtime(600519)

重要规则:
1. 每次只输出一个 Thought 和一个 Action
2. 根据观察结果决定下一步
3. 当任务完成时，输出 Action: finish(最终回答)"""
    
    def _create_system_message(self, content: str) -> SystemMessage: return SystemMessage(content=content)
    
    def _create_human_message(self, content: str) -> HumanMessage: return HumanMessage(content=content)
    
    def _create_ai_message(self, content: str) -> AIMessage: return AIMessage(content=content)
    
    def _log_message(self, state: AgentState, message: str):
        if "messages" not in state:
            state["messages"] = []
        
        state["messages"].append({
            "agent": self.name,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def _update_token_usage(self, response, state: AgentState):
        if hasattr(response, 'usage_metadata'):
            usage = response.usage_metadata
            self.token_usage["prompt"] += usage.get('prompt_tokens', 0)
            self.token_usage["completion"] += usage.get('completion_tokens', 0)
            self.token_usage["total"] = self.token_usage["prompt"] + self.token_usage["completion"]
    
    def parse_action(self, action_str: str) -> Dict[str, Any]:
        action_str = action_str.strip()
        
        if re.match(r'^finish\s*\(', action_str, re.IGNORECASE):
            idx = action_str.find('(')
            content_start = idx + 1
            content = action_str[content_start:].strip()
            if content.endswith(')'):
                content = content[:-1].strip()
            if not content:
                content = "任务完成"
            return {"tool": "finish", "params": {"content": content}}
        
        tools = self._parse_multiple_actions(action_str)
        if len(tools) == 1:
            return tools[0]
        elif len(tools) > 1:
            return {"tool": "__batch__", "params": {}, "tools": tools}
        
        return {"tool": "unknown", "params": {}, "raw": action_str}
    
    def _parse_multiple_actions(self, action_str: str) -> List[Dict[str, Any]]:
        """解析多个工具调用，支持逗号分隔的批量调用"""
        tools = []
        
        # 改进的括号匹配算法，支持嵌套的JSON结构
        i = 0
        while i < len(action_str):
            # 查找工具名称
            tool_match = re.match(r'(\w+)\s*\(', action_str[i:])
            if not tool_match:
                i += 1
                continue
            
            tool_name = tool_match.group(1)
            start = i + tool_match.end() - 1  # 左括号的位置
            
            # 使用括号计数器找到匹配的右括号
            depth = 0
            j = start
            in_string = False
            escape_next = False
            
            while j < len(action_str):
                char = action_str[j]
                
                if escape_next:
                    escape_next = False
                    j += 1
                    continue
                
                if char == '\\':
                    escape_next = True
                    j += 1
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                elif not in_string:
                    if char in '([{':
                        depth += 1
                    elif char in ')]}':
                        depth -= 1
                        if depth == 0:
                            # 找到匹配的右括号
                            params_str = action_str[start+1:j]
                            
                            # 解析参数
                            params = self._parse_params(params_str)
                            
                            if tool_name.lower() != 'finish':
                                tools.append({"tool": tool_name, "params": params})
                            
                            i = j + 1
                            break
                j += 1
            else:
                i += 1
        
        return tools
    
    def _parse_params(self, params_str: str) -> Dict[str, Any]:
        """解析工具参数"""
        params = {}
        params_str = params_str.strip()
        
        if not params_str:
            return params
        
        # 尝试解析JSON格式的参数
        if params_str.startswith('{') and params_str.endswith('}'):
            try:
                import json
                params = json.loads(params_str)
                return params
            except:
                pass
            
            try:
                import ast
                parsed = ast.literal_eval(params_str)
                if isinstance(parsed, dict):
                    params = parsed
                    return params
            except:
                pass
        
        # 解析key=value格式的参数
        if '=' in params_str:
            parts = re.split(r',\s*(?=[^=]+=)', params_str)
            for part in parts:
                if '=' in part:
                    key, value = part.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 尝试解析值
                    if value.startswith('{') or value.startswith('['):
                        try:
                            import json
                            params[key] = json.loads(value)
                        except:
                            params[key] = value
                    elif value.startswith('"') or value.startswith("'"):
                        params[key] = value[1:-1] if len(value) > 1 else value
                    else:
                        try:
                            params[key] = int(value)
                        except:
                            try:
                                params[key] = float(value)
                            except:
                                params[key] = value
        
        return params
    
    def parse_special_output(self, response: str) -> Dict[str, Any]:
        result = {
            "type": "normal",
            "need_user": None,
            "need_more_agent": None,
            "data_unavailable": [],
            "analysis_unavailable": []
        }
        
        if "NEED_USER:" in response:
            lines = response.strip().split("\n")
            for line in lines:
                if line.startswith("NEED_USER:"):
                    question = line.replace("NEED_USER:", "").strip()
                    result["type"] = "need_user"
                    result["need_user"] = question
                    break
        
        if "NEED_MORE:" in response:
            lines = response.strip().split("\n")
            for line in lines:
                if line.startswith("NEED_MORE:"):
                    agent_name = line.replace("NEED_MORE:", "").strip()
                    result["need_more_agent"] = agent_name
                    break
        
        if "DATA_UNAVAILABLE:" in response:
            lines = response.strip().split("\n")
            for line in lines:
                if line.startswith("DATA_UNAVAILABLE:"):
                    unavailable = line.replace("DATA_UNAVAILABLE:", "").strip()
                    result["data_unavailable"] = [x.strip() for x in unavailable.split("/")]
        
        if "ANALYSIS_UNAVAILABLE:" in response:
            lines = response.strip().split("\n")
            for line in lines:
                if line.startswith("ANALYSIS_UNAVAILABLE:"):
                    unavailable = line.replace("ANALYSIS_UNAVAILABLE:", "").strip()
                    result["analysis_unavailable"] = [x.strip() for x in unavailable.split("/")]
        
        return result
    
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        if self._tool_registry is None:
            return "错误: 工具注册表未设置"
        
        tool = self._tool_registry.get(tool_name)
        if tool is None:
            return f"错误: 未知工具 {tool_name}"
        
        if self.tool_categories is None or len(self.tool_categories) == 0:
            return f"错误: {self.name} 没有工具调用权限"
        
        tool_allowed = False
        for cat in self.tool_categories:
            if tool.category == cat:
                tool_allowed = True
                break
            elif cat == ToolCategory.DATA and tool.category in [
                ToolCategory.DATA, ToolCategory.DATA_NEWS,
                ToolCategory.DATA_STOCK, ToolCategory.DATA_COMPANY
            ]:
                tool_allowed = True
                break
        if not tool_allowed:
            return f"错误: {self.name} 没有权限调用工具 {tool_name}（类别: {tool.category}）"
        
        try:
            expected_params = list(tool.parameters.keys()) if tool.parameters else []
            mapped_params = {}
            
            if not params:
                pass
            elif "arg" in params:
                if len(expected_params) >= 1:
                    mapped_params[expected_params[0]] = params["arg"]
            elif "args" in params:
                args_list = params["args"]
                if isinstance(args_list, list):
                    for i, val in enumerate(args_list):
                        if i < len(expected_params):
                            param_name = expected_params[i]
                            mapped_params[param_name] = self._convert_param(param_name, val)
                elif isinstance(args_list, str):
                    if len(expected_params) >= 1:
                        mapped_params[expected_params[0]] = args_list
            else:
                for key, val in params.items():
                    if key in expected_params:
                        mapped_params[key] = self._convert_param(key, val)
            
            import inspect
            sig = inspect.signature(tool.func)
            for param_name, param in sig.parameters.items():
                if param_name not in mapped_params:
                    if param.default != inspect.Parameter.empty:
                        pass
                    else:
                        defaults = {"symbol": "", "days": 30, "k": 4, "max_results": 10, "keyword": "", "query": ""}
                        if param_name in defaults:
                            mapped_params[param_name] = defaults[param_name]
            
            if asyncio.iscoroutinefunction(tool.func):
                result = await tool.func(**mapped_params)
            else:
                result = tool.func(**mapped_params)
            
            return result
        except Exception as e:
            return f"工具执行错误: {str(e)}"
    
    async def execute_skill(self, skill_name: str, params: Dict[str, Any]) -> Any:
        if self._skill_registry is None:
            return "错误: 技能注册表未设置"
        
        from src.skills import skill_registry as global_skill_registry
        skill = global_skill_registry.get(skill_name)
        if skill is None:
            return f"错误: 未知技能 {skill_name}"
        
        if self.skill_categories is None or len(self.skill_categories) == 0:
            return f"错误: {self.name} 没有技能调用权限"
        
        skill_allowed = False
        from src.skills.base import SkillCategory
        for cat in self.skill_categories:
            if skill.category == cat:
                skill_allowed = True
                break
            elif cat == SkillCategory.COMPOSITE and skill.category in [
                SkillCategory.COMPOSITE, SkillCategory.STOCK, 
                SkillCategory.NEWS, SkillCategory.COMPANY
            ]:
                skill_allowed = True
                break
        
        if not skill_allowed:
            return f"错误: {self.name} 没有权限调用技能 {skill_name}"
        
        try:
            result = global_skill_registry.execute(skill_name, **params)
            
            if result.success:
                return result.data
            else:
                return {"error": result.message, "errors": result.errors}
        except Exception as e:
            return f"技能执行错误: {str(e)}"
    
    def _convert_param(self, param_name: str, value: Any) -> Any:
        if param_name in ("days", "k", "max_results") and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                defaults = {"days": 30, "k": 4, "max_results": 10}
                return defaults.get(param_name, value)
        return value
    
    async def think(self, state: AgentState) -> Dict[str, str]:
        llm = self._get_llm()
        
        context_parts = []
        context_parts.append(f"用户问题: {state.get('query', '')}")
        
        rag_context = state.get("rag_context", [])
        if rag_context:
            rag_summary = "\n".join([str(c)[:300] for c in rag_context[:3]])
            context_parts.append(f"向量库检索结果 (rag_context):\n{rag_summary}")
        
        if state.get("collected_data"):
            data_summary = "\n".join(str(d)[:500] for d in state["collected_data"][-3:])
            context_parts.append(f"已采集数据:\n{data_summary}")
        
        if state.get("analysis_results"):
            analysis_summary = str(state["analysis_results"][-3:])[:500]
            context_parts.append(f"分析结果: {analysis_summary}")
        
        iteration_logs = state.get("iteration_logs", [])
        if iteration_logs:
            history_parts = []
            for log in iteration_logs:
                if log.get("thought"):
                    history_parts.append(f"Thought: {log['thought']}")
                if log.get("action"):
                    history_parts.append(f"Action: {log['action']}")
                if log.get("observation"):
                    history_parts.append(f"Observation: {log['observation']}")
            if history_parts:
                context_parts.append(f"历史推理记录:\n" + "\n".join(history_parts))
        
        context_parts.append(f"当前迭代: {state.get('agent_iteration', 0)}/{self.max_iterations}")
        
        messages = [
            self._create_system_message(self._get_react_prompt()),
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
    
    async def react_loop(self, state: AgentState) -> AgentState:
        iteration = state.get("agent_iteration", 0)
        if "iteration_logs" not in state:
            state["iteration_logs"] = []
        
        while iteration < self.max_iterations:
            iteration += 1
            state["agent_iteration"] = iteration
            
            snapshot_manager.save(state, f"iteration_{iteration}", self.name)
            
            try:
                think_result = await self.think(state)
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
                    self._log_message(state, "任务完成")
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
                
                restored_state = snapshot_manager.restore_last()
                if restored_state:
                    state = restored_state
                    self._log_message(state, f"已回滚到上一步")
                
                state["error"] = str(e)
                state["observation"] = f"执行出错，已回滚: {str(e)}"
                
                if iteration >= 3:
                    state["answer"] = f"任务执行中多次出错: {str(e)}"
                    state["is_finished"] = True
                    break
        
        if iteration >= self.max_iterations and not state.get("is_finished"):
            state["answer"] = f"数据采集完成，已收集 {len(state.get('collected_data', []))} 条数据"
            state["is_finished"] = True
        
        return state
    
    async def _execute_single_tool(self, state: AgentState, tool_name: str, params: Dict[str, Any]) -> Any:
        """执行单个工具"""
        from src.skills import skill_registry as global_skill_registry
        skill = global_skill_registry.get(tool_name)
        
        if skill and self.skill_categories and len(self.skill_categories) > 0:
            result = await self.execute_skill(tool_name, params)
        else:
            result = await self.execute_tool(tool_name, params)
        
        if isinstance(result, str) and (result.startswith("错误:") or result.startswith("工具执行错误") or result.startswith("技能执行错误")):
            raise Exception(result)
        
        return result
    
    async def _execute_batch_tools(self, state: AgentState, tools: List[Dict[str, Any]]) -> List[str]:
        """批量执行多个工具（并行）"""
        import asyncio
        
        async def execute_one(tool_info: Dict[str, Any]) -> str:
            tool_name = tool_info.get("tool")
            params = tool_info.get("params", {})
            try:
                result = await self._execute_single_tool(state, tool_name, params)
                self._add_to_collected_data(state, result)
                if isinstance(result, dict):
                    return f"[{tool_name}] {str(result)[:200]}"
                elif isinstance(result, list):
                    return f"[{tool_name}] 获取 {len(result)} 条数据"
                return f"[{tool_name}] {str(result)[:200]}"
            except Exception as e:
                return f"[{tool_name}] 错误: {str(e)}"
        
        tasks = [execute_one(t) for t in tools]
        results = await asyncio.gather(*tasks)
        return list(results)
    
    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        pass
    
    # ─── 通信能力 ──────────────────────────────────────

    async def send_message(self, to_agent: str, msg_type: str,
                           content: Any, thread_id: str = None) -> str:
        """通过消息总线发送消息给另一个 Agent"""
        message_bus, _ = _get_communication()
        from src.communication.models import MessageType
        try:
            mtype = MessageType(msg_type)
        except ValueError:
            mtype = MessageType.QUERY
        return message_bus.send(
            from_agent=self.name, to_agent=to_agent,
            type=mtype, content=content, thread_id=thread_id,
        )

    async def read_messages(self) -> List[dict]:
        """读取所有未读消息"""
        message_bus, _ = _get_communication()
        msgs = message_bus.get_messages(self.name)
        return [
            {"from": m.from_agent, "type": m.type.value,
             "content": m.content, "thread_id": m.thread_id,
             "timestamp": m.timestamp.isoformat()}
            for m in msgs
        ]

    def blackboard_read(self, namespace: str, key: str) -> Any:
        """从黑板读取数据"""
        _, blackboard = _get_communication()
        return blackboard.read(namespace, key)

    def blackboard_write(self, namespace: str, key: str, value: Any):
        """写入数据到黑板"""
        _, blackboard = _get_communication()
        blackboard.write(namespace, key, value, updated_by=self.name)

    # ─── 记忆能力 ──────────────────────────────────────

    async def remember(self, query: str, answer: str = "",
                       thought_process: str = "", state: AgentState = None):
        """将当前交互存储到记忆系统"""
        ms = _get_memory_system()
        await ms.store(
            query=query, answer=answer, thought_process=thought_process,
            state=state,
        )

    async def recall(self, query_text: str, limit: int = 5) -> str:
        """从记忆系统检索相关内容"""
        ms = _get_memory_system()
        results_dict = await ms.retrieve(query_text, limit=limit)
        return ms.get_context_string(results_dict, top_k=limit)

    def __call__(self, state: AgentState) -> AgentState:
        return asyncio.run(self.process(state))
    
    async def invoke_llm(self, system_prompt: str, user_input: str, 
                         temperature: float = None, state: AgentState = None) -> str:
        llm = self._get_llm(temperature)
        
        messages = [
            self._create_system_message(system_prompt),
            self._create_human_message(user_input)
        ]
        
        try:
            response = await llm.ainvoke(messages)
            
            if state:
                self._update_token_usage(state, response)
            
            return response.content
        except Exception as e:
            return f"LLM调用错误: {str(e)}"
    
    async def plan_tools_batch(self, state: AgentState, planning_prompt: str) -> dict:
        """
        批量规划工具调用的通用方法
        返回: {"thought": str, "tools": list, ...}
        """
        import json
        llm = self._get_llm()
        
        messages = [
            self._create_system_message("你是专业的任务规划专家，擅长规划工具调用。"),
            self._create_human_message(planning_prompt)
        ]
        
        response = await llm.ainvoke(messages)
        self._update_token_usage(response, state)
        
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            return json.loads(content.strip())
        except Exception:
            return {"thought": "解析失败", "tools": []}
    
    async def execute_tools_batch(self, state: AgentState, tools: list, 
                                   parallel: bool = False) -> list:
        """
        批量执行工具的通用方法
        Args:
            state: Agent状态
            tools: 工具列表 [{"name": "tool_name", "params": {...}}, ...]
            parallel: 是否并行执行（默认顺序执行）
        Returns:
            执行结果列表
        """
        if parallel:
            return await self._execute_tools_parallel(state, tools)
        return await self._execute_tools_sequential(state, tools)
    
    async def _execute_tools_sequential(self, state: AgentState, tools: list) -> list:
        """顺序执行工具"""
        results = []
        for tool_info in tools:
            tool_name = tool_info.get("name")
            params = tool_info.get("params", {})
            
            result = await self.execute_tool(tool_name, params)
            results.append({
                "tool": tool_name,
                "params": params,
                "result": result
            })
            
            self._add_to_collected_data(state, result)
        
        return results
    
    async def _execute_tools_parallel(self, state: AgentState, tools: list) -> list:
        """并行执行工具"""
        import asyncio
        
        async def execute_single(tool_info: dict) -> dict:
            tool_name = tool_info.get("name")
            params = tool_info.get("params", {})
            result = await self.execute_tool(tool_name, params)
            return {
                "tool": tool_name,
                "params": params,
                "result": result
            }
        
        tasks = [execute_single(t) for t in tools]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "tool": tools[i].get("name"),
                    "params": tools[i].get("params", {}),
                    "result": {"error": str(result)}
                })
            else:
                final_results.append(result)
                self._add_to_collected_data(state, result.get("result"))
        
        return final_results
    
    def _add_to_collected_data(self, state: AgentState, result: Any):
        """将工具结果添加到 collected_data"""
        if isinstance(result, dict):
            if "error" not in result:
                state["collected_data"].append(result)
        elif isinstance(result, list) and result:
            if isinstance(result[0], dict) and "error" not in result[0]:
                state["collected_data"].extend(result)
