#!/usr/bin/env python3
"""测试图表生成脚本"""

import sys
sys.path.insert(0, '.')

print("=" * 60)
print("测试图表生成脚本")
print("=" * 60)

# 测试1: 导入模块
print("\n【测试1】导入chart_generator模块...")
try:
    from src.skills.visualization_skill.scripts.chart_generator import (
        generate_trend_chart,
        generate_kline_chart,
        ensure_output_dir,
        OUTPUT_DIR
    )
    print("✅ 模块导入成功")
    print(f"   OUTPUT_DIR: {OUTPUT_DIR}")
except Exception as e:
    print(f"❌ 模块导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试2: 确保输出目录存在
print("\n【测试2】确保输出目录存在...")
try:
    ensure_output_dir()
    import os
    if os.path.exists(OUTPUT_DIR):
        print(f"✅ 输出目录已创建: {OUTPUT_DIR}")
    else:
        print(f"❌ 输出目录创建失败: {OUTPUT_DIR}")
except Exception as e:
    print(f"❌ 创建输出目录失败: {e}")
    import traceback
    traceback.print_exc()

# 测试3: 生成趋势图
print("\n【测试3】生成趋势图...")
try:
    test_data = {
        "dates": ["2023-Q1", "2023-Q2", "2023-Q3", "2023-Q4"],
        "values": [100.0, 105.0, 110.0, 115.0],
        "title": "茅台季度利润趋势图",
        "ylabel": "利润（亿元）"
    }
    print(f"   测试数据: {test_data}")
    
    image_path = generate_trend_chart(test_data)
    print(f"✅ 趋势图生成成功: {image_path}")
    
    # 检查文件是否存在
    import os
    if os.path.exists(image_path):
        file_size = os.path.getsize(image_path)
        print(f"   文件大小: {file_size} 字节")
    else:
        print(f"   ⚠️  文件不存在: {image_path}")
except Exception as e:
    print(f"❌ 生成趋势图失败: {e}")
    import traceback
    traceback.print_exc()

# 测试4: 生成K线图
print("\n【测试4】生成K线图...")
try:
    test_kline_data = [
        {"date": "2024-01-01", "open": 100, "close": 105, "high": 110, "low": 95, "volume": 10000},
        {"date": "2024-01-02", "open": 105, "close": 102, "high": 108, "low": 100, "volume": 12000},
        {"date": "2024-01-03", "open": 102, "close": 108, "high": 112, "low": 101, "volume": 15000},
    ]
    print(f"   测试数据: {len(test_kline_data)} 条K线数据")
    
    image_path = generate_kline_chart(symbol="600519", days=3, data=test_kline_data)
    print(f"✅ K线图生成成功: {image_path}")
    
    # 检查文件是否存在
    import os
    if os.path.exists(image_path):
        file_size = os.path.getsize(image_path)
        print(f"   文件大小: {file_size} 字节")
    else:
        print(f"   ⚠️  文件不存在: {image_path}")
except Exception as e:
    print(f"❌ 生成K线图失败: {e}")
    import traceback
    traceback.print_exc()

# 测试5: 列出生成的图片
print("\n【测试5】列出生成的图片...")
try:
    import os
    import glob
    
    png_files = glob.glob(os.path.join(OUTPUT_DIR, "*.png"))
    print(f"✅ 找到 {len(png_files)} 个PNG文件:")
    for i, file in enumerate(png_files[-5:], 1):  # 显示最近5个
        file_size = os.path.getsize(file)
        print(f"   {i}. {os.path.basename(file)} ({file_size} 字节)")
except Exception as e:
    print(f"❌ 列出文件失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
