#!/usr/bin/env python3
"""
数据收集工具可用性测试脚本
测试 EnhancedDataCollector 中的所有数据收集工具
"""

import sys
import asyncio
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '.')

from src.tools.enhanced_data_collector import enhanced_data_collector


async def test_get_stock_realtime():
    """测试实时股价获取"""
    print("\n" + "="*60)
    print("测试 get_stock_realtime(600519)")
    print("="*60)
    
    try:
        result = enhanced_data_collector.get_stock_realtime("600519")
        print(f"结果类型: {type(result)}")
        print(f"结果内容:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        
        if "error" in result:
            print(f"❌ 工具调用失败: {result['error']}")
            return False
        else:
            print(f"✅ 工具调用成功")
            print(f"   股票: {result.get('name')} ({result.get('symbol')})")
            print(f"   价格: {result.get('price')}")
            print(f"   涨跌幅: {result.get('change_percent')}%")
            print(f"   数据源: {result.get('source')}")
            return True
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def test_get_stock_history():
    """测试历史股价获取"""
    print("\n" + "="*60)
    print("测试 get_stock_history(600519, days=5)")
    print("="*60)
    
    try:
        result = enhanced_data_collector.get_stock_history("600519", days=5)
        print(f"结果类型: {type(result)}")
        print(f"结果长度: {len(result)}")
        
        if result and "error" in result[0]:
            print(f"❌ 工具调用失败: {result[0]['error']}")
            return False
        elif result:
            print(f"✅ 工具调用成功，获取到 {len(result)} 条历史数据")
            print(f"   最近一条数据: {result[-1]}")
            return True
        else:
            print(f"⚠️  工具返回空结果")
            return False
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def test_get_market_index():
    """测试市场指数获取"""
    print("\n" + "="*60)
    print("测试 get_market_index()")
    print("="*60)
    
    try:
        result = enhanced_data_collector.get_market_index()
        print(f"结果类型: {type(result)}")
        print(f"结果长度: {len(result)}")
        
        if result and "error" in result[0]:
            print(f"❌ 工具调用失败: {result[0]['error']}")
            return False
        elif result:
            print(f"✅ 工具调用成功，获取到 {len(result)} 个指数")
            for idx in result[:3]:  # 显示前3个指数
                print(f"   {idx.get('name')}: {idx.get('price')} ({idx.get('change_percent')}%)")
            return True
        else:
            print(f"⚠️  工具返回空结果")
            return False
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def test_search_news():
    """测试新闻搜索"""
    print("\n" + "="*60)
    print("测试 search_news('茅台', max_results=3)")
    print("="*60)
    
    try:
        result = enhanced_data_collector.search_news("茅台", max_results=3)
        print(f"结果类型: {type(result)}")
        print(f"结果长度: {len(result)}")
        
        if result and "error" in result[0]:
            print(f"❌ 工具调用失败: {result[0]['error']}")
            return False
        elif result:
            print(f"✅ 工具调用成功，获取到 {len(result)} 条新闻")
            for i, news in enumerate(result[:2], 1):
                print(f"   新闻{i}: {news.get('title', '无标题')[:50]}...")
                print(f"      时间: {news.get('time')}")
                print(f"      来源: {news.get('source')}")
            return True
        else:
            print(f"⚠️  工具返回空结果")
            return False
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def test_get_company_info():
    """测试公司信息获取"""
    print("\n" + "="*60)
    print("测试 get_company_info('600519')")
    print("="*60)
    
    try:
        result = enhanced_data_collector.get_company_info("600519")
        print(f"结果类型: {type(result)}")
        print(f"结果内容:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        
        if "error" in result:
            print(f"❌ 工具调用失败: {result['error']}")
            return False
        else:
            print(f"✅ 工具调用成功")
            print(f"   公司: {result.get('company_name')}")
            print(f"   行业: {result.get('industry')}")
            print(f"   主营业务: {result.get('main_business', '')[:50]}...")
            return True
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def test_get_top_shareholders():
    """测试股东信息获取"""
    print("\n" + "="*60)
    print("测试 get_top_shareholders('600519')")
    print("="*60)
    
    try:
        result = enhanced_data_collector.get_top_shareholders("600519")
        print(f"结果类型: {type(result)}")
        print(f"结果长度: {len(result)}")
        
        if not result:
            print(f"⚠️  工具返回空结果")
            return False
        else:
            print(f"✅ 工具调用成功，获取到 {len(result)} 个股东")
            for shareholder in result[:3]:
                print(f"   {shareholder.get('rank')}. {shareholder.get('shareholder')}: {shareholder.get('ratio')}")
            return True
    except Exception as e:
        print(f"❌ 工具调用异常: {e}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("="*80)
    print("数据收集工具可用性测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    test_results = {}
    
    # 运行所有测试
    tests = [
        ("get_stock_realtime", test_get_stock_realtime),
        ("get_stock_history", test_get_stock_history),
        ("get_market_index", test_get_market_index),
        ("search_news", test_search_news),
        ("get_company_info", test_get_company_info),
        ("get_top_shareholders", test_get_top_shareholders),
    ]
    
    for test_name, test_func in tests:
        print(f"\n开始测试: {test_name}")
        result = await test_func()
        test_results[test_name] = result
        print(f"测试完成: {test_name} - {'✅ 通过' if result else '❌ 失败'}")
    
    # 输出总结报告
    print("\n" + "="*80)
    print("测试总结报告")
    print("="*80)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    print(f"总测试数: {total}")
    print(f"通过数: {passed}")
    print(f"失败数: {total - passed}")
    print(f"通过率: {passed/total*100:.1f}%")
    
    print("\n详细结果:")
    for test_name, result in test_results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    if passed == total:
        print("\n🎉 所有数据收集工具测试通过！")
    else:
        print("\n⚠️  部分工具测试失败，请检查网络连接和数据源可用性")
    
    return test_results


if __name__ == "__main__":
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试脚本运行异常: {e}")
        import traceback
        traceback.print_exc()