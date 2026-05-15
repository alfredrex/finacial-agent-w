# FinIntel-Multi-Agent — 金融投研多智能体系统

基于 LangGraph 的金融分析系统，集成**四层混合记忆**、**遗忘机制**、**KVStore-SQL-RAG 三层数据架构**和**工具注册调用系统**，实现智能问答、数据分析和投研报告生成。

## 核心特性

### 四层混合记忆系统 (HybridMemorySystem)

| 层级 | 名称 | 存储引擎 | 内容 | 生命周期 |
|------|------|---------|------|---------|
| L1 | 瞬时记忆 | Python dict | 会话上下文、当前实体、最近股票 | 会话关闭即清 |
| L2 | 用户记忆 | kvstore (C/RESP) | 用户画像、关注列表、投资策略偏好 | 持久化，30天未访问自动清理 |
| L3 | 股票记忆 | kvstore (C/RESP) | 股票基础信息、行情快照、RAG文档ID | 行情7天过期，基础信息持久 |
| L4 | 语义记忆 | ChromaDB + BGE | 研报全文、财报文本、新闻长文 | 持久化，1年以上归档 |

检索策略：**短路优先** — 上层命中且足够时不再查下层，减少延迟。

### 遗忘机制 (ForgettingManager)

防止记忆膨胀和过时数据误导，四层各司其职：

| 层级 | 触发条件 | 策略 |
|------|---------|------|
| L1 | 会话关闭 | 全量清空 |
| L2 | 每次检索时检查 | 30天未访问的股票从关注列表移除；查询历史上限100条 |
| L3 | 行情读取时检查 | 价格快照超过7天 → 标记为过期，下次查询自动刷新 |
| L4 | 定时任务 | 研报/财报超过365天 → 归档到冷存储 |

### KVStore-SQL-RAG 三层数据架构

```
用户查询
   │
   ├── 1. KVStore CacheService (带TTL逻辑缓存)
   │       ├── quote: 5分钟
   │       ├── news: 1小时
   │       ├── announcement: 1天
   │       └── user_profile: 不过期
   │
   ├── 2. SQLite FactStore (结构化财报指标，唯一数据源)
   │       └── 11家公司 × 222条财务指标
   │
   └── 3. ChromaDB RAG (语义检索)
           └── BGE-small-zh-v1.5 嵌入 + 5步金融分块
```

**数据优先级**：`get_financial_data(东财API)` → `SQL FactStore` → `search_financial_web`

### 工具注册与调用系统

统一工具注册中心 (`ToolRegistry`)，支持 ReAct 模式的工具发现与调用：

```
ToolRegistry
├── DATA_STOCK      # get_stock_realtime, get_stock_history, get_market_index
├── DATA_NEWS       # search_news
├── DATA_COMPANY    # get_company_info, get_top_shareholders
├── DATA_FINANCIAL  # get_financial_data (东方财富API)
├── DATA_SEARCH     # search_financial_web (DuckDuckGo → PDF下载 → SQL入库)
├── RAG             # search_rag, ingest_document
├── MEMORY          # save_memory, recall_memory
├── FILE            # parse_pdf, parse_excel, download_file
└── ANALYSIS        # calculate_technical_indicators, generate_report
```

DataAgent 在 ReAct 循环中通过 `tool_registry.get_tools_prompt()` 获取可用工具列表，LLM 自主决策调用链路。

### SourceFetcher — 多源财报下载

自动搜索并下载上市公司财报 PDF，验证真伪后入库：

- 数据源：雪球、巨潮资讯、东方财富
- 下载验证：文件大小 + PDF header 检测
- 自动入库：PDF → 解析 → SQLite FactStore

### OnDemandIngestor — 按需知识摄入

当本地无数据时自动触发：
1. 外部搜索（DuckDuckGo API）
2. PDF 下载
3. 解析提取关键财务指标
4. 写入 SQLite FactStore + ChromaDB RAG

### Query Router — 智能路由

按问题类型自动决定数据源优先级：
- 行情类 → 缓存 → API
- 基本面 → SQL → API
- 深度研报 → RAG → 搜索 → SQL
- 新闻事件 → 搜索 → RAG

API 和 SQL 数据冲突时输出专业不一致提示，不静默覆盖。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                CoordinatorAgent (协调器)                      │
│   消息总线 + 黑板系统 → 多Agent协同                            │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Dispatcher   │    │  MemoryAgent  │    │   DataAgent   │
│   任务调度     │    │   记忆管理     │    │   数据收集     │
│   流程判断     │    │ 四层记忆检索   │    │  ReAct工具调用 │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      ┌───────────┐   ┌───────────┐   ┌───────────┐
      │ QAAgent   │   │ ReportAgent│   │ Evaluator │
      │  问答生成  │   │  报告生成  │   │  评估验证  │
      └───────────┘   └───────────┘   └───────────┘
