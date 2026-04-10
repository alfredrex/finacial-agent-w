from typing import Dict, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult
from src.tools.fallback_data_collector import fallback_data_collector


class GetStockRealtimeSkill(BaseSkill):
    name = "get_stock_realtime"
    description = "获取股票实时行情数据（价格、涨跌幅、成交量等）"
    category = SkillCategory.STOCK
    parameters = {"symbol": "股票代码"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        try:
            data = fallback_data_collector.get_stock_realtime(symbol)
            if "error" in data:
                return SkillResult(
                    success=False,
                    data=data,
                    message=data.get("error", "获取失败"),
                    source=data.get("source", "none")
                )
            return SkillResult(
                success=True,
                data=data,
                message="获取成功",
                source=data.get("source", "unknown")
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


class GetStockHistorySkill(BaseSkill):
    name = "get_stock_history"
    description = "获取股票历史K线数据（开盘价、收盘价、最高价、最低价等）"
    category = SkillCategory.STOCK
    parameters = {"symbol": "股票代码", "days": "天数(可选，默认30)"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        days = kwargs.get("days", 30)
        try:
            data = fallback_data_collector.get_stock_history(symbol, days)
            if data and len(data) > 0 and "error" in data[0]:
                return SkillResult(
                    success=False,
                    data=data,
                    message=data[0].get("error", "获取失败"),
                    source="none"
                )
            return SkillResult(
                success=True,
                data=data,
                message=f"获取成功，共{len(data)}条记录",
                source=data[0].get("source", "unknown") if data else "none"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


class GetMarketIndexSkill(BaseSkill):
    name = "get_market_index"
    description = "获取市场指数数据（上证指数、深证成指、创业板指等）"
    category = SkillCategory.STOCK
    parameters = {}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return True
    
    def execute(self, **kwargs) -> SkillResult:
        try:
            data = fallback_data_collector.get_market_index()
            if data and len(data) > 0 and "error" in data[0]:
                return SkillResult(
                    success=False,
                    data=data,
                    message=data[0].get("error", "获取失败"),
                    source="none"
                )
            return SkillResult(
                success=True,
                data=data,
                message=f"获取成功，共{len(data)}个指数",
                source=data[0].get("source", "unknown") if data else "none"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


stock_quote_skill = GetStockRealtimeSkill()
stock_history_skill = GetStockHistorySkill()
market_index_skill = GetMarketIndexSkill()
