# 数据分析 Skill

## 功能说明

承载所有 MCP 工具、取数接口、计算脚本，通过 ReAct 循环取数、算指标。

---

## 可用工具

### 数据获取工具
| 工具 | 功能 | 参数 |
|------|------|------|
| `get_stock_realtime` | 获取实时行情 | symbol: 股票代码 |
| `get_stock_history` | 获取历史K线 | symbol: 股票代码, days: 天数 |
| `get_market_index` | 获取市场指数 | 无 |
| `search_news` | 搜索新闻 | keyword: 关键词, max_results: 结果数 |
| `get_company_info` | 获取公司信息 | symbol: 股票代码 |
| `get_top_shareholders` | 获取十大股东 | symbol: 股票代码 |

### 分析计算工具
| 工具 | 功能 | 参数 |
|------|------|------|
| `comprehensive_analysis` | 综合技术分析 | symbol: 股票代码 |
| `search_knowledge` | 搜索知识库 | query: 查询文本, k: 结果数 |

---

## 工作流程

### 1. 分析用户需求
判断需要哪些数据和分析

### 2. 获取数据
按需调用工具获取数据：
- 技术分析 → get_stock_history + comprehensive_analysis
- 基本面分析 → get_company_info + search_news
- 财务分析 → get_company_info

### 3. 计算指标
使用 comprehensive_analysis 计算技术指标

### 4. 输出结构化数据
整理成结构化格式，供后续深度分析使用

---

## 输出格式

```json
{
  "symbol": "股票代码",
  "realtime": {
    "price": 价格,
    "change": 涨跌额,
    "change_percent": 涨跌幅
  },
  "history": [
    {"date": "日期", "open": 开盘价, "close": 收盘价, "high": 最高价, "low": 最低价, "volume": 成交量}
  ],
  "analysis": {
    "trend": "趋势判断",
    "rsi": RSI值,
    "macd": MACD值,
    "volatility": 波动率,
    "max_drawdown": 最大回撤
  },
  "company": {
    "name": "公司名称",
    "industry": "行业",
    "main_business": "主营业务"
  },
  "news": [
    {"title": "标题", "content": "内容", "time": "时间"}
  ]
}
```

---

## 重要规则

1. **按需获取**：只获取分析需要的数据，不冗余获取
2. **数据优先级**：
   - rag_context（优先使用）
   - collected_data（次优先）
   - 工具调用（最后）
3. **数据不足时**：输出 NEED_MORE: DataAgent 请求更多数据
4. **完成标志**：数据收集完成后调用 finish()
