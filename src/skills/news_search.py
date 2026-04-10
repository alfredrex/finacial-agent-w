from typing import Dict, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult
from src.tools.fallback_data_collector import fallback_data_collector


class SearchNewsSkill(BaseSkill):
    name = "search_news"
    description = "搜索新闻资讯（公司动态、行业新闻、市场消息等）"
    category = SkillCategory.NEWS
    parameters = {"keyword": "关键词", "max_results": "结果数(可选，默认10)"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "keyword" in kwargs and kwargs["keyword"]
    
    def execute(self, **kwargs) -> SkillResult:
        keyword = kwargs["keyword"]
        max_results = kwargs.get("max_results", 10)
        try:
            data = fallback_data_collector.search_news(keyword, max_results)
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
                message=f"获取成功，共{len(data)}条新闻",
                source=data[0].get("data_source", "unknown") if data else "none"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


news_search_skill = SearchNewsSkill()
