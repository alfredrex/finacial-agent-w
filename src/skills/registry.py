from typing import Dict, List, Optional, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult


class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._categories: Dict[SkillCategory, List[str]] = {
            cat: [] for cat in SkillCategory
        }
    
    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill
        self._categories[skill.category].append(skill.name)
    
    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)
    
    def list_skills(self) -> List[str]:
        return list(self._skills.keys())
    
    def get_by_category(self, category: SkillCategory) -> List[BaseSkill]:
        return [self._skills[name] for name in self._categories[category]]
    
    def get_skills_description(self, categories: List[SkillCategory] = None) -> str:
        skills_desc = []
        for skill in self._skills.values():
            if categories and skill.category not in categories:
                continue
            skills_desc.append(skill.get_description())
        return "\n".join(skills_desc)
    
    def execute(self, skill_name: str, **kwargs) -> SkillResult:
        skill = self.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                data={},
                message=f"Skill '{skill_name}' not found",
                tools_used=[],
                errors=[f"Skill '{skill_name}' not found"]
            )
        
        if not skill.validate_params(**kwargs):
            return SkillResult(
                success=False,
                data={},
                message=f"Invalid parameters for skill '{skill_name}'",
                tools_used=[],
                errors=["Invalid parameters"]
            )
        
        return skill.execute(**kwargs)


skill_registry = SkillRegistry()
