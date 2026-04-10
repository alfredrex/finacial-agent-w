from src.skills.base import BaseSkill, SkillCategory, SkillResult
from src.skills.registry import skill_registry

from src.skills.composite import (
    stock_analysis_skill,
    company_research_skill,
    market_overview_skill,
    stock_quick_view_skill,
)

skill_registry.register(stock_analysis_skill)
skill_registry.register(company_research_skill)
skill_registry.register(market_overview_skill)
skill_registry.register(stock_quick_view_skill)

__all__ = [
    "BaseSkill",
    "SkillCategory",
    "SkillResult",
    "skill_registry",
    "stock_analysis_skill",
    "company_research_skill",
    "market_overview_skill",
    "stock_quick_view_skill",
]
