from typing import Literal
import copy
from langgraph.graph import StateGraph, END

from src.state import AgentState
from src.agents.dispatcher_agent import dispatcher_agent
from src.agents.base_agent import snapshot_manager
from src.agents.data_agent import data_agent
from src.agents.analysis_agent import analysis_agent
from src.agents.qa_agent import qa_agent
from src.agents.report_agent import report_agent
from src.agents.file_processing_agent import file_processing_agent
from src.agents.memory_agent import memory_agent
from src.agents.visualization_agent import visualization_agent
from src.tools.registry import tool_registry
from src.tools.register_tools import register_all_tools
from src.memory.user_memory import user_memory_manager


register_all_tools()


def _check_agent_visit(state: AgentState, agent_name: str, max_visits: int = 2) -> bool:
    visit_count = state.get("agent_visit_count", {})
    current_count = visit_count.get(agent_name, 0)
    if current_count >= max_visits:
        return False
    visit_count[agent_name] = current_count + 1
    state["agent_visit_count"] = visit_count
    return True


async def dispatcher_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_dispatcher", "workflow")
    
    file_paths = state.get("file_paths", [])
    if file_paths:
        result = await dispatcher_agent.process(state)
        return {
            "selected_agent": "FileProcessingAgent",
            "current_agent": result.get("current_agent"),
            "thought": result.get("thought"),
            "rewritten_query": result.get("rewritten_query"),
            "action": "select_agent(FileProcessingAgent)",
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 1),
            "need_more_agent": None,
            "needs_deep_analysis": result.get("needs_deep_analysis", False),
            "deep_analysis_done": False,
            "indicator_calculation_done": False,
            "needs_visualization": result.get("needs_visualization", False),
            "visualization_done": False,
            "agent_visit_count": result.get("agent_visit_count", {}),
            "data_unavailable": [],
            "analysis_unavailable": [],
            "need_user_input": result.get("need_user_input"),
            "needs_data_collection": result.get("needs_data_collection", False),
            "needs_analysis": result.get("needs_analysis", False),
            "data_collection_finished": False,
            "analysis_finished": False,
            "exception_info": None,
            "exception_handled": False,
            "output_type": result.get("output_type", "qa"),
            "report_type": result.get("report_type"),
            "report_domain": result.get("report_domain"),
            "is_deep_qa": result.get("is_deep_qa", False),
            "needs_file_processing": True,
            "file_processing_done": False,
            "needs_memory_retrieval": result.get("needs_memory_retrieval", False),
            "memory_retrieval_done": False,
            "memory_context": [],
            "memory_sources": [],
        }
    
    try:
        result = await dispatcher_agent.process(state)
        return {
            "selected_agent": result.get("selected_agent"),
            "current_agent": result.get("current_agent"),
            "thought": result.get("thought"),
            "rewritten_query": result.get("rewritten_query"),
            "action": result.get("action"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 1),
            "need_more_agent": None,
            "needs_deep_analysis": result.get("needs_deep_analysis", False),
            "deep_analysis_done": False,
            "indicator_calculation_done": False,
            "needs_visualization": result.get("needs_visualization", False),
            "visualization_done": False,
            "agent_visit_count": result.get("agent_visit_count", {}),
            "data_unavailable": [],
            "analysis_unavailable": [],
            "need_user_input": result.get("need_user_input"),
            "needs_data_collection": result.get("needs_data_collection", False),
            "needs_analysis": result.get("needs_analysis", False),
            "data_collection_finished": False,
            "analysis_finished": False,
            "exception_info": None,
            "exception_handled": False,
            "output_type": result.get("output_type", "qa"),
            "report_type": result.get("report_type"),
            "report_domain": result.get("report_domain"),
            "is_deep_qa": result.get("is_deep_qa", False),
            "needs_file_processing": result.get("needs_file_processing", False),
            "file_processing_done": False,
            "needs_memory_retrieval": result.get("needs_memory_retrieval", False),
            "memory_retrieval_done": False,
            "memory_context": [],
            "memory_sources": [],
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "dispatcher",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def memory_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_memory_agent", "workflow")
    try:
        result = await memory_agent.process(state)
        return {
            "memory_context": result.get("memory_context", []),
            "memory_sources": result.get("memory_sources", []),
            "memory_retrieval_done": True,
            "thought": result.get("thought"),
            "action": result.get("action"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "iteration_logs": result.get("iteration_logs", []),
            "is_finished": result.get("is_finished", True),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "memory_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def data_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_data_agent", "workflow")
    try:
        result = await data_agent.process(state)
        is_finished = result.get("is_finished", False)
        data_collection_finished = result.get("data_collection_finished", is_finished)
        return {
            "collected_data": result.get("collected_data", []),
            "answer": result.get("answer"),
            "is_finished": is_finished,
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "rag_context": state.get("rag_context", []),
            "need_more_agent": result.get("need_more_agent"),
            "analysis_results": state.get("analysis_results", []),
            "needs_deep_analysis": state.get("needs_deep_analysis", False),
            "needs_visualization": state.get("needs_visualization", False),
            "visualization_done": state.get("visualization_done", False),
            "agent_visit_count": state.get("agent_visit_count", {}),
            "data_unavailable": result.get("data_unavailable", []),
            "analysis_unavailable": state.get("analysis_unavailable", []),
            "need_user_input": result.get("need_user_input"),
            "data_collection_finished": data_collection_finished,
            "analysis_finished": state.get("analysis_finished", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "data_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def analysis_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_analysis_agent", "workflow")
    try:
        result = await analysis_agent.process(state)
        is_finished = result.get("is_finished", False)
        return {
            "analysis_results": result.get("analysis_results", []),
            "answer": result.get("answer"),
            "is_finished": is_finished,
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "rag_context": state.get("rag_context", []),
            "need_more_agent": result.get("need_more_agent"),
            "collected_data": state.get("collected_data", []),
            "needs_deep_analysis": state.get("needs_deep_analysis", False),
            "needs_visualization": state.get("needs_visualization", False),
            "visualization_done": state.get("visualization_done", False),
            "deep_analysis_done": result.get("deep_analysis_done", False),
            "indicator_calculation_done": result.get("indicator_calculation_done", False),
            "agent_visit_count": result.get("agent_visit_count", {}),
            "data_unavailable": state.get("data_unavailable", []),
            "analysis_unavailable": result.get("analysis_unavailable", []),
            "need_user_input": result.get("need_user_input"),
            "data_collection_finished": state.get("data_collection_finished", False),
            "analysis_finished": result.get("analysis_finished", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "analysis_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def qa_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_qa_agent", "workflow")
    try:
        result = await qa_agent.process(state)
        return {
            "answer": result.get("answer"),
            "is_finished": result.get("is_finished", False),
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "rag_context": state.get("rag_context", []),
            "need_more_agent": result.get("need_more_agent"),
            "agent_visit_count": state.get("agent_visit_count", {}),
            "data_unavailable": state.get("data_unavailable", []),
            "analysis_unavailable": state.get("analysis_unavailable", []),
            "data_collection_finished": state.get("data_collection_finished", False),
            "analysis_finished": state.get("analysis_finished", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "qa_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def report_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_report_agent", "workflow")
    try:
        result = await report_agent.process(state)
        return {
            "report": result.get("report"),
            "answer": result.get("answer"),
            "is_finished": result.get("is_finished", False),
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "rag_context": state.get("rag_context", []),
            "need_more_agent": result.get("need_more_agent"),
            "collected_data": state.get("collected_data", []),
            "analysis_results": state.get("analysis_results", []),
            "agent_visit_count": state.get("agent_visit_count", {}),
            "data_unavailable": state.get("data_unavailable", []),
            "analysis_unavailable": state.get("analysis_unavailable", []),
            "need_user_input": result.get("need_user_input"),
            "data_collection_finished": state.get("data_collection_finished", False),
            "analysis_finished": state.get("analysis_finished", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "report_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def file_processing_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_file_processing_agent", "workflow")
    try:
        result = await file_processing_agent.process(state)
        return {
            "answer": result.get("answer"),
            "is_finished": result.get("is_finished", False),
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "rag_context": state.get("rag_context", []),
            "need_more_agent": result.get("need_more_agent"),
            "collected_data": state.get("collected_data", []),
            "analysis_results": state.get("analysis_results", []),
            "agent_visit_count": state.get("agent_visit_count", {}),
            "data_unavailable": state.get("data_unavailable", []),
            "analysis_unavailable": state.get("analysis_unavailable", []),
            "need_user_input": result.get("need_user_input"),
            "data_collection_finished": state.get("data_collection_finished", False),
            "analysis_finished": state.get("analysis_finished", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "file_processing_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


async def visualization_agent_node(state: AgentState) -> dict:
    snapshot_manager.save(state, "before_visualization_agent", "workflow")
    print(f"[DEBUG] visualization_agent_node: 开始执行")
    try:
        result = await visualization_agent.process(state)
        print(f"[DEBUG] visualization_agent_node: 执行成功, visualization_done=True")
        return {
            "answer": result.get("answer"),
            "is_finished": result.get("is_finished", False),
            "thought": result.get("thought"),
            "action": result.get("action"),
            "observation": result.get("observation"),
            "current_agent": result.get("current_agent"),
            "messages": result.get("messages", []),
            "agent_iteration": result.get("agent_iteration", 0),
            "iteration_logs": result.get("iteration_logs", []),
            "charts": result.get("charts", []),
            "tables": result.get("tables", []),
            "visualization_done": True,
            "collected_data": state.get("collected_data", []),
            "analysis_results": state.get("analysis_results", []),
            "agent_visit_count": state.get("agent_visit_count", {}),
            "data_collection_finished": state.get("data_collection_finished", False),
            "analysis_finished": state.get("analysis_finished", False),
            "deep_analysis_done": state.get("deep_analysis_done", False),
            "exception_info": None,
            "exception_handled": state.get("exception_handled", False),
        }
    except Exception as e:
        print(f"[DEBUG] visualization_agent_node: 执行失败 - {str(e)}")
        restored = snapshot_manager.restore_last()
        if restored:
            restored["exception_info"] = {
                "agent": "visualization_agent",
                "error": str(e),
                "error_type": type(e).__name__
            }
            restored["exception_handled"] = False
            return restored
        raise


def route_from_dispatcher(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "qa_agent", "report_agent", 
    "file_processing_agent", "memory_agent", "wait_for_user"
]:
    if state.get("need_user_input"):
        return "wait_for_user"
    
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    if state.get("needs_file_processing") and not state.get("file_processing_done"):
        return "file_processing_agent"
    
    if state.get("needs_memory_retrieval") and not state.get("memory_retrieval_done"):
        return "memory_agent"
    
    selected = state.get("selected_agent")
    if selected == "DataAgent":
        return "data_agent"
    elif selected == "AnalysisAgent":
        return "analysis_agent"
    elif selected == "QAAgent":
        return "qa_agent"
    elif selected == "ReportAgent":
        return "report_agent"
    elif selected == "FileProcessingAgent":
        return "file_processing_agent"
    
    return "qa_agent"


def route_from_file_processing_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "qa_agent", "report_agent", "memory_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    if state.get("needs_memory_retrieval") and not state.get("memory_retrieval_done"):
        return "memory_agent"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    elif need_more == "QAAgent":
        return "qa_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    needs_analysis = state.get("needs_analysis", False)
    data_collection_finished = state.get("data_collection_finished", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


def route_from_memory_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "qa_agent", "report_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    elif need_more == "QAAgent":
        return "qa_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    needs_analysis = state.get("needs_analysis", False)
    data_collection_finished = state.get("data_collection_finished", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


def route_from_data_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "visualization_agent", "qa_agent", "report_agent", "wait_for_user"
]:
    if state.get("need_user_input"):
        return "wait_for_user"
    
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    elif need_more == "QAAgent":
        return "qa_agent"
    
    needs_analysis = state.get("needs_analysis", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    needs_visualization = state.get("needs_visualization", False)
    visualization_done = state.get("visualization_done", False)
    data_collection_finished = state.get("data_collection_finished", False)
    
    print(f"[DEBUG] route_from_data_agent: needs_visualization={needs_visualization}, visualization_done={visualization_done}")
    print(f"[DEBUG] route_from_data_agent: data_collection_finished={data_collection_finished}, needs_analysis={needs_analysis}")
    
    if needs_visualization and not visualization_done and data_collection_finished and not needs_analysis:
        print(f"[DEBUG] route_from_data_agent: 返回 visualization_agent")
        return "visualization_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


def route_from_analysis_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "visualization_agent", "qa_agent", "report_agent", "wait_for_user"
]:
    if state.get("need_user_input"):
        return "wait_for_user"
    
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    elif need_more == "QAAgent":
        return "qa_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    data_collection_finished = state.get("data_collection_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    needs_deep_analysis = state.get("needs_deep_analysis", False)
    deep_analysis_done = state.get("deep_analysis_done", False)
    indicator_calculation_done = state.get("indicator_calculation_done", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_deep_analysis and not deep_analysis_done:
        if indicator_calculation_done and data_collection_finished and analysis_finished:
            if _check_agent_visit(state, "AnalysisAgent"):
                return "analysis_agent"
    
    needs_visualization = state.get("needs_visualization", False)
    visualization_done = state.get("visualization_done", False)
    
    print(f"[DEBUG] route_from_analysis_agent: needs_visualization={needs_visualization}, visualization_done={visualization_done}")
    print(f"[DEBUG] route_from_analysis_agent: data_collection_finished={data_collection_finished}, analysis_finished={analysis_finished}")
    
    if needs_visualization and not visualization_done:
        if (data_collection_finished and analysis_finished) or deep_analysis_done:
            print(f"[DEBUG] route_from_analysis_agent: 返回 visualization_agent")
            return "visualization_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


def route_from_file_processing_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "qa_agent", "report_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    elif need_more == "QAAgent":
        return "qa_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    needs_analysis = state.get("needs_analysis", False)
    data_collection_finished = state.get("data_collection_finished", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


async def wait_for_user_node(state: AgentState) -> dict:
    return {
        "need_user_input": state.get("need_user_input"),
        "is_finished": False,
    }


def route_from_qa_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "visualization_agent", "report_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "end"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        data_collection_finished = state.get("data_collection_finished", False)
        if not data_collection_finished:
            if _check_agent_visit(state, "DataAgent"):
                return "data_agent"
    elif need_more == "AnalysisAgent":
        analysis_finished = state.get("analysis_finished", False)
        if not analysis_finished:
            if _check_agent_visit(state, "AnalysisAgent"):
                return "analysis_agent"
    elif need_more == "ReportAgent":
        return "report_agent"
    
    needs_visualization = state.get("needs_visualization", False)
    visualization_done = state.get("visualization_done", False)
    data_collection_finished = state.get("data_collection_finished", False)
    
    if needs_visualization and not visualization_done and data_collection_finished:
        return "visualization_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    needs_analysis = state.get("needs_analysis", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "end"


def route_from_report_agent(state: AgentState) -> Literal[
    "data_agent", "analysis_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "end"
    
    need_more = state.get("need_more_agent")
    
    if need_more == "DataAgent":
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    elif need_more == "AnalysisAgent":
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    needs_data_collection = state.get("needs_data_collection", False)
    needs_analysis = state.get("needs_analysis", False)
    data_collection_finished = state.get("data_collection_finished", False)
    analysis_finished = state.get("analysis_finished", False)
    
    if needs_data_collection and not data_collection_finished:
        if _check_agent_visit(state, "DataAgent"):
            return "data_agent"
    
    if needs_analysis and not analysis_finished:
        if _check_agent_visit(state, "AnalysisAgent"):
            return "analysis_agent"
    
    return "end"


def route_from_visualization_agent(state: AgentState) -> Literal[
    "qa_agent", "report_agent", "end"
]:
    if state.get("exception_info") and not state.get("exception_handled"):
        return "qa_agent"
    
    output_type = state.get("output_type", "qa")
    if output_type == "report":
        return "report_agent"
    
    return "qa_agent"


def create_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)
    
    workflow.add_node("dispatcher", dispatcher_node)
    workflow.add_node("data_agent", data_agent_node)
    workflow.add_node("analysis_agent", analysis_agent_node)
    workflow.add_node("visualization_agent", visualization_agent_node)
    workflow.add_node("qa_agent", qa_agent_node)
    workflow.add_node("report_agent", report_agent_node)
    workflow.add_node("file_processing_agent", file_processing_agent_node)
    workflow.add_node("memory_agent", memory_agent_node)
    workflow.add_node("wait_for_user", wait_for_user_node)
    
    workflow.set_entry_point("dispatcher")
    
    workflow.add_conditional_edges(
        "dispatcher",
        route_from_dispatcher,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "file_processing_agent": "file_processing_agent",
            "memory_agent": "memory_agent",
            "wait_for_user": "wait_for_user",
        }
    )
    
    workflow.add_conditional_edges(
        "file_processing_agent",
        route_from_file_processing_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "memory_agent": "memory_agent",
            "end": END,
        }
    )
    
    workflow.add_conditional_edges(
        "memory_agent",
        route_from_memory_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "end": END,
        }
    )
    
    workflow.add_conditional_edges(
        "data_agent",
        route_from_data_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "visualization_agent": "visualization_agent",
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "wait_for_user": "wait_for_user",
        }
    )
    
    workflow.add_conditional_edges(
        "analysis_agent",
        route_from_analysis_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "visualization_agent": "visualization_agent",
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "wait_for_user": "wait_for_user",
        }
    )
    
    workflow.add_conditional_edges(
        "visualization_agent",
        route_from_visualization_agent,
        {
            "qa_agent": "qa_agent",
            "report_agent": "report_agent",
            "end": END,
        }
    )
    
    workflow.add_conditional_edges(
        "qa_agent",
        route_from_qa_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "visualization_agent": "visualization_agent",
            "report_agent": "report_agent",
            "end": END,
        }
    )
    
    workflow.add_conditional_edges(
        "report_agent",
        route_from_report_agent,
        {
            "data_agent": "data_agent",
            "analysis_agent": "analysis_agent",
            "end": END,
        }
    )
    
    return workflow


class MultiAgentSystem:
    def __init__(self):
        self.workflow = create_workflow()
        self.app = self.workflow.compile()
    
    async def run(self, query: str, file_paths: list = None, conversation_history: list = None) -> AgentState:
        memory_summary = user_memory_manager.get_memory_summary()
        
        add_result = await user_memory_manager.add_memory(query)
        
        initial_state: AgentState = {
            "query": query,
            "rewritten_query": None,
            "file_paths": file_paths or [],
            "collected_data": [],
            "analysis_results": [],
            "rag_context": [],
            "answer": None,
            "report": None,
            "error": None,
            "current_agent": None,
            "selected_agent": None,
            "messages": [],
            "metadata": {},
            "thought": None,
            "action": None,
            "observation": None,
            "iteration": 0,
            "agent_iteration": 0,
            "is_finished": False,
            "next_tool": None,
            "next_params": None,
            "iteration_logs": [],
            "conversation_history": conversation_history or [],
            "need_more_agent": None,
            "needs_deep_analysis": False,
            "deep_analysis_done": False,
            "indicator_calculation_done": False,
            "agent_visit_count": {},
            "data_unavailable": [],
            "analysis_unavailable": [],
            "need_user_input": None,
            "user_response": None,
            "token_usage": {},
            "change_percent": 0.0,
            "volume": 0.0,
            "timestamp": "",
            "needs_data_collection": False,
            "needs_analysis": False,
            "needs_deep_analysis": False,
            "deep_analysis_done": False,
            "data_collection_finished": False,
            "analysis_finished": False,
            "exception_info": None,
            "exception_handled": False,
            "output_type": "qa",
            "report_type": None,
            "report_domain": None,
            "is_deep_qa": False,
            "needs_visualization": False,
            "visualization_done": False,
            "charts": [],
            "tables": [],
            "user_memory_summary": memory_summary,
        }
        
        final_state = await self.app.ainvoke(initial_state)
        
        return final_state
    
    async def run_stream(self, query: str, file_paths: list = None, conversation_history: list = None):
        initial_state: AgentState = {
            "query": query,
            "rewritten_query": None,
            "file_paths": file_paths or [],
            "collected_data": [],
            "analysis_results": [],
            "rag_context": [],
            "answer": None,
            "report": None,
            "error": None,
            "current_agent": None,
            "selected_agent": None,
            "messages": [],
            "metadata": {},
            "thought": None,
            "action": None,
            "observation": None,
            "iteration": 0,
            "agent_iteration": 0,
            "is_finished": False,
            "next_tool": None,
            "next_params": None,
            "iteration_logs": [],
            "conversation_history": conversation_history or [],
            "need_more_agent": None,
            "needs_deep_analysis": False,
            "deep_analysis_done": False,
            "indicator_calculation_done": False,
            "agent_visit_count": {},
            "data_unavailable": [],
            "analysis_unavailable": [],
            "need_user_input": None,
            "user_response": None,
            "token_usage": {},
            "change_percent": 0.0,
            "volume": 0.0,
            "timestamp": "",
            "needs_data_collection": False,
            "needs_analysis": False,
            "needs_deep_analysis": False,
            "deep_analysis_done": False,
            "data_collection_finished": False,
            "analysis_finished": False,
            "exception_info": None,
            "exception_handled": False,
            "output_type": "qa",
            "report_type": None,
            "report_domain": None,
            "is_deep_qa": False,
            "needs_visualization": False,
            "visualization_done": False,
            "charts": [],
            "tables": [],
        }
        
        current_state = initial_state
        
        async for event in self.app.astream(initial_state):
            for node_name, node_output in event.items():
                if node_name == END:
                    yield "final", current_state
                    return
                else:
                    if node_output:
                        current_state.update(node_output)
                    yield node_name, node_output
        
        yield "final", current_state


system = MultiAgentSystem()
