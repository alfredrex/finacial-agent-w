#!/usr/bin/env python3
"""测试数据收集工具"""

import sys
sys.path.insert(0, '.')

from src.tools.register_tools import register_all_tools
from src.tools.registry import tool_registry, ToolCategory

from src.tools.enhanced_data_collector import enhanced_data_collector

register_all_tools()

print("\n" + "="*60)
print("数据收集工具测试")
print("=" * 60)

tools = tool_registry.list_tools()
print(f"\n总共注册了 {len(tools)} 个工具:")
for tool_name in tools:
    tool = tool_registry.get(tool_name)
    print(f"\n{tool_name}:")
    print(f"  描述: {tool.description}")
    print(f"  类别: {tool.category}")
    print(f"  参数: {tool.parameters}")
    print(f"  函数: {tool.func.__name__ if tool.func else 'None'}")

print("\n" + "="*60)
print("\n测试工具调用:")
print("=" * 60)

# 测试股票实时数据
print("\n1. 测试 get_stock_realtime")
try:
    result = enhanced_data_collector.get_stock_realtime("600519")
    print(f"✅ 成功获取茅台实时数据:")
    print(f"   股票: {result.get('name')}")
    print(f"   价格: {result.get('price')}")
    print(f"   涨跌幅: {result.get('change_percent')}%")
except Exception as e:
    print(f"❌ 失败: {e}")

    import traceback
    traceback.print_exc()

# 测试股票历史数据
print("\n2. 测试 get_stock_history")
try:
    result = enhanced_data_collector.get_stock_history("600519", days=5)
    print(f"✅ 成功获取茅台历史数据:")
    print(f"   数据条数: {len(result)}")
    if result:
        print(f"   最新数据: {result[-1]}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试市场指数
print("\n3. 测试 get_market_index")
try:
    result = enhanced_data_collector.get_market_index()
    print(f"✅ 成功获取市场指数数据:")
    print(f"   指数数量: {len(result)}")
    if result:
        print(f"   第一个指数: {result[0].get('name')}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试新闻搜索
print("\n4. 测试 search_news")
try:
    result = enhanced_data_collector.search_news("茅台", max_results=3)
    print(f"✅ 成功获取茅台新闻:")
    print(f"   新闻数量: {len(result)}")
    if result:
        print(f"   第一条新闻: {result[0].get('title')}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试公司信息
print("\n5. 测试 get_company_info")
try:
    result = enhanced_data_collector.get_company_info("600519")
    print(f"✅ 成功获取茅台公司信息:")
    print(f"   公司名: {result.get('company_name')}")
    print(f"   行业: {result.get('industry')}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试股东信息
print("\n6. 测试 get_top_shareholders")
try:
    result = enhanced_data_collector.get_top_shareholders("600519")
    print(f"✅ 成功获取茅台股东信息:")
    print(f"   股东数量: {len(result)}")
    if result:
        print(f"   第一大股东: {result[0].get('shareholder')}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

# 测试财务数据
print("\n7. 测试 get_financial_data")
try:
    result = enhanced_data_collector.get_financial_data("600519", "profit")
    print(f"✅ 成功获取茅台财务数据:")
    print(f"   数据源: {result.get('source')}")
    print(f"   利润数据条数: {len(result.get('profit', []))}")
    if result.get('profit'):
        print(f"   最新利润: {result['profit'][-1]}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("测试完成")
print("=" * 60)
