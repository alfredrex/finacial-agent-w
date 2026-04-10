#!/usr/bin/env python3
"""测试财务数据获取 - 详细调试"""

import sys
sys.path.insert(0, '.')

from src.tools.enhanced_data_collector import EnhancedDataCollector
import json

collector = EnhancedDataCollector()
print('测试财务数据获取...\n')

# 测试各个数据源
print('1. 测试akshare数据源:')
result = collector._safe_akshare_call(collector._akshare_financial, '600519', 'profit')
if result:
    print(f'  成功，数据: {json.dumps(result, indent=2, ensure_ascii=False, default=str)[:300]}')
else:
    print('  失败')

print('\n2. 测试东方财富数据源:')
result = collector._eastmoney_financial('600519', 'profit')
if result:
    print(f'  成功，数据: {json.dumps(result, indent=2, ensure_ascii=False, default=str)[:300]}')
else:
    print('  失败')

print('\n3. 测试新浪财经数据源:')
result = collector._sina_financial('600519', 'profit')
if result:
    print(f'  成功，数据: {json.dumps(result, indent=2, ensure_ascii=False, default=str)[:500]}')
else:
    print('  失败')

print('\n4. 测试腾讯财经数据源:')
result = collector._tencent_financial('600519', 'profit')
if result:
    print(f'  成功，数据: {json.dumps(result, indent=2, ensure_ascii=False, default=str)[:300]}')
else:
    print('  失败')

print('\n5. 测试模拟数据:')
result = collector._mock_financial_data('600519', 'profit')
print(f'  数据源: {result.get("source")}')
print(f'  利润数据条数: {len(result.get("profit", []))}')
if result.get('profit'):
    print(f'  最新利润: {result["profit"][-1]}')

print('\n6. 测试完整流程:')
result = collector.get_financial_data('600519', 'profit')
print(f'  最终数据源: {result.get("source")}')
print(f'  利润数据条数: {len(result.get("profit", []))}')
if result.get('profit'):
    print(f'  最新利润: {result["profit"][-1]}')
