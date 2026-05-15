"""完整验证: BYD 检索全链路"""
import sys, asyncio
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

async def main():
    from src.memory.kvstore_client import KvstoreClient
    from src.memory.hybrid_memory import HybridMemorySystem, register_stock_name
    from src.memory.kvstore_memory import StockMemory
    from src.tools.rag_manager import rag_manager

    kv = KvstoreClient(host="127.0.0.1", port=2000)
    kv.connect()
    print("kvstore: connected")

    # 初始化 stock names
    sm = StockMemory(kv)
    for code in sm.get_all_codes():
        name = sm.get_base_field(code, "name")
        if name:
            register_stock_name(name, code)
            if len(name) >= 2:
                register_stock_name(name[-2:], code)
    print(f"names loaded: {len(sm.get_all_codes())} codes")

    # 初始化 L4
    try:
        vs = rag_manager.initialize_vectorstore()
        print(f"ChromaDB: {type(vs).__name__}")
    except Exception as e:
        print(f"ChromaDB: failed ({e})")
        vs = None

    # 混合记忆
    hms = HybridMemorySystem(
        kvstore_client=kv,
        chroma_store=vs,
        user_id="default"
    )

    # 检索
    print("\n─── 检索: '比亚迪第一季度财报营收多少' ───")
    ctx = await hms.retrieve("比亚迪第一季度财报营收多少")

    print(f"Layers hit: {ctx.layers_hit}")
    print(f"Stock codes: {list(ctx.stock_info.keys())}")
    for code, info in ctx.stock_info.items():
        print(f"  {code}: name={info['base'].get('name')} rag_ids={len(info.get('rag_ids',{}))}")

    if ctx.rag_doc_ids:
        print(f"RAG doc_ids (first 3): {ctx.rag_doc_ids[:3]}")
    else:
        print("RAG doc_ids: EMPTY!")

    print(f"Semantic results: {len(ctx.semantic_results)}")
    if ctx.semantic_results:
        for i, r in enumerate(ctx.semantic_results[:2]):
            content = r.get('content', '')[:150]
            meta = r.get('metadata', {})
            print(f"  [{i}] {meta.get('title','?')}: {content}...")
    else:
        print("Semantic results: EMPTY!")

    print(f"\nCombined context ({len(ctx.get_combined_context())} chars):")
    print(ctx.get_combined_context()[:400])

    kv.close()
    print("\nDone.")

asyncio.run(main())
