from typing import Dict, Any
from src.skills.base import BaseSkill, SkillCategory, SkillResult
from src.tools.rag_manager import rag_manager


class SearchKnowledgeSkill(BaseSkill):
    name = "search_knowledge"
    description = "搜索知识库（已上传的文档内容）"
    category = SkillCategory.KNOWLEDGE
    parameters = {"query": "查询文本", "k": "结果数(可选，默认4)"}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return "query" in kwargs and kwargs["query"]
    
    def execute(self, **kwargs) -> SkillResult:
        query = kwargs["query"]
        k = kwargs.get("k", 4)
        try:
            data = rag_manager.get_relevant_context(query, k)
            if not data:
                return SkillResult(
                    success=True,
                    data=[],
                    message="知识库为空或无相关内容",
                    source="chromadb"
                )
            return SkillResult(
                success=True,
                data=data,
                message=f"获取成功，共{len(data)}条相关内容",
                source="chromadb"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


class GetCollectionStatsSkill(BaseSkill):
    name = "get_collection_stats"
    description = "获取知识库统计信息"
    category = SkillCategory.KNOWLEDGE
    parameters = {}
    fallback_skills = []
    
    def validate_params(self, **kwargs) -> bool:
        return True
    
    def execute(self, **kwargs) -> SkillResult:
        try:
            data = rag_manager.get_collection_stats()
            return SkillResult(
                success=True,
                data=data,
                message=f"知识库共有{data.get('document_count', 0)}个文档",
                source="chromadb"
            )
        except Exception as e:
            return SkillResult(
                success=False,
                data=None,
                message=str(e),
                source="none"
            )


search_knowledge_skill = SearchKnowledgeSkill()
get_collection_stats_skill = GetCollectionStatsSkill()
