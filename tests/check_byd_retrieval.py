"""模拟 BYD 检索链路"""
import sys, asyncio
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

async def main():
    from src.memory.kvstore_client import KvstoreClient
    from src.memory.hybrid_memory import HybridMemorySystem, extract_entities, _KNOWN_NAMES

    kv = KvstoreClient(host="127.0.0.1", port=2000)
    kv.connect()

    # 加载名字映射 (模拟 system 启动时的行为)
    from src.memory.kvstore_memory import StockMemory
    sm = StockMemory(kv)
    codes = sm.get_all_codes()
    print(f"codes in kvstore: {codes}")
    for code in codes:
        name = sm.get_base_field(code, "name")
        if name:
            from src.memory.hybrid_memory import register_stock_name
            register_stock_name(name, code)
            if len(name) >= 2:
                register_stock_name(name[-2:], code)
    print(f"KNOWN_NAMES: {dict(_KNOWN_NAMES)}")

    # 实体提取
    ents = extract_entities("比亚迪第一季度财报怎么样")
    print(f"entities: {ents}")

    # L3 检查
    for code in ents.get('stocks', []):
        info = sm.get_full_info(code)
        print(f"  {code}: {info['base']['name']} rag_count={len(info.get('rag_ids',{}))}")

    # 如果 entities 里没有 BYD，说明 _load_stock_names 在 system 初始化时没拿到数据
    if '002594' not in ents.get('stocks', []):
        print("\n⚠ BYD not in entities! Checking if _load_stock_names ran...")
    else:
        print("\n✅ BYD found in entities — retrieval should work")

    kv.close()

asyncio.run(main())
