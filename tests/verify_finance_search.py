"""验证: 财务费用检索"""
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
    hms = HybridMemorySystem(kvstore_client=kv, chroma_store=vs, user_id="default")

    # 测试1: 财务费用
    ctx = await hms.retrieve("比亚迪财务费用是多少")
    print(f"测试1 财务费用: layers={ctx.layers_hit} results={len(ctx.semantic_results)}")
    found = False
    for r in ctx.semantic_results:
        c = r.get("content", "")
        if "财务费用" in c:
            i = c.find("财务费用")
            print(f"  HIT => {c[i:i+150]}")
            found = True
            break
    if not found:
        print("  NOT FOUND in results")
        for r in ctx.semantic_results[:2]:
            print(f"  [{r.get('content','')[:80]}]")

    # 测试2: 净利润  
    ctx2 = await hms.retrieve("比亚迪净利润多少")
    print(f"\n测试2 净利润: layers={ctx2.layers_hit} results={len(ctx2.semantic_results)}")
    for r in ctx2.semantic_results:
        c = r.get("content", "")
        if "净利润" in c:
            i = c.find("净利润")
            print(f"  HIT => {c[i:i+150]}")
            break
    
    kv.close()
    print("\nDone.")

asyncio.run(main())
