"""快速验证：MemoryAgent + kvstore L3 数据注入"""
import sys, os, asyncio
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

async def main():
    from src.workflow import system
    
    # 直接测试 hybrid_memory 检索（不走 LangGraph）
    if system.hybrid_memory:
        ctx = await system.hybrid_memory.retrieve("茅台PE多少")
        print(f"Layers hit: {ctx.layers_hit}")
        print(f"Stock codes found: {list(ctx.stock_info.keys())}")
        for code, info in ctx.stock_info.items():
            print(f"  {code}: {info['base'].get('name')} PE={info['base'].get('pe_ttm')} price={info['quote'].get('price')}")
        print(f"Context: {ctx.get_combined_context()[:500]}")
        print("OK")
    else:
        print("No hybrid_memory available")

asyncio.run(main())
