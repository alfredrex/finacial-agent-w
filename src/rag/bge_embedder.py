"""
BGE Embedding 封装 — BAAI/bge-small-zh-v1.5

特性:
  - 本地模型加载 (无需联网)
  - L2 归一化 (用于余弦相似度 = 归一化后点积)
  - 批量编码, 最大 512 token 输入
  - LangChain Embeddings 兼容接口
"""

from __future__ import annotations

import os
import numpy as np
from typing import List, Optional

import torch
from transformers import AutoTokenizer, AutoModel


class BGEEmbedder:
    """BGE-small-zh-v1.5 本地 embedding 服务。

    Usage:
        embedder = BGEEmbedder(model_path="./models/BAAI/bge-small-zh-v1___5")
        vecs = embedder.embed(["文本1", "文本2"])   # → np.ndarray (N, 512)
        single = embedder.embed_query("查询文本")    # → np.ndarray (512,)
    """

    DIM = 512
    MAX_LEN = 512

    def __init__(self, model_path: str = "./models/BAAI/bge-small-zh-v1___5",
                 device: str = "cpu", normalize: bool = True):
        """
        Args:
            model_path: 模型目录路径
            device: "cpu" 或 "cuda"
            normalize: 是否 L2 归一化 (默认 True, 用于余弦相似度)
        """
        self.model_path = model_path
        self.device = device
        self.normalize = normalize
        self._tokenizer: Optional[AutoTokenizer] = None
        self._model: Optional[AutoModel] = None
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModel.from_pretrained(self.model_path)
        self._model.to(self.device)
        self._model.eval()
        self._loaded = True

    def embed(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """批量 embedding (返回 L2 归一化向量)。

        Args:
            texts: 文本列表
            batch_size: 批大小

        Returns:
            np.ndarray shape (len(texts), 512)
        """
        self._ensure_loaded()
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.MAX_LEN,
                return_tensors="pt",
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

            with torch.no_grad():
                outputs = self._model(**encoded)
                # BGE: 使用 [CLS] token 作为句子表示
                embeddings = outputs.last_hidden_state[:, 0, :].cpu().numpy()

            if self.normalize:
                embeddings = embeddings / np.linalg.norm(
                    embeddings, axis=1, keepdims=True
                )
            all_embeddings.append(embeddings)

        return np.vstack(all_embeddings)

    def embed_query(self, text: str) -> np.ndarray:
        """单条查询 embedding (BGE 查询不加 instruction prefix)。

        Returns:
            np.ndarray shape (512,)
        """
        return self.embed([text])[0]

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        """批量文档 embedding (BGE 文档不加 instruction prefix)。

        Returns:
            np.ndarray shape (len(texts), 512)
        """
        return self.embed(texts)

    # ── LangChain Embeddings 兼容接口 ──────────────────

    def embed_documents_lc(self, texts: List[str]) -> List[List[float]]:
        """LangChain 兼容: 返回 List[List[float]]。"""
        return self.embed(texts).tolist()

    def embed_query_lc(self, text: str) -> List[float]:
        """LangChain 兼容: 返回 List[float]。"""
        return self.embed_query(text).tolist()


# ── 全局单例 ─────────────────────────────────────────

_default_embedder: Optional[BGEEmbedder] = None


def get_embedder(model_path: str = None) -> BGEEmbedder:
    """获取全局 BGE embedder 单例。"""
    global _default_embedder
    if _default_embedder is None:
        path = model_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "models", "BAAI", "bge-small-zh-v1___5"
        )
        path = os.path.abspath(path)
        _default_embedder = BGEEmbedder(model_path=path)
    return _default_embedder
