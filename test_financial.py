#!/usr/bin/env python3
"""测试财务数据获取"""

import sys
sys.path.insert(0, '.')

from src.tools.enhanced_data_collector import EnhancedDataCollector

collector = EnhancedDataCollector()
print('测试财务数据获取...')
result = collector.get_financial_data('600519', 'profit')
print(f'数据源: {result.get("source")}')
print(f'利润数据条数: {len(result.get("profit", []))}')
if result.get('profit'):
    print(f'最新利润数据: {result["profit"][-1]}')
    print(f'\n利润趋势:')
    for item in result["profit"][-4:]:
        print(f"  {item['date']}: {item['value']}亿元")
