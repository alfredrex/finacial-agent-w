"""诊断 QAAgent 收到的数据"""
import sys, asyncio
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

async def main():
    from src.agents.qa_agent import qa_agent
    from src.agents.memory_agent import memory_agent
    from src.memory.kvstore_client import KvstoreClient
    from src.memory.hybrid_memory import HybridMemorySystem, register_stock_name
    from src.memory.kvstore_memory import StockMemory
    from src.tools.rag_manager import rag_manager

    kv = KvstoreClient(host="127.0.0.1", port=2000)
    kv.connect()

    sm = StockMemory(kv)
    for code in sm.get_all_codes():
        name = sm.get_base_field(code, "name")
        if name:
            register_stock_name(name, code)
            if len(name) >= 2:
                register_stock_name(name[-2:], code)

    vs = rag_manager.initialize_vectorstore()

    hms = HybridMemorySystem(kvstore_client=kv, chroma_store=vs, user_id="default")
    memory_agent.set_hybrid_memory(hms)

    state = {
        "query": "比亚迪2026年第一季度的净利润是多少",
        "rewritten_query": None, "user_id": "default",
        "collected_data": [], "rag_context": [], "memory_context": [],
        "conversation_history": [], "analysis_results": [],
        "charts": [], "tables": [],
        "visualization_done": False, "is_deep_qa": False,
        "data_unavailable": [], "analysis_unavailable": [],
    }

    # Step 1: MemoryAgent
    result = await memory_agent.process(state)
    print("=== MemoryAgent output ===")
    cd = result.get("collected_data", [])
    print(f"collected_data: {len(cd)} items")
    for item in cd:
        src = item.get("source") or item.get("data_source")
        print(f"  - [{src}] {str(item)[:100]}")
    print(f"rag_context: {len(result.get('rag_context',[]))} items")
    print(f"memory_context: {result.get('memory_context',[''])[0][:200]}")

    # Step 2: QAAgent
    result2 = await qa_agent.process(result)
    print(f"\n=== QAAgent answer ===")
    print(result2.get("answer","")[:400])

    kv.close()

asyncio.run(main())
