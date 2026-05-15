-- FinIntel-Multi-Agent SQLite FactStore
-- Version 1: 六张表

-- 公司基本信息
CREATE TABLE IF NOT EXISTS company (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    exchange TEXT,
    industry TEXT,
    sector TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 入库的财报文档
CREATE TABLE IF NOT EXISTS report_document (
    doc_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    company_name TEXT,
    report_period TEXT,
    report_type TEXT,          -- quarterly_report / annual_report
    file_path TEXT,
    source_url TEXT,
    upload_time TEXT,
    parse_status TEXT,         -- pending / done / partial / failed
    parser_version TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 指标字典（标准化映射）
CREATE TABLE IF NOT EXISTS metric_dictionary (
    metric_code TEXT PRIMARY KEY,
    standard_name TEXT NOT NULL,   -- 中文标准名: "营业收入"
    aliases TEXT,                  -- JSON数组: ["营业总收入","一、营业总收入"]
    statement_type TEXT,           -- income / balance_sheet / cash_flow
    value_type TEXT,               -- amount / ratio / per_share
    default_unit TEXT,             -- 元 / % / 元/股
    description TEXT,
    created_at TEXT,
    updated_at TEXT
);

-- 财务事实（核心表）
CREATE TABLE IF NOT EXISTS financial_fact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    ticker TEXT NOT NULL,
    company_name TEXT,
    report_period TEXT NOT NULL,
    report_type TEXT,

    statement_type TEXT,           -- income / balance_sheet / cash_flow
    metric_code TEXT NOT NULL,     -- 标准化指标名: revenue
    metric_name TEXT,              -- 中文标准名: "营业收入"
    raw_metric_name TEXT,          -- 原始名称: "一、营业总收入"

    value REAL,
    raw_value TEXT,                -- 原始字符串: "150,225,314,000.00"
    unit TEXT,                     -- 元 / 万元 / %
    currency TEXT DEFAULT 'CNY',
    scale INTEGER DEFAULT 1,       -- 相对"元"的倍率

    source_doc_id TEXT,
    source_page INTEGER,
    source_table_name TEXT,
    table_id TEXT,
    row_label TEXT,
    column_label TEXT,

    confidence REAL,
    extraction_method TEXT,        -- regex / table_parse / manual
    created_at TEXT,
    updated_at TEXT,

    UNIQUE(ticker, report_period, metric_code, source_doc_id)
);

-- 无法识别的指标（待审核）
CREATE TABLE IF NOT EXISTS unknown_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    ticker TEXT,
    company_name TEXT,
    report_period TEXT,
    source_doc_id TEXT,
    source_page INTEGER,
    source_table_name TEXT,

    raw_metric_name TEXT,
    raw_value TEXT,
    context_text TEXT,

    suggested_metric_code TEXT,
    confidence REAL,
    reviewed INTEGER DEFAULT 0,

    created_at TEXT,
    updated_at TEXT
);

-- 解析错误记录
CREATE TABLE IF NOT EXISTS extraction_error (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    doc_id TEXT,
    ticker TEXT,
    report_period TEXT,
    page INTEGER,
    table_id TEXT,

    error_type TEXT,
    raw_text TEXT,
    message TEXT,

    created_at TEXT
);

-- 入库任务记录
CREATE TABLE IF NOT EXISTS ingestion_job (
    job_id TEXT PRIMARY KEY,

    input_path TEXT,
    job_type TEXT,                -- single / batch
    status TEXT,                  -- running / done / failed

    total_docs INTEGER,
    success_docs INTEGER,
    failed_docs INTEGER,

    started_at TEXT,
    finished_at TEXT,
    error_message TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_financial_fact_ticker_period
    ON financial_fact(ticker, report_period);
CREATE INDEX IF NOT EXISTS idx_financial_fact_metric_code
    ON financial_fact(metric_code);
CREATE INDEX IF NOT EXISTS idx_financial_fact_source_doc
    ON financial_fact(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_unknown_metric_ticker
    ON unknown_metric(ticker, report_period);
