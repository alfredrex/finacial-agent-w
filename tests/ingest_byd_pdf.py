"""比亚迪财报 PDF 解析入库

流程: PDF文本提取 → 5步语义分块 → BGE embedding → ChromaDB入库 + kvstore L3索引
"""
import sys, os, json, re
os.chdir("/home/wjh/FinIntel-Multi-Agent")
sys.path.insert(0, ".")

# ─── 1. PDF 文本提取 ───
from PyPDF2 import PdfReader

pdf_path = "data/byd_2026_1.pdf"
reader = PdfReader(pdf_path)
print(f"PDF: {len(reader.pages)} pages")

raw_text = []
for i, page in enumerate(reader.pages):
    text = page.extract_text()
    if text:
        raw_text.append(text)
full_text = "\n".join(raw_text)
print(f"Extracted: {len(full_text)} chars")

# ─── 2. 语义分块 ───
from src.rag.financial_chunker import chunk_financial_text

chunks = chunk_financial_text(full_text)
print(f"Chunks: {len(chunks)}")

# 分析分布
lengths = [len(c) for c in chunks]
print(f"  min: {min(lengths)}, max: {max(lengths)}, avg: {sum(lengths)//len(lengths)}")
# 预览前3块
for i, c in enumerate(chunks[:3]):
    print(f"  [{i+1}] {len(c)}c: {c[:100]}...")

# ─── 3. 提取关键财务数据 (用于 kvstore L3) ───
def extract_financial_data(text):
    """从文本中提取结构化财务数据"""
    data = {}
    # 营收
    m = re.search(r'营收[总收入]*[约达到为]*\s*([\d,.]+\s*[万亿]?元?)', text)
    if m: data['revenue'] = m.group(1)
    m = re.search(r'营业收入[约达到为]*\s*([\d,.]+\s*[万亿]?元?)', text)
    if m: data['revenue'] = m.group(1)

    # 净利润
    m = re.search(r'净利润[约达到为]*\s*([\d,.]+\s*[万亿]?元?)', text)
    if m: data['net_profit'] = m.group(1)
    m = re.search(r'归[属母]?[公司于].*?净利润[约达到为]*\s*([\d,.]+\s*[万亿]?元?)', text)
    if m: data['net_profit'] = m.group(1)

    # 增长率
    m = re.search(r'[同比]*增长\s*([\d.]+%)', text)
    if m: data['growth'] = m.group(1)

    # PE
    m = re.search(r'市盈率[\(（]?PE[\)）]?\s*[约达到为]*\s*([\d.]+)', text)
    if m: data['pe'] = m.group(1)

    return data

fin_data = extract_financial_data(full_text)
print(f"\n财务数据: {fin_data}")

# ─── 4. ChromaDB 入库 ───
from src.rag.bge_embedder import get_embedder, BGEEmbedder
from langchain_chroma import Chroma
from langchain_core.documents import Document

embedder = BGEEmbedder(model_path="./models/BAAI/bge-small-zh-v1___5")
embed_fn = type('Emb', (), {
    'embed_documents': lambda self, texts: embedder.embed_documents_lc(texts),
    'embed_query': lambda self, text: embedder.embed_query_lc(text),
})()

vs = Chroma(
    persist_directory="./chromadb",
    embedding_function=embed_fn,
    collection_name="financial_docs",
    collection_metadata={"hnsw:space": "cosine"},
)

# 清旧 BYD 数据
try:
    old = vs.get()
    if old.get('ids'):
        byd_ids = [i for i, id_ in enumerate(old['ids']) if 'byd' in str(old['metadatas'][i]).lower()]
        # 全量获取再过滤删除
        all_ids = old['ids']
        all_metas = old.get('metadatas', [{}]*len(all_ids))
        to_delete = [id_ for id_, meta in zip(all_ids, all_metas) if '比亚迪' in str(meta)]
        if to_delete:
            vs.delete(ids=to_delete)
            print(f"Cleared {len(to_delete)} old BYD docs")
except Exception as e:
    print(f"Clear skip: {e}")

# 入库
stock_code = "002594"
doc_ids = []
for i, chunk in enumerate(chunks):
    doc_id = f"byd_q1_2026_{i:03d}"
    doc_ids.append(doc_id)
    vs.add_documents([Document(
        page_content=chunk,
        metadata={
            "title": "比亚迪2026年第一季度财报",
            "source": "比亚迪官方",
            "date": "2026-04-30",
            "stock_codes": [stock_code],
            "category": "quarterly_report",
            "sector": "新能源汽车",
            "chunk_index": i,
        }
    )], ids=[doc_id])

print(f"Stored: {len(chunks)} chunks in ChromaDB")

# ─── 5. kvstore L3 索引 ───
from src.memory.kvstore_client import KvstoreClient
from src.memory.kvstore_memory import StockMemory

kv = KvstoreClient(host="127.0.0.1", port=2000)
kv.connect()
sm = StockMemory(kv)

# 基础信息
sm.update_base(stock_code, {
    "name": "比亚迪", "sector": "新能源汽车", "industry": "汽车制造",
})
# 行情 (Q1 期末估值快照)
sm.update_quote(stock_code, {"price": fin_data.get('price', '')})

# RAG 索引 — 把 ChromaDB 文档 ID 注册到 kvstore L3
for i, doc_id in enumerate(doc_ids):
    sm.add_rag_index(stock_code, f"byd_q1_2026_chunk{i:03d}", doc_id)

print(f"kvstore L3: registered {len(doc_ids)} RAG indexes for {stock_code}")

# ─── 6. 验证检索 ───
results = vs.similarity_search("比亚迪营收多少", k=2)
print("\n─── 检索验证 '比亚迪营收多少' ───")
for d in results:
    print(f"  [{len(d.page_content)}c] {d.page_content[:120]}...")

print("\n=== 入库完成 ===")
