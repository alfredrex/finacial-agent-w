#!/usr/bin/env python3
"""
图表生成模块
使用 matplotlib 和 mplfinance 生成各类金融图表
"""

import os
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端，避免GUI问题
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np

# 设置环境变量避免OpenMP警告
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

# 尝试导入mplfinance，如果失败则使用备用方案
try:
    import mplfinance as mpf
    HAS_MPLFINANCE = True
except ImportError:
    HAS_MPLFINANCE = False
    print("[WARNING] mplfinance未安装，K线图功能将受限")

import pandas as pd

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

COLORS = {
    'up': '#E74C3C',
    'down': '#2ECC71',
    'primary': '#3498DB',
    'secondary': '#95A5A6',
    'accent': '#F39C12'
}

OUTPUT_DIR = "output/charts"

def ensure_output_dir():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

def generate_kline_chart(symbol: str, days: int = 60, data: list = None) -> str:
    """
    生成K线图（蜡烛图）
    
    Args:
        symbol: 股票代码
        days: 天数
        data: K线数据列表，格式: [{"date": "2024-01-01", "open": 100, "high": 105, "low": 98, "close": 103, "volume": 1000000}, ...]
    
    Returns:
        图片路径
    """
    ensure_output_dir()
    
    if data is None or len(data) == 0:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        placeholder_path = os.path.join(OUTPUT_DIR, f"kline_{symbol}_{timestamp}_placeholder.png")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, f'K线图\n{symbol}\n最近{days}天\n\n(需要实际数据)', 
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(f'{symbol} K线图', fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(placeholder_path, dpi=100, bbox_inches='tight')
        plt.close()
        return placeholder_path
    
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    df = df[['open', 'high', 'low', 'close', 'volume']]
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"kline_{symbol}_{timestamp}.png")
    
    mc = mpf.make_marketcolors(
        up=COLORS['up'],
        down=COLORS['down'],
        edge='inherit',
        wick='inherit',
        volume='in',
    )
    s = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', gridcolor=COLORS['secondary'])
    
    mpf.plot(
        df,
        type='candle',
        style=s,
        title=f'{symbol} K线图',
        ylabel='价格',
        ylabel_lower='成交量',
        volume=True,
        figsize=(12, 6),
        savefig=output_path
    )
    
    return output_path

def generate_trend_chart(data: dict) -> str:
    """
    生成趋势图（折线图）
    
    Args:
        data: {
            "dates": ["2024-01-01", "2024-01-02", ...],
            "values": [100, 102, 98, ...],
            "title": "股价走势",
            "ylabel": "价格"
        }
    
    Returns:
        图片路径
    """
    ensure_output_dir()
    print(f"[DEBUG] generate_trend_chart 接收到的data: {data}")
    
    dates = data.get('dates', [])
    values = data.get('values', [])
    title = data.get('title', '趋势图')
    ylabel = data.get('ylabel', '值')
    
    print(f"[DEBUG] dates: {dates}, values: {values}, title: {title}")
    
    if not dates or not values:
        print(f"[DEBUG] 数据为空，生成占位图")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        placeholder_path = os.path.join(OUTPUT_DIR, f"trend_{timestamp}_placeholder.png")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, f'趋势图\n{title}\n\n(需要实际数据)', 
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(placeholder_path, dpi=100, bbox_inches='tight')
        plt.close()
        print(f"[DEBUG] 占位图已保存: {placeholder_path}")
        return placeholder_path
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"trend_{timestamp}.png")
    print(f"[DEBUG] 准备生成图片: {output_path}")
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    x = range(len(dates))
    # 绘制标准折线图，不填充
    ax.plot(x, values, color=COLORS['primary'], linewidth=2, marker='o', markersize=6, markerfacecolor='white', markeredgewidth=2, markeredgecolor=COLORS['primary'])
    
    # 添加数据标签
    for i, (xi, yi) in enumerate(zip(x, values)):
        ax.annotate(f'{yi:.1f}', (xi, yi), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9)
    
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel('日期', fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i] for i in x[::step]], rotation=45, ha='right')
    
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()
    
    print(f"[DEBUG] 图片已保存: {output_path}")
    return output_path

