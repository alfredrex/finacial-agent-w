# 金融投研问答与报告生成系统

基于 LangGraph 的多智能体金融分析系统，采用 ReAct 模式实现智能问答、数据分析和报告生成。

## 功能特性

- 📊 **股票行情查询** - 实时行情、历史K线、市场指数
- 📈 **技术指标计算** - MA、MACD、RSI、KDJ等技术指标
- 📝 **投研报告生成** - 自动生成深度研究报告
- 📄 **文档解析** - 支持PDF、Word、Excel等文档解析
- 🔍 **财务数据分析** - 利润表、资产负债表、现金流量表
- 📉 **可视化图表** - K线图、趋势图、对比图、表格

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户输入                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   DispatcherAgent (调度器)                   │
│  判断任务类型，设置流程参数                                   │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  DataAgent    │    │ AnalysisAgent │    │Visualization  │
│  数据收集      │───▶│  数据分析      │───▶│    Agent      │
│  (最大15轮)    │    │  (最大10轮)    │    │   可视化      │
└───────────────┘    └───────────────┘    └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   ReportAgent / QAAgent                      │
│                      生成最终输出                            │
└─────────────────────────────────────────────────────────────┘
```

## 数据源

| 数据类型 | 数据源 | 优先级 |
|---------|--------|--------|
| 实时行情 | Tushare > 新浪财经 > 腾讯财经 | 高→低 |
| 历史K线 | Tushare > 东方财富 > 新浪财经 | 高→低 |
| 公司信息 | 东方财富 > 新浪财经 > 腾讯财经 | 高→低 |
| 股东信息 | Tushare > 东方财富 | 高→低 |
| 财务数据 | 东方财富 > 新浪财经 > 腾讯财经 | 高→低 |

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/mjhxyx/FinIntel-Multi-Agent
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
.\venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑.env文件，填入你的API密钥
```

`.env` 文件配置：

```env
# LLM API 配置 (必填)
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# Tushare API Token (可选，用于股票数据)
TUSHARE_TOKEN=your_tushare_token_here
```

## 使用方法

### 启动系统

```bash
python main.py
```

### 示例查询

```
请输入问题: 茅台股价多少？

请输入问题: 画茅台K线图

请输入问题: 茅台深度报告

请输入问题: 分析600519的技术指标
```

## 项目结构

```
jinrongagent/
├── main.py                 # 主程序入口
├── .env                    # 环境变量配置 (不提交)
├── .env.example            # 环境变量示例
├── .gitignore              # Git忽略文件
├── requirements.txt        # 依赖列表
├── README.md               # 说明文档
│
├── src/
│   ├── config.py           # 配置管理
│   ├── workflow.py         # 工作流定义
│   │
│   ├── agents/             # 智能体
│   │   ├── base_agent.py       # 基础智能体
│   │   ├── dispatcher_agent.py # 调度器
│   │   ├── data_agent.py       # 数据收集
│   │   ├── analysis_agent.py   # 数据分析
│   │   ├── visualization_agent.py # 可视化
│   │   ├── report_agent.py     # 报告生成
│   │   └── qa_agent.py         # 问答
│   │
│   ├── tools/              # 工具
│   │   ├── enhanced_data_collector.py # 数据收集器
│   │   ├── financial_analyzer.py      # 财务分析
│   │   ├── rag_manager.py             # 知识库管理
│   │   └── register_tools.py          # 工具注册
│   │
│   └── skills/             # 技能模块
│       └── visualization_skill/
│           └── scripts/
│               └── chart_generator.py  # 图表生成
│
├── output/                 # 输出目录
│   └── charts/             # 生成的图表
│
├── chromadb/               # 向量数据库
│
└── reports/                # 生成的报告
```

## Agent 说明

| Agent | 功能 | 最大迭代次数 |
|-------|------|-------------|
| DispatcherAgent | 任务调度、流程判断 | 1 |
| DataAgent | 数据收集、新闻搜索 | 15 |
| AnalysisAgent | 技术分析、深度分析 | 10 |
| VisualizationAgent | 图表生成 | 3 |
| ReportAgent | 报告生成 | 3 |
| QAAgent | 问答生成 | 3 |

## API 获取

### DeepSeek API (推荐)

1. 访问 [DeepSeek官网](https://platform.deepseek.com/)
2. 注册账号并获取API Key
3. 填入 `.env` 文件

### Tushare API (可选)

1. 访问 [Tushare官网](https://tushare.pro/)
2. 注册账号并获取Token
3. 填入 `.env` 文件

## 注意事项

1. **API费用**: DeepSeek API 需要充值使用
2. **数据延迟**: 免费数据源可能有延迟
3. **网络问题**: 部分数据源可能需要代理

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
