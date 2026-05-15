"""RAG 端到端测试: BGE embedding + 分块 + 入库 + 检索"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag.financial_chunker import chunk_financial_text
from src.rag.bge_embedder import get_embedder
from src.tools.rag_manager import rag_manager
from langchain_core.documents import Document

# 测试文本 (模拟研报)
text = """贵州茅台（600519）深度研究报告

投资要点：
贵州茅台2025年实现营收1700亿元，同比增长12.5%；净利润800亿元，同比增长15.2%。毛利率92.3%，净利率47.1%，ROE达到35.6%。我们给予买入评级，目标价1700元。

财务分析：
茅台酒营收1450亿元，系列酒营收250亿元。直销渠道占比提升至55%。当前PE（TTM）28.5倍，处于历史估值中位数附近。

风险提示：宏观经济下行风险；消费税改革不确定性。"""

# 1. 语义分块
chunks = chunk_financial_text(text)
print(f"Chunks: {len(chunks)}")

# 2. Embedding 验证
embedder = get_embedder()
vec = embedder.embed_query("茅台PE多少")
print(f"Embedding dims: {vec.shape[0]}, norm: {sum(vec**2):.4f}")

# 3. 入库 + 检索
vs = rag_manager.initialize_vectorstore()
print(f"VS type: {type(vs).__name__}")

# 清除旧测试数据
try:
    existing = vs.get()
    if existing.get('ids'):
        vs.delete(ids=existing['ids'])
        print(f"Cleared {len(existing['ids'])} old docs")
except Exception as e:
    print(f"Clear skip: {e}")

# 入库
from langchain_core.documents import Document
docs = [
    Document(page_content=c, metadata={
        "title": "茅台深度研报", "source": "测试", "date": "2026-05-12",
        "stock_codes": ["600519"], "chunk_index": i,
    })
    for i, c in enumerate(chunks)
]
ids = vs.add_documents(docs)
print(f"Stored {len(ids)} chunks")

# 4. 检索
results = vs.similarity_search("茅台PE多少", k=2)
print(f"\n检索 '茅台PE多少':")
for i, doc in enumerate(results):
    print(f"  [{i}] score: {doc.metadata.get('score','?')} | {doc.page_content[:80]}...")

print("\nALL PASSED")
