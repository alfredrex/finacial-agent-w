---
name: financial-visualization
description: 金融数据可视化技能，生成K线图、趋势图、对比图、财务表格等专业图表
user-invocable: true
---

# 金融可视化 Skill

## 功能说明

将金融数据转换为专业图表和表格，包括：
- K线图（蜡烛图）
- 趋势图（折线图）
- 对比图（柱状图）
- 财务数据表格
- 综合仪表盘

## 触发条件

当任务涉及以下场景时自动激活：
- 需要生成图表展示数据
- 需要可视化分析结果
- 需要制作报告配图
- 用户明确要求"画图"、"生成图表"

## 可用脚本

### 1. generate_kline_chart
生成K线图（蜡烛图）

```python
# 参数
symbol: str      # 股票代码
days: int = 60   # 天数，默认60天
# 输出
# 保存图片到 output/charts/ 目录，返回图片路径
```

### 2. generate_trend_chart
生成趋势图（折线图）

```python
# 参数
data: dict       # 数据 {"dates": [...], "values": [...], "title": "..."}
# 输出
# 保存图片到 output/charts/ 目录，返回图片路径
```

### 3. generate_comparison_chart
生成对比图（柱状图）

```python
# 参数
data: dict       # 数据 {"categories": [...], "series": {"名称": [...], ...}, "title": "..."}
# 输出
# 保存图片到 output/charts/ 目录，返回图片路径
```

### 4. generate_table
生成格式化表格

```python
# 参数
data: list       # 表格数据 [{"列1": "值1", ...}, ...]
title: str       # 表格标题
# 输出
# 返回 Markdown 格式的表格字符串
```

## 工作流程

1. **分析数据类型**
   - 判断数据适合哪种图表类型
   - 确定图表的维度和指标

2. **选择图表类型**
   - 时间序列数据 → K线图/趋势图
   - 对比数据 → 柱状图/条形图
   - 结构数据 → 饼图/表格
   - 多维度数据 → 组合图

3. **生成图表**
   - 调用对应的脚本生成图片
   - 图片保存到 `output/charts/` 目录
   - 返回图片路径或 base64 编码

4. **插入报告**
   - 将图表路径插入到 QA 或 Report 中
   - Markdown 格式: `![图表标题](图片路径)`

## 图表设计规范

### 配色方案
- 上涨: #E74C3C (红色)
- 下跌: #2ECC71 (绿色)
- 主色调: #3498DB (蓝色)
- 辅助色: #95A5A6 (灰色)

### 字体规范
- 标题: 14pt 粗体
- 坐标轴: 10pt
- 图例: 9pt

### 图表尺寸
- 默认: 800x400 像素
- 报告配图: 600x300 像素
- 大图: 1200x600 像素

## 示例用法

### 示例1: 生成K线图
```
用户: 帮我画茅台最近30天的K线图

执行:
1. 调用 generate_kline_chart(symbol="600519", days=30)
2. 生成图片 output/charts/kline_600519_30d.png
3. 返回: ![茅台K线图](output/charts/kline_600519_30d.png)
```

### 示例2: 生成对比图
```
用户: 对比茅台和五粮液的营收

执行:
1. 准备数据
2. 调用 generate_comparison_chart(data)
3. 生成图片 output/charts/comparison_revenue.png
4. 返回: ![营收对比](output/charts/comparison_revenue.png)
```

### 示例3: 生成表格
```
用户: 把财务数据整理成表格

执行:
1. 调用 generate_table(data, title="财务数据")
2. 返回 Markdown 表格
```

## 注意事项

- 图片默认保存到 `output/charts/` 目录
- 图片命名格式: `{类型}_{股票代码}_{时间戳}.png`
- 表格使用 Markdown 格式，可直接嵌入报告
- 复杂图表建议使用 pyecharts 生成交互式 HTML
