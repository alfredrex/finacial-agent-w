"""验证 L3 metrics 是否正确注入"""
import sys, asyncio
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

async def main():
    from src.memory.kvstore_client import KvstoreClient
    from src.memory.hybrid_memory import HybridMemorySystem, register_stock_name
    from src.memory.kvstore_memory import StockMemory
    from src.tools.rag_manager import rag_manager

    kv = KvstoreClient(host="127.0.0.1", port=2000); kv.connect()
    sm = StockMemory(kv)
    for code in sm.get_all_codes():
        n = sm.get_base_field(code, "name")
        if n: register_stock_name(n, code); register_stock_name(n[-2:], code)
    vs = rag_manager.initialize_vectorstore()
    hms = HybridMemorySystem(kvstore_client=kv, chroma_store=vs)

    ctx = await hms.retrieve("比亚迪净利润多少")
    print(f"L3 metrics: {ctx.stock_info.get('002594',{}).get('metrics',{})}")
    print(f"L3 semantic_summary: {ctx.semantic_summary[:500]}")
    print(f"L4 results: {len(ctx.semantic_results)}")
    print(f"Combined: {ctx.get_combined_context()[:800]}")
    kv.close()

asyncio.run(main())