def generate_comparison_chart(data: dict) -> str:
    """
    生成对比图（柱状图）
    
    Args:
        data: {
            "categories": ["茅台", "五粮液", "泸州老窖"],
            "series": {
                "营收": [100, 80, 60],
                "利润": [50, 40, 30]
            },
            "title": "白酒企业对比",
            "ylabel": "亿元"
        }
    
    Returns:
        图片路径
    """
    ensure_output_dir()
    
    categories = data.get('categories', [])
    series = data.get('series', {})
    title = data.get('title', '对比图')
    ylabel = data.get('ylabel', '值')
    
    if not categories or not series:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        placeholder_path = os.path.join(OUTPUT_DIR, f"comparison_{timestamp}_placeholder.png")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, f'对比图\n{title}\n\n(需要实际数据)', 
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(placeholder_path, dpi=100, bbox_inches='tight')
        plt.close()
        return placeholder_path
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"comparison_{timestamp}.png")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(categories))
    width = 0.8 / len(series)
    
    colors = [COLORS['primary'], COLORS['up'], COLORS['accent'], COLORS['secondary']]
    
    for i, (label, values) in enumerate(series.items()):
        offset = (i - len(series) / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=label, color=colors[i % len(colors)])
        
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                   f'{val}', ha='center', va='bottom', fontsize=8)
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('类别', fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.legend()
    
    ax.grid(True, linestyle=':', alpha=0.6, axis='y')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()
    
    return output_path

def generate_pie_chart(data: dict) -> str:
    """
    生成饼图
    
    Args:
        data: {
            "labels": ["股票", "债券", "现金"],
            "values": [60, 30, 10],
            "title": "资产配置"
        }
    
    Returns:
        图片路径
    """
    ensure_output_dir()
    
    labels = data.get('labels', [])
    values = data.get('values', [])
    title = data.get('title', '饼图')
    
    if not labels or not values:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        placeholder_path = os.path.join(OUTPUT_DIR, f"pie_{timestamp}_placeholder.png")
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.text(0.5, 0.5, f'饼图\n{title}\n\n(需要实际数据)', 
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(placeholder_path, dpi=100, bbox_inches='tight')
        plt.close()
        return placeholder_path
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"pie_{timestamp}.png")
    
    fig, ax = plt.subplots(figsize=(8, 8))
    
    colors = [COLORS['primary'], COLORS['up'], COLORS['accent'], COLORS['secondary'], '#9B59B6']
    
    wedges, texts, autotexts = ax.pie(
        values, 
        labels=labels, 
        autopct='%1.1f%%',
        colors=colors[:len(labels)],
        startangle=90,
        explode=[0.02] * len(labels)
    )
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()
    
    return output_path

def generate_table(data: list, title: str = "数据表格") -> str:
    """
    生成 Markdown 格式的表格
    
    Args:
        data: [{"列1": "值1", "列2": "值2", ...}, ...]
        title: 表格标题
    
    Returns:
        Markdown 格式的表格字符串
    """
    if not data:
        return f"### {title}\n\n暂无数据"
    
    headers = list(data[0].keys())
    
    md_lines = [f"### {title}\n"]
    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    
    for row in data:
        values = [str(row.get(h, "")) for h in headers]
        md_lines.append("| " + " | ".join(values) + " |")
    
    return "\n".join(md_lines)

def generate_multi_line_chart(data: dict) -> str:
    """
    生成多线趋势图
    
    Args:
        data: {
            "dates": ["2024-01", "2024-02", ...],
            "series": {
                "茅台": [100, 102, ...],
                "五粮液": [80, 82, ...]
            },
            "title": "股价走势对比",
            "ylabel": "价格"
        }
    
    Returns:
        图片路径
    """
    ensure_output_dir()
    
    dates = data.get('dates', [])
    series = data.get('series', {})
    title = data.get('title', '多线趋势图')
    ylabel = data.get('ylabel', '值')
    
    if not dates or not series:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        placeholder_path = os.path.join(OUTPUT_DIR, f"multiline_{timestamp}_placeholder.png")
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, f'多线趋势图\n{title}\n\n(需要实际数据)', 
                ha='center', va='center', fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(title, fontsize=14, fontweight='bold')
        plt.tight_layout()
        plt.savefig(placeholder_path, dpi=100, bbox_inches='tight')
        plt.close()
        return placeholder_path
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"multiline_{timestamp}.png")
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    colors = [COLORS['primary'], COLORS['up'], COLORS['accent'], COLORS['secondary'], '#9B59B6']
    markers = ['o', 's', '^', 'D', 'v']
    
    x = range(len(dates))
    
    for i, (label, values) in enumerate(series.items()):
        ax.plot(x, values, color=colors[i % len(colors)], linewidth=2, 
                marker=markers[i % len(markers)], markersize=4, label=label)
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel('日期', fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.legend()
    
    step = max(1, len(dates) // 10)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([dates[i] for i in x[::step]], rotation=45, ha='right')
    
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=100, bbox_inches='tight')
    plt.close()
    
    return output_path
