from src.tools.registry import tool_registry, ToolCategory
from src.tools.enhanced_data_collector import enhanced_data_collector
from src.tools.financial_analyzer import financial_analyzer
from src.tools.rag_manager import rag_manager
from src.tools.file_processor import file_processor


def register_all_tools():
    tool_registry.register(
        name="get_stock_realtime",
        description="获取股票实时行情数据（价格、涨跌幅、成交量等）",
        category=ToolCategory.DATA_STOCK,
        parameters={"symbol": "股票代码"},
        func=enhanced_data_collector.get_stock_realtime
    )
    
    tool_registry.register(
        name="get_stock_history",
        description="获取股票历史K线数据（开盘价、收盘价、最高价、最低价等）",
        category=ToolCategory.DATA_STOCK,
        parameters={"symbol": "股票代码", "days": "天数"},
        func=enhanced_data_collector.get_stock_history
    )
    
    tool_registry.register(
        name="get_market_index",
        description="获取市场指数数据（上证指数、深证成指、创业板指等）",
        category=ToolCategory.DATA_STOCK,
        parameters={},
        func=enhanced_data_collector.get_market_index
    )
    
    tool_registry.register(
        name="search_news",
        description="搜索新闻资讯（公司动态、行业新闻、市场消息等）",
        category=ToolCategory.DATA_NEWS,
        parameters={"keyword": "关键词", "max_results": "结果数"},
        func=enhanced_data_collector.search_news
    )
    
    tool_registry.register(
        name="get_company_info",
        description="获取上市公司基本信息（公司名称、行业、主营业务、注册资本、上市日期等）",
        category=ToolCategory.DATA_COMPANY,
        parameters={"symbol": "股票代码"},
        func=enhanced_data_collector.get_company_info
    )
    
    tool_registry.register(
        name="get_top_shareholders",
        description="获取上市公司十大股东信息（股东名称、持股数量、持股比例等）",
        category=ToolCategory.DATA_COMPANY,
        parameters={"symbol": "股票代码", "date": "日期(可选，格式YYYYMMDD)"},
        func=enhanced_data_collector.get_top_shareholders
    )
    
    tool_registry.register(
        name="get_financial_data",
        description="获取财务数据（利润、营收、现金流等）",
        category=ToolCategory.DATA_COMPANY,
        parameters={"symbol": "股票代码", "data_type": "数据类型(profit/revenue/cashflow/all)"},
        func=enhanced_data_collector.get_financial_data
    )
    
    tool_registry.register(
        name="comprehensive_analysis",
        description="综合分析股票（技术指标、趋势判断、风险评估）",
        category=ToolCategory.ANALYSIS,
        parameters={"symbol": "股票代码"},
        func=financial_analyzer.comprehensive_analysis_wrapper
    )
    
    tool_registry.register(
        name="search_knowledge",
        description="搜索知识库（已上传的文档内容）",
        category=ToolCategory.KNOWLEDGE,
        parameters={"query": "查询", "k": "结果数"},
        func=rag_manager.get_relevant_context
    )
    
    tool_registry.register(
        name="get_collection_stats",
        description="获取知识库统计信息",
        category=ToolCategory.KNOWLEDGE,
        parameters={},
        func=rag_manager.get_collection_stats
    )
    
    tool_registry.register(
        name="process_file",
        description="处理文件并添加到知识库（支持PDF、DOCX、TXT、XLSX、CSV）",
        category=ToolCategory.FILE,
        parameters={"file_path": "文件路径"},
        func=file_processor.process_file
    )


register_all_tools()
