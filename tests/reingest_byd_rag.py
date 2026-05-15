"""修复: 通过 rag_manager 入库 BYD 数据"""
import sys, os, json
os.chdir("/home/wjh/FinIntel-Multi-Agent")
sys.path.insert(0, ".")

from PyPDF2 import PdfReader
from src.rag.financial_chunker import chunk_financial_text
from src.tools.rag_manager import rag_manager
from langchain_core.documents import Document

# 1. PDF 提取
reader = PdfReader("data/byd_2026_1.pdf")
full_text = "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
print(f"Extracted: {len(full_text)} chars")

# 2. 语义分块
chunks = chunk_financial_text(full_text)
print(f"Chunks: {len(chunks)}")

# 3. 通过 rag_manager 入库
stock_code = "002594"
vs = rag_manager.initialize_vectorstore()
print(f"VS type: {type(vs).__name__}")

# 清旧 BYD
all_data = vs.get()
to_del = [i for i, m in enumerate(all_data.get('metadatas',[])) if '比亚迪' in str(m)]
to_del_ids = [all_data['ids'][i] for i in to_del]
if to_del_ids:
    vs.delete(ids=to_del_ids)
    print(f"Cleared {len(to_del_ids)} old docs")

# 入库（带显式 ID）
for i, chunk in enumerate(chunks):
    doc_id = f"byd_q1_2026_{i:03d}"
    vs.add_documents([Document(
        page_content=chunk,
        metadata={
            "title": "比亚迪2026年Q1财报", "source": "比亚迪官方",
            "date": "2026-04-30", "stock_codes": ["002594"],
            "category": "quarterly_report", "sector": "新能源汽车",
            "chunk_index": i,
        }
    )], ids=[doc_id])

print(f"Stored: {len(chunks)} docs")

# 4. 验证检索
ids_to_check = ["byd_q1_2026_000", "byd_q1_2026_001", "byd_q1_2026_002"]
result = vs.get(ids=ids_to_check)
print(f"get({ids_to_check}): {len(result.get('ids',[]))} docs found")
if result.get('documents'):
    print(f"  [0]: {result['documents'][0][:120]}...")

# 5. kvstore L3 索引
from src.memory.kvstore_client import KvstoreClient
from src.memory.kvstore_memory import StockMemory
kv = KvstoreClient(host="127.0.0.1", port=2000)
kv.connect()
sm = StockMemory(kv)
sm.update_base(stock_code, {"name": "比亚迪", "sector": "新能源汽车"})
for i in range(len(chunks)):
    sm.add_rag_index(stock_code, f"byd_q1_2026_chunk{i:03d}", f"byd_q1_2026_{i:03d}")
print(f"kvstore L3: {len(chunks)} indexes")

kv.close()
print("\nDone — now re-run test_byd_full.py")
