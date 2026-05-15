from typing import List, Dict, Any, Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document

from src.config import settings
from src.tools.file_processor import FileInfo


class _BGELangChainWrapper:
    """将 BGEEmbedder 包装为 LangChain Embeddings 兼容接口。"""
    def __init__(self, embedder):
        self._embedder = embedder
    def embed_documents(self, texts): return self._embedder.embed_documents_lc(texts)
    def embed_query(self, text): return self._embedder.embed_query_lc(text)


class RAGManager:
    def __init__(self, collection_name="default", persist_directory=None):
        self._embeddings = None
        self._vectorstore = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._initialized = False
        self._collection_name = collection_name
        self._persist_directory = persist_directory or settings.CHROMA_DB_PATH

    def _get_embeddings(self):
        if self._embeddings is None:
            from src.rag.bge_embedder import get_embedder
            self._embeddings = _BGELangChainWrapper(get_embedder())
        return self._embeddings

    def initialize_vectorstore(self):
        if self._vectorstore is None:
            from langchain_chroma import Chroma
            embeddings = self._get_embeddings()
            self._vectorstore = Chroma(
                persist_directory=self._persist_directory,
                embedding_function=embeddings,
                collection_name=self._collection_name,
                collection_metadata={"hnsw:space": "cosine"},
            )
            self._initialized = True
        return self._vectorstore

    def add_documents(self, file_info, metadata=None):
        vs = self.initialize_vectorstore()
        base = {"file_path": file_info["file_path"], "file_type": file_info["file_type"]}
        if metadata: base.update(metadata)
        docs = [Document(page_content=c, metadata={**base, "chunk_index": i})
                for i, c in enumerate(file_info["chunks"])]
        if docs: vs.add_documents(docs)
        return len(docs)

    def add_texts(self, texts, metadatas=None, ids=None):
        vs = self.initialize_vectorstore()
        kwargs = {"texts": texts, "metadatas": metadatas or [{} for _ in texts]}
        if ids: kwargs["ids"] = ids
        vs.add_texts(**kwargs)
        return len(texts)

    def similarity_search(self, query, k=4):
        try: return self.initialize_vectorstore().similarity_search(query, k=k)
        except: return []

    def similarity_search_with_score(self, query, k=4):
        try: return self.initialize_vectorstore().similarity_search_with_score(query, k=k)
        except: return []

    def max_marginal_relevance_search(self, query, k=4, fetch_k=20, lambda_mult=0.5):
        try: return self.initialize_vectorstore().max_marginal_relevance_search(
            query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult)
        except: return []

    def get_relevant_context(self, query, k=5):
        try: return [d.page_content for d in self.similarity_search(query, k=k)]
        except: return []

    def get_relevant_context_with_sources(self, query, k=4):
        results = self.similarity_search_with_score(query, k=k)
        return {"contexts": [d.page_content for d, _ in results],
                "sources": [{"file_path": d.metadata.get("file_path",""), "score": round(s,4)}
                           for d, s in results]}

    def delete_documents_by_file(self, file_path):
        try:
            c = self.initialize_vectorstore()._collection
            r = c.get(where={"file_path": file_path})
            if r["ids"]: c.delete(ids=r["ids"])
            return True
        except: return False

    def clear_collection(self):
        try:
            c = self.initialize_vectorstore()._collection
            r = c.get()
            if r["ids"]: c.delete(ids=r["ids"])
            return True
        except: return False

    def get_collection_stats(self):
        try:
            return {"document_count": self.initialize_vectorstore()._collection.count(),
                    "collection_name": settings.CHROMA_COLLECTION_NAME}
        except: return {"document_count": 0, "collection_name": settings.CHROMA_COLLECTION_NAME}

    async def add_documents_async(self, file_info, metadata=None):
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self.add_documents, file_info, metadata)

    async def similarity_search_async(self, query, k=4):
        return await asyncio.get_event_loop().run_in_executor(
            self._executor, self.similarity_search, query, k)

    async def get_relevant_context_async(self, query, k=4):
        return [d.page_content for d in await self.similarity_search_async(query, k)]


rag_manager = RAGManager()
