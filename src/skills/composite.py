from typing import Dict, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult


class StockAnalysisSkill(BaseSkill):
    name = "stock_analysis"
    description = "股票综合分析：获取实时行情、历史K线、技术指标分析"
    category = SkillCategory.COMPOSITE
    parameters = {"symbol": "股票代码", "days": "分析天数(可选，默认60)"}
    required_tools = ["get_stock_realtime", "get_stock_history", "comprehensive_analysis"]
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        days = kwargs.get("days", 60)
        
        result_data = {}
        tools_used = []
        errors = []
        
        realtime = self._call_tool("get_stock_realtime", symbol=symbol)
        if "error" not in realtime:
            result_data["realtime"] = realtime
            tools_used.append("get_stock_realtime")
        else:
            errors.append(f"实时行情: {realtime.get('error')}")
        
        history = self._call_tool("get_stock_history", symbol=symbol, days=days)
        if "error" not in (history[0] if history else {}):
            result_data["history"] = history
            tools_used.append("get_stock_history")
        else:
            errors.append(f"历史数据: {history[0].get('error') if history else '无数据'}")
        
        analysis = self._call_tool("comprehensive_analysis", symbol=symbol)
        if "error" not in analysis:
            result_data["analysis"] = analysis
            tools_used.append("comprehensive_analysis")
        else:
            errors.append(f"技术分析: {analysis.get('error')}")
        
        success = len(tools_used) > 0
        
        return SkillResult(
            success=success,
            data=result_data,
            message=f"股票分析完成，使用了 {len(tools_used)} 个工具" if success else "股票分析失败",
            tools_used=tools_used,
            errors=errors
        )


class CompanyResearchSkill(BaseSkill):
    name = "company_research"
    description = "公司综合研究：获取公司信息、十大股东、相关新闻"
    category = SkillCategory.COMPOSITE
    parameters = {"symbol": "股票代码", "news_count": "新闻数量(可选，默认5)"}
    required_tools = ["get_company_info", "get_top_shareholders", "search_news"]
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        news_count = kwargs.get("news_count", 5)
        
        result_data = {}
        tools_used = []
        errors = []
        
        company_info = self._call_tool("get_company_info", symbol=symbol)
        if "error" not in company_info:
            result_data["company_info"] = company_info
            tools_used.append("get_company_info")
        else:
            errors.append(f"公司信息: {company_info.get('error')}")
        
        shareholders = self._call_tool("get_top_shareholders", symbol=symbol)
        if "error" not in (shareholders[0] if shareholders else {}):
            result_data["shareholders"] = shareholders
            tools_used.append("get_top_shareholders")
        else:
            errors.append(f"股东信息: {shareholders[0].get('error') if shareholders else '无数据'}")
        
        company_name = company_info.get("company_name", symbol) if "company_info" in result_data else symbol
        news = self._call_tool("search_news", keyword=company_name, max_results=news_count)
        if "error" not in (news[0] if news else {}):
            result_data["news"] = news
            tools_used.append("search_news")
        else:
            errors.append(f"新闻: {news[0].get('error') if news else '无数据'}")
        
        success = len(tools_used) > 0
        
        return SkillResult(
            success=success,
            data=result_data,
            message=f"公司研究完成，使用了 {len(tools_used)} 个工具" if success else "公司研究失败",
            tools_used=tools_used,
            errors=errors
        )


class MarketOverviewSkill(BaseSkill):
    name = "market_overview"
    description = "市场概览：获取市场指数、热门新闻"
    category = SkillCategory.COMPOSITE
    parameters = {"news_count": "新闻数量(可选，默认10)"}
    required_tools = ["get_market_index", "search_news"]
    
    def validate_params(self, **kwargs) -> bool:
        return True
    
    def execute(self, **kwargs) -> SkillResult:
        news_count = kwargs.get("news_count", 10)
        
        result_data = {}
        tools_used = []
        errors = []
        
        market_index = self._call_tool("get_market_index")
        if "error" not in (market_index[0] if market_index else {}):
            result_data["market_index"] = market_index
            tools_used.append("get_market_index")
        else:
            errors.append(f"市场指数: {market_index[0].get('error') if market_index else '无数据'}")
        
        news = self._call_tool("search_news", keyword="A股", max_results=news_count)
        if "error" not in (news[0] if news else {}):
            result_data["news"] = news
            tools_used.append("search_news")
        else:
            errors.append(f"新闻: {news[0].get('error') if news else '无数据'}")
        
        success = len(tools_used) > 0
        
        return SkillResult(
            success=success,
            data=result_data,
            message=f"市场概览完成，使用了 {len(tools_used)} 个工具" if success else "市场概览失败",
            tools_used=tools_used,
            errors=errors
        )


class StockQuickViewSkill(BaseSkill):
    name = "stock_quick_view"
    description = "股票快速查看：获取实时行情和基本信息"
    category = SkillCategory.COMPOSITE
    parameters = {"symbol": "股票代码"}
    required_tools = ["get_stock_realtime", "get_company_info"]
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        
        result_data = {}
        tools_used = []
        errors = []
        
        realtime = self._call_tool("get_stock_realtime", symbol=symbol)
        if "error" not in realtime:
            result_data["realtime"] = realtime
            tools_used.append("get_stock_realtime")
        else:
            errors.append(f"实时行情: {realtime.get('error')}")
        
        company_info = self._call_tool("get_company_info", symbol=symbol)
        if "error" not in company_info:
            result_data["company_info"] = company_info
            tools_used.append("get_company_info")
        else:
            errors.append(f"公司信息: {company_info.get('error')}")
        
        success = len(tools_used) > 0
        
        return SkillResult(
            success=success,
            data=result_data,
            message=f"快速查看完成，使用了 {len(tools_used)} 个工具" if success else "快速查看失败",
            tools_used=tools_used,
            errors=errors
        )


stock_analysis_skill = StockAnalysisSkill()
company_research_skill = CompanyResearchSkill()
market_overview_skill = MarketOverviewSkill()
stock_quick_view_skill = StockQuickViewSkill()
