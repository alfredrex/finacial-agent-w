"""模拟 main.py 流程 — 比亚迪净利润查询"""
import sys, asyncio
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

async def main():
    from src.workflow import MultiAgentSystem

    # 模拟 main.py 启动
    system = MultiAgentSystem()
    print(f"kvstore: {'OK' if system.hybrid_memory else 'FALLBACK'}")
    if system.hybrid_memory:
        stats = system.hybrid_memory.l3.get_full_info("002594")
        print(f"L3 BYD: name={stats['base'].get('name')} rag={len(stats.get('rag_ids',{}))}")

        # 直接测 ChromaDB
        vs = system.hybrid_memory.chroma_store
        ids = ['byd_q1_2026_000', 'byd_q1_2026_001']
        r = vs.get(ids=ids)
        print(f"ChromaDB get({ids}): {len(r.get('ids',[]))} docs")

    print("\n─── run('比亚迪2026年第一季度的净利润是多少') ───")
    result = await system.run("比亚迪2026年第一季度的净利润是多少")
    answer = result.get("answer", "") or result.get("report", "")
    print(f"\nANSWER: {answer[:500]}")

    # 检查中间状态
    layers = result.get("hybrid_memory", {}).get("layers_hit", [])
    kvstore_data = [d for d in result.get("collected_data", []) if d.get("source") == "kvstore_l3"]
    print(f"\nlayers: {layers}")
    print(f"kvstore_L3 data: {len(kvstore_data)}")
    print(f"memory_sources: {result.get('memory_sources', [])}")

    system.close()

asyncio.run(main())
