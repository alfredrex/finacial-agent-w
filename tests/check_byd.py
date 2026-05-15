"""排查 BYD 数据是否存在"""
import sys, os
os.chdir("/home/wjh/FinIntel-Multi-Agent")
sys.path.insert(0, ".")
from src.memory.kvstore_client import KvstoreClient

kv = KvstoreClient(host="127.0.0.1", port=2000)
kv.connect()

# 1. kvstore L3: 股票索引
codes_raw = kv.hget("stock:_index:_codes")
print(f"L3 stock codes: {codes_raw}")

# 2. kvstore L3: 比亚迪基础数据
name = kv.hget("stock:002594:base:name")
sector = kv.hget("stock:002594:base:sector")
print(f"BYD base: name={name}, sector={sector}")

# 3. kvstore L3: RAG 索引
rag_labels = kv.hget("stock:002594:_rag_labels")
print(f"BYD rag labels: {rag_labels}")

# 4. ChromaDB 文档数
from langchain_chroma import Chroma
from src.rag.bge_embedder import BGEEmbedder
embedder = BGEEmbedder(model_path="./models/BAAI/bge-small-zh-v1___5")
emb_fn = type('E', (), {
    'embed_documents': lambda s, t: embedder.embed_documents_lc(t),
    'embed_query': lambda s, t: embedder.embed_query_lc(t)
})()
vs = Chroma(persist_directory="./chromadb", embedding_function=emb_fn, collection_name="financial_docs")
all_data = vs.get()
print(f"\nChromaDB total docs: {len(all_data.get('ids', []))}")
byd_docs = [i for i, m in enumerate(all_data.get('metadatas', [])) if '比亚迪' in str(m)]
print(f"BYD docs in ChromaDB: {len(byd_docs)}")
if byd_docs:
    for i in byd_docs[:2]:
        print(f"  [{i}] {all_data['documents'][i][:100]}...")

kv.close()
