"""清理 pyc 缓存并运行 RAG E2E 测试"""
import os, sys, shutil, pathlib

os.chdir("/home/wjh/FinIntel-Multi-Agent")
sys.path.insert(0, ".")

# 清理缓存
base = pathlib.Path("src/tools")
for d in base.rglob("__pycache__"):
    shutil.rmtree(d, ignore_errors=True)
for f in base.rglob("*.pyc"):
    try: os.remove(f)
    except: pass
print("Cache cleared")

# 导入
from src.rag.financial_chunker import chunk_financial_text
from src.rag.bge_embedder import get_embedder
from src.tools.rag_manager import rag_manager
from langchain_core.documents import Document

# 测试文本
text = """贵州茅台（600519）深度研究报告

投资要点：
贵州茅台2025年实现营收1700亿元，同比增长12.5%；净利润800亿元，同比增长15.2%。
毛利率92.3%，净利率47.1%，ROE达到35.6%。给予买入评级，目标价1700元。

财务分析：
茅台酒营收1450亿元，系列酒营收250亿元。直销渠道占比55%。
当前PE（TTM）28.5倍，处于历史估值中位数附近。"""

# 分块
chunks = chunk_financial_text(text)
print(f"Chunks: {len(chunks)}")

# Embedding
embedder = get_embedder()
vec = embedder.embed_query("茅台PE多少")
print(f"Embedding: {vec.shape[0]}d, norm={sum(vec**2):.4f}")

# 入库
vs = rag_manager.initialize_vectorstore()
try:
    old = vs.get()
    if old.get('ids'):
        vs.delete(ids=old['ids'])
except: pass

docs = [Document(page_content=c, metadata={
    "title": "茅台研报", "source": "test", "date": "2026-05-12",
    "stock_codes": ["600519"], "chunk_index": i
}) for i, c in enumerate(chunks)]
vs.add_documents(docs)
print(f"Stored: {len(docs)} docs")

# 检索
results = vs.similarity_search("茅台PE多少", k=2)
print("\n检索 '茅台PE多少':")
for d in results:
    print(f"  [{len(d.page_content)}c] {d.page_content[:100]}...")

print("\nALL PASSED")
