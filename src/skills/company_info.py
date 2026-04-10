from typing import Dict, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult
from src.tools.fallback_data_collector import fallback_data_collector


class GetCompanyInfoSkill(BaseSkill):
    name = "get_company_info"
    description = "获取上市公司基本信息（公司名称、行业、主营业务、注册资本、上市日期等）"
    category = SkillCategory.COMPANY
    parameters = {"symbol": "股票代码"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        try:
            data = fallback_data_collector.get_company_info(symbol)
            if "error" in data:
                return SkillResult(
                    success=False,
                    data=data,
                    message=data.get("error", "获取失败"),
                    source="none"
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


class GetTopShareholdersSkill(BaseSkill):
    name = "get_top_shareholders"
    description = "获取上市公司十大股东信息（股东名称、持股数量、持股比例等）"
    category = SkillCategory.COMPANY
    parameters = {"symbol": "股票代码", "date": "日期(可选，格式YYYYMMDD)"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "symbol" in kwargs and kwargs["symbol"]
    
    def execute(self, **kwargs) -> SkillResult:
        symbol = kwargs["symbol"]
        date = kwargs.get("date")
        try:
            data = fallback_data_collector.get_top_shareholders(symbol, date)
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
                message=f"获取成功，共{len(data)}位股东",
                source=data[0].get("source", "unknown") if data else "none"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


company_info_skill = GetCompanyInfoSkill()
top_shareholders_skill = GetTopShareholdersSkill()
