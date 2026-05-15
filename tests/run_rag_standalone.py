"""独立 RAG 端到端测试 — 绕过 src/tools 导入链"""
import sys, os
os.chdir("/home/wjh/FinIntel-Multi-Agent")
sys.path.insert(0, ".")

from transformers import AutoTokenizer, AutoModel
import torch, numpy as np

# ─── 1. BGE Embedding ───
path = "./models/BAAI/bge-small-zh-v1___5"
tokenizer = AutoTokenizer.from_pretrained(path)
model = AutoModel.from_pretrained(path)
model.eval()

def bge_embed(texts):
    if isinstance(texts, str): texts = [texts]
    inp = tokenizer(texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        emb = model(**inp).last_hidden_state[:,0,:].numpy()
    return emb / np.linalg.norm(emb, axis=1, keepdims=True)

class BGECompat:
    def embed_documents(self, texts): return bge_embed(texts).tolist()
    def embed_query(self, text): return bge_embed(text).tolist()[0]

embed_fn = BGECompat()
vec = embed_fn.embed_query("测试")
print(f"BGE: {len(vec)}d, norm={sum(v**2 for v in vec):.4f}")

# ─── 2. 分块 ───
from src.rag.financial_chunker import chunk_financial_text

text = """贵州茅台（600519）深度研究报告

投资要点：
贵州茅台2025年实现营收1700亿元，同比增长12.5%；净利润800亿元，同比增长15.2%。
毛利率92.3%，净利率47.1%，ROE达到35.6%。给予买入评级，目标价1700元。

财务分析：茅台酒营收1450亿元，系列酒营收250亿元。当前PE（TTM）28.5倍。"""

chunks = chunk_financial_text(text)
print(f"Chunks: {len(chunks)}")

# ─── 3. ChromaDB 入库 ───
from langchain_chroma import Chroma
from langchain_core.documents import Document

vs = Chroma(
    persist_directory="./chromadb",
    embedding_function=embed_fn,
    collection_name="financial_docs",
    collection_metadata={"hnsw:space": "cosine"},
)

# 清旧数据
try:
    old = vs.get()
    if old.get('ids'):
        vs.delete(ids=old['ids'])
except: pass

docs = [Document(page_content=c, metadata={
    "title": "茅台研报", "source": "test", "date": "2026-05-12",
    "stock_codes": ["600519"], "chunk_index": i
}) for i, c in enumerate(chunks)]
ids = vs.add_documents(docs)
print(f"Stored: {len(ids)} docs")

# ─── 4. 检索 ───
results = vs.similarity_search("茅台PE多少", k=2)
print("\n检索 '茅台PE多少':")
for d in results:
    print(f"  [{len(d.page_content)}c] {d.page_content[:120]}...")

# ─── 5. 验证 L2 归一化后的余弦相似度 ───
q_vec = np.array(embed_fn.embed_query("茅台PE多少"))
d_vec = np.array(embed_fn.embed_documents([chunks[0]])[0])
sim = np.dot(q_vec, d_vec)
print(f"\nCosine sim: {sim:.4f}")
assert sim > 0.3, f"Similarity too low: {sim}"
assert sim <= 1.01, f"Similarity bad: {sim}"

print("\n=== ALL PASSED ===")
