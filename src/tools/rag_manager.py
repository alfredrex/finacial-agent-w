from typing import List, Dict, Any, Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import settings
from src.tools.file_processor import FileInfo


class RAGManager:
    def __init__(self, collection_name: str = "default", persist_directory: Optional[str] = None):
        self._embeddings: Optional[OpenAIEmbeddings] = None
        self._vectorstore: Optional[Chroma] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._initialized = False
        self._collection_name = collection_name
        self._persist_directory = persist_directory or settings.CHROMA_DB_PATH
    
    def _get_embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            embed_kwargs = {
                "model": settings.EMBEDDING_MODEL,
            }
            
            embedding_api_key = settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY
            embedding_base_url = settings.EMBEDDING_BASE_URL
            
            if embedding_base_url:
                embed_kwargs["base_url"] = embedding_base_url
            
            self._embeddings = OpenAIEmbeddings(
                openai_api_key=embedding_api_key,
                **embed_kwargs
            )
        
        return self._embeddings
    
    def initialize_vectorstore(self) -> Chroma:
        if self._vectorstore is None:
            embeddings = self._get_embeddings()
            
            self._vectorstore = Chroma(
                persist_directory=self._persist_directory,
                embedding_function=embeddings,
                collection_name=self._collection_name,
            )
            
            self._initialized = True
        
        return self._vectorstore
    
    def add_documents(self, file_info: FileInfo, metadata: Dict[str, Any] = None) -> int:
        vectorstore = self.initialize_vectorstore()
        
        base_metadata = {
            "file_path": file_info["file_path"],
            "file_type": file_info["file_type"],
        }
        
        if metadata:
            base_metadata.update(metadata)
        
        documents = []
        for i, chunk in enumerate(file_info["chunks"]):
            doc_metadata = {**base_metadata, "chunk_index": i}
            documents.append(Document(page_content=chunk, metadata=doc_metadata))
        
        if documents:
            vectorstore.add_documents(documents)
        
        return len(documents)
    
    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]] = None,
                  ids: Optional[List[str]] = None) -> int:
        vectorstore = self.initialize_vectorstore()

        if metadatas is None:
            metadatas = [{} for _ in texts]

        kwargs = {"texts": texts, "metadatas": metadatas}
        if ids is not None:
            kwargs["ids"] = ids
        vectorstore.add_texts(**kwargs)

        return len(texts)
    
    def similarity_search(self, query: str, k: int = 4) -> List[Document]:
        vectorstore = self.initialize_vectorstore()
        
        try:
            results = vectorstore.similarity_search(query, k=k)
            return results
        except Exception as e:
            return []
    
    def similarity_search_with_score(self, query: str, k: int = 4) -> List[tuple]:
        vectorstore = self.initialize_vectorstore()
        
        try:
            results = vectorstore.similarity_search_with_score(query, k=k)
            return results
        except Exception as e:
            return []
    
    def max_marginal_relevance_search(self, query: str, k: int = 4, 
                                       fetch_k: int = 20, 
                                       lambda_mult: float = 0.5) -> List[Document]:
        vectorstore = self.initialize_vectorstore()
        
        try:
            results = vectorstore.max_marginal_relevance_search(
                query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult
            )
            return results
        except Exception as e:
            return []
    
    def get_relevant_context(self, query: str, k: int = 4) -> List[str]:
        documents = self.similarity_search(query, k=k)
        
        return [doc.page_content for doc in documents]
    
    def get_relevant_context_with_sources(self, query: str, k: int = 4) -> Dict[str, Any]:
        results = self.similarity_search_with_score(query, k=k)
        
        contexts = []
        sources = []
        
        for doc, score in results:
            contexts.append(doc.page_content)
            sources.append({
                "file_path": doc.metadata.get("file_path", "未知"),
                "file_type": doc.metadata.get("file_type", "未知"),
                "chunk_index": doc.metadata.get("chunk_index", 0),
                "score": round(score, 4)
            })
        
        return {
            "contexts": contexts,
            "sources": sources
        }
    
    def delete_documents_by_file(self, file_path: str) -> bool:
        vectorstore = self.initialize_vectorstore()
        
        try:
            collection = vectorstore._collection
            
            results = collection.get(
                where={"file_path": file_path}
            )
            
            if results["ids"]:
                collection.delete(ids=results["ids"])
            
            return True
        except Exception as e:
            return False
    
    def clear_collection(self) -> bool:
        vectorstore = self.initialize_vectorstore()
        
        try:
            collection = vectorstore._collection
            results = collection.get()
            
            if results["ids"]:
                collection.delete(ids=results["ids"])
            
            return True
        except Exception as e:
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        vectorstore = self.initialize_vectorstore()
        
        try:
            collection = vectorstore._collection
            count = collection.count()
            
            return {
                "document_count": count,
                "collection_name": settings.CHROMA_COLLECTION_NAME
            }
        except Exception as e:
            return {
                "document_count": 0,
                "collection_name": settings.CHROMA_COLLECTION_NAME,
                "error": str(e)
            }
    
    async def add_documents_async(self, file_info: FileInfo, 
                                   metadata: Dict[str, Any] = None) -> int:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, 
            self.add_documents, 
            file_info, 
            metadata
        )
    
    async def similarity_search_async(self, query: str, k: int = 4) -> List[Document]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.similarity_search,
            query,
            k
        )
    
    async def get_relevant_context_async(self, query: str, k: int = 4) -> List[str]:
        documents = await self.similarity_search_async(query, k)
        return [doc.page_content for doc in documents]


rag_manager = RAGManager()