```

### Agent 职责

| Agent | 功能 | 最大迭代 |
|-------|------|---------|
| CoordinatorAgent | 多Agent协同、消息总线、黑板系统 | — |
| DispatcherAgent | 任务类型判断、流程参数设置 | 1 |
| MemoryAgent | 四层记忆存储/检索、遗忘触发 | 5 |
| DataAgent | ReAct 工具调用、数据收集、联网搜索 | 15 |
| QAAgent | 融合记忆上下文的问答生成 | 5 |
| ReportAgent | 深度投研报告生成 | 5 |
| Evaluator | 答案质量评估（准确性、完整性、时效性） | — |

### 通信系统

```
MessageBus ─── 异步消息传递，Agent间解耦通信
Blackboard ─── 共享工作空间，中间结果发布/订阅
AgentRegistry ─── Agent发现与能力注册
```

## 数据源

| 数据类型 | 数据源 | 优先级 |
|---------|--------|--------|
| 实时行情 | 东方财富 > 新浪财经 > 腾讯财经 | 高→低 |
| 历史K线 | 东方财富 > 新浪财经 | 高→低 |
| 财务指标 | 东方财富 API > SQLite FactStore > DuckDuckGo搜索 | 高→低 |
| 公司信息 | 东方财富 > 新浪财经 | 高→低 |
| 研报/财报 | 雪球 > 巨潮资讯 > 东方财富 (PDF下载验证) | 高→低 |
| RAG检索 | ChromaDB (BGE嵌入) > DuckDuckGo → 下载入库 | 高→低 |

## 安装

### 1. 克隆仓库

```bash
git clone git@github.com:alfredrex/finacial-agent-w.git
cd FinIntel-Multi-Agent
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

### 4. 下载嵌入模型

```bash
# BGE-small-zh-v1.5 (约180MB)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder='./models')"
```

### 5. 配置环境变量

```bash
cp .env.example .env
```

`.env` 文件配置：

```env
# LLM API 配置 (必填)
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# 可选
TUSHARE_TOKEN=your_tushare_token_here
```

### 6. 初始化数据库

```bash
# 启动 kvstore (C语言键值存储)
cd kvstore && make && ./kvstore_server &
# 初始化 SQLite FactStore
python -c "from src.storage.fact_store import FactStore; FactStore().init_db()"
```

## 使用方法

### 启动系统

```bash
python main.py
```

### 示例查询

```
请输入问题: 茅台PE多少？和五粮液对比一下

请输入问题: 比亚迪2025年营收和净利润

请输入问题: 给我一份茅台深度分析报告

请输入问题: 分析新能源汽车行业最近动态
```

### 批量评测

```bash
# 标准问题集评测
python tests/v4_verify.py

# 端到端测试
python tests/v3_e2e.py
```

## 项目结构

