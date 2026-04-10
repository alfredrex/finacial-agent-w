from typing import TypedDict, List, Optional, Annotated
from operator import add
from enum import Enum


class TaskType(str, Enum):
    QA = "qa"
    REPORT = "report"
    ANALYSIS = "analysis"
    DATA_COLLECTION = "data_collection"
    FILE_PROCESSING = "file_processing"
    SYSTEM_STATUS = "system_status"


class AgentState(TypedDict):
    query: str
    rewritten_query: Optional[str]
    task_type: TaskType
    file_paths: List[str]
    collected_data: List
    analysis_results: List
    rag_context: List[str]
    answer: Optional[str]
    report: Optional[str]
    error: Optional[str]
    current_agent: Optional[str]
    selected_agent: Optional[str]
    messages: List
    metadata: dict
    thought: Optional[str]
    action: Optional[str]
    observation: Optional[str]
    iteration: int
    agent_iteration: int
    is_finished: bool
    next_tool: Optional[str]
    next_params: Optional[dict]
    iteration_logs: List
    conversation_history: List
    need_more_agent: Optional[str]
    needs_deep_analysis: bool
    deep_analysis_done: bool
    indicator_calculation_done: bool
    needs_visualization: bool
    visualization_done: bool
    charts: List[dict]
    tables: List[dict]
    agent_visit_count: dict
    data_unavailable: List[str]
    analysis_unavailable: List[str]
    need_user_input: Optional[str]
    user_response: Optional[str]
    needs_data_collection: bool
    needs_analysis: bool
    data_collection_finished: bool
    analysis_finished: bool
    exception_info: Optional[dict]
    exception_handled: bool
    output_type: Optional[str]
    report_type: Optional[str]
    report_domain: Optional[str]
    is_deep_qa: bool
    needs_memory_retrieval: bool
    memory_retrieval_done: bool
    memory_context: List[str]
    memory_sources: List[dict]
    entity_memory: Optional[dict]
    task_memory: Optional[dict]
    needs_file_processing: bool
    file_processing_done: bool
    user_memory_summary: Optional[str]


class FileInfo(TypedDict):
    file_path: str
    file_type: str
    content: str
    chunks: List[str]


class AnalysisResult(TypedDict):
    indicator_name: str
    value: float
    description: str
    timestamp: str


class StockData(TypedDict):
    symbol: str
    name: str
    price: float
    change: float
    change_percent: float
    volume: float
    timestamp: str


class FinancialReport(TypedDict):
    title: str
    content: str
    sections: List[dict]
    generated_at: str
    data_sources: List[str]
