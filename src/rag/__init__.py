"""RAG 模块: BGE embedding + 金融语义分块"""
from .bge_embedder import BGEEmbedder, get_embedder
from .financial_chunker import chunk_financial_text, chunk_with_metadata