```
FinIntel-Multi-Agent/
├── main.py                     # 主程序入口
├── .env.example                # 环境变量示例
├── .gitignore                  # Git忽略文件
├── requirements.txt            # 依赖列表
├── README.md                   # 说明文档
│
├── kvstore/                    # C语言键值存储服务
│   ├── kvstore_server          # 服务端
│   └── Makefile                # 编译脚本
│
├── src/
│   ├── config.py               # 配置管理
│   ├── state.py                # 全局状态定义
│   ├── workflow.py             # LangGraph 工作流
│   │
│   ├── agents/                 # 智能体
│   │   ├── coordinator_agent.py    # 多Agent协调器
│   │   ├── dispatcher_agent.py     # 任务调度
│   │   ├── memory_agent.py         # 记忆管理Agent
│   │   ├── data_agent.py           # 数据收集(ReAct)
│   │   ├── qa_agent.py             # 问答生成
│   │   └── base_agent.py           # Agent基类
│   │
│   ├── communication/          # 通信系统
│   │   ├── message_bus.py          # 异步消息总线
│   │   ├── blackboard.py           # 共享黑板
│   │   ├── agent_registry.py       # Agent注册中心
│   │   └── models.py               # 通信数据模型
│   │
│   ├── memory/                 # 四层记忆系统
│   │   ├── hybrid_memory.py        # 四层记忆统一入口
│   │   ├── working_memory.py       # L1 瞬时记忆
│   │   ├── episodic_memory.py      # L2 用户记忆(经历)
│   │   ├── semantic_memory.py      # L3 语义记忆
│   │   ├── user_memory.py          # 用户偏好记忆
│   │   ├── consolidator.py         # 记忆合并器
│   │   ├── forgetting.py           # 遗忘机制 (四层TTL)
│   │   ├── cache_service.py        # KVStore缓存(TTL)
│   │   ├── kvstore_client.py       # KVStore Python RESP客户端
│   │   ├── kvstore_memory.py       # KVStore记忆层封装
│   │   ├── data_source_pipeline.py # 数据源管线
│   │   └── models.py               # 记忆数据模型
│   │
│   ├── storage/                # SQLite 事实存储
│   │   ├── fact_store.py           # 财报指标唯一数据源
│   │   └── schema.sql              # 数据库Schema
│   │
│   ├── rag/                    # RAG 检索增强
│   │   ├── bge_embedder.py         # BGE嵌入模型封装
│   │   └── financial_chunker.py    # 金融文本5步分块
│   │
│   ├── router/                 # 查询路由
│   │   ├── query_router.py         # 智能路由决策
│   │   └── query_schema.py         # 查询类型定义
│   │
│   ├── sources/                # 数据源
│   │   └── fetcher.py              # 多源财报下载器
│   │
│   ├── ingestion/              # 数据摄入
│   │   ├── on_demand.py            # 按需摄入(搜索→下载→入库)
│   │   ├── batch_ingestor.py       # 批量摄入
│   │   ├── report_ingestor.py      # 财报摄入
│   │   ├── header_mapper.py        # 表头映射
│   │   ├── metric_normalizer.py    # 指标标准化
│   │   └── unit_normalizer.py      # 单位标准化
│   │
│   ├── tools/                  # 工具系统
│   │   ├── registry.py             # 工具注册中心
│   │   ├── register_tools.py       # 工具注册入口
│   │   ├── enhanced_data_collector.py # 数据采集工具
│   │   ├── financial_analyzer.py   # 财务分析工具
│   │   ├── rag_manager.py          # RAG管理工具
│   │   ├── file_processor.py       # 文件处理工具
│   │   └── web_search_tool.py      # DuckDuckGo联网搜索
│   │
│   ├── evaluation/             # 评估系统
│   │   └── evaluator.py            # 答案质量评估
│   │
│   └── verification/           # 验证系统
│       └── answer_verifier.py      # 答案验证器
│
├── tests/                      # 测试
│   ├── v4_verify.py                # 完整验证
│   ├── v3_e2e.py                   # V3端到端测试
│   ├── v2_eval.py                  # V2评估
│   ├── test_query_router.py        # 路由测试
│   ├── test_kvstore_client.py      # KVStore客户端测试
│   ├── test_hybrid_memory.py       # 混合记忆测试
│   └── ...                         # 其他测试文件
│
├── data/                       # 数据文件
│   ├── eval/                       # 评测数据集
│   └── finintel_factstore.db       # SQLite事实数据库
│
├── models/                     # 模型文件 (不提交)
├── output/                     # 输出目录
├── chromadb/                   # ChromaDB向量存储
└── reports/                    # 生成的报告
```

## API 获取

### DeepSeek API (推荐)

1. 访问 [DeepSeek官网](https://platform.deepseek.com/)
2. 注册账号并获取 API Key
3. 填入 `.env` 文件

### 东方财富 API (免费)

无需注册，系统内置直接调用。

### Tushare API (可选)

1. 访问 [Tushare官网](https://tushare.pro/)
2. 注册账号并获取 Token
3. 填入 `.env` 文件

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 编排框架 | LangGraph | 多Agent状态图编排 |
| LLM | DeepSeek / 豆包 | ReAct推理引擎 |
| 键值存储 | kvstore (C + RESP) | 自研高性能内存KV |
| 结构化存储 | SQLite | 财报指标唯一数据源 |
| 向量检索 | ChromaDB + BGE-small-zh | 研报语义搜索 |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 | 中文金融文本嵌入 |
| 数据采集 | 东方财富/雪球/巨潮 | 多源实时数据 |
| 联网搜索 | DuckDuckGo API | 增量信息检索 |
| 通信 | MessageBus + Blackboard | Agent间异步解耦通信 |

## 数据流全景

```
用户问题
   │
   ├── QueryRouter ─── 判断问题类型，决定数据源优先级
   │
   ├── CacheService (KVStore TTL) ─── 热点数据秒级返回
   │    ├── 命中 → 直接返回
   │    └── 未命中 ↓
   │
   ├── SQLite FactStore ─── 结构化财报数据
   │    ├── 命中 → 返回 + 写缓存
   │    └── 未命中 ↓
   │
   ├── 东方财富 API ─── 实时行情/财务指标
   │    ├── 成功 → 返回 + 写入 SQL
   │    └── 失败 ↓
   │
   ├── ChromaDB RAG ─── 研报/财报语义检索
   │    ├── 命中 → 返回 + 注入上下文
   │    └── 未命中 ↓
   │
   └── OnDemandIngestor ─── 按需搜索→下载→解析→入库
        └── DuckDuckGo 搜索 → PDF下载 → 提取指标 → SQL + RAG 双写

同时:
   MemoryAgent ─── 检索四层记忆，注入上下文
   ForgettingManager ─── 检查TTL，清理过期数据
```

## 注意事项

1. **API费用**: DeepSeek API 需要充值使用
2. **模型下载**: BGE 模型首次运行自动下载 (~180MB)，确保网络通畅
3. **kvstore**: 首次使用需编译 C 服务端 `cd kvstore && make`
4. **数据延迟**: 免费数据源可能有延迟，缓存TTL按数据类型分级
5. **网络问题**: 部分数据源可能需要代理访问

## License

MIT License
