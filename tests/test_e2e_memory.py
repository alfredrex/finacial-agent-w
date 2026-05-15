"""端到端验证：混合记忆 + MultiAgentSystem 集成测试"""
import sys, os, asyncio

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

async def main():
    from src.workflow import system

    print("=" * 60)
    print("端到端测试：混合记忆系统 + FinIntel MultiAgentSystem")
    print("=" * 60)

    # 检查 kvstore 状态
    if system.hybrid_memory:
        print(f"\n[kvstore] 已连接，四层混合记忆就绪")
        print(f"  L2 画像: {system.hybrid_memory.l2.get_profile_summary()[:100]}...")
    else:
        print(f"\n[kvstore] 未连接，降级为 ChromaDB 模式")

    # 测试 1: 简单股价查询
    print("\n─── 测试1: 茅台PE多少？───")
    try:
        result = await system.run("茅台PE多少？")
        answer = result.get("answer", "") or result.get("report", "")
        print(f"  回答: {answer[:200]}")
        # 检查是否从 kvstore 获取了数据
        collected = result.get("collected_data", [])
        kvstore_data = [d for d in collected if d.get("source") == "kvstore_l3"]
        memory_sources = result.get("memory_sources", [])
        hybrid = result.get("hybrid_memory", {})
        print(f"  kvstore L3 数据: {len(kvstore_data)} 条")
        print(f"  记忆层命中: {hybrid.get('layers_hit', [])}")
        print(f"  记忆源: {[s.get('type','') for s in memory_sources]}")

        # 验证
        if "28.5" in answer or "PE" in answer:
            print("  ✓ 回答包含 PE 信息")
        else:
            print("  ⚠ 回答未明确包含 PE 数值")

    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 测试 2: 查询会话上下文
    print("\n─── 测试2: 它贵不贵？(代词指代) ───")
    try:
        result = await system.run("它贵不贵？")
        answer = result.get("answer", "") or result.get("report", "")
        print(f"  回答: {answer[:200]}")
        hybrid = result.get("hybrid_memory", {})
        print(f"  记忆层命中: {hybrid.get('layers_hit', [])}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

    # 统计
    if system.hybrid_memory:
        stats = system.hybrid_memory.get_stats()
        print(f"\n─── 混合记忆统计 ───")
        print(f"  L1 会话对话轮次: {stats['l1']['turns']}")
        print(f"  L1 追踪实体: {stats['l1']['entity_types']}")

    # 清理
    system.close()
    print("\n=== 端到端测试完成 ===")

asyncio.run(main())
