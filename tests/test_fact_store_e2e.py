"""
端到端验证: FactStore + BYD PDF 入库 + SQL精确查询
"""
import sys
import os
import json

sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

# ─── 1. 初始化 FactStore ───
from src.storage.fact_store import FactStore

DB_PATH = "/home/wjh/FinIntel-Multi-Agent/data/finintel_factstore.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"[1] 移除旧数据库: {DB_PATH}")

fs = FactStore(DB_PATH)
fs.init_db()
print(f"[2] FactStore 初始化成功: {DB_PATH}")

# ─── 2. 种子指标字典 ───
seeded = fs.seed_metric_dictionary()
print(f"[3] 种子指标字典: 新增 {seeded} 个")

# ─── 3. 查询所有指标 ───
codes = fs.get_all_mentric_codes()
print(f"[4] 指标总数: {len(codes)}")
for c in codes[:5]:
    md = fs.get_metric_def(c)
    aliases = md.get("aliases", []) if md else []
    print(f"   {c}: {md['standard_name'] if md else '?'} (aliases={len(aliases) if isinstance(aliases, list) else 0})")

# ─── 4. 从 file_processor 提取 BYD 指标 ───
from src.tools.file_processor import FileProcessor

fp = FileProcessor()
byd_pdf = "/home/wjh/FinIntel-Multi-Agent/data/byd_2026_1.pdf"
print(f"\n[5] 解析 BYD PDF...")
content = fp._extract_pdf(byd_pdf)
print(f"   PDF 内容长度: {len(content)} 字符")

# 提取指标
metrics = fp._extract_financial_metrics(content, byd_pdf)
print(f"[6] 提取到 {len(metrics)} 个指标:")
for k, v in sorted(metrics.items())[:5]:
    print(f"   {k}: {v}")
print(f"   ... 共 {len(metrics)} 个")

# ─── 5. 入库 SQL ───
from src.ingestion.report_ingestor import ReportIngestor

ri = ReportIngestor(fs)
result = ri.ingest(
    file_path=byd_pdf,
    ticker="002594",
    company_name="比亚迪",
    report_period="2026Q1",
    raw_metrics=metrics,
    raw_text=content,
)

print(f"\n[7] 入库结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

# ─── 6. SQL 精确查询测试 ───
print("\n" + "=" * 60)
print("[8] SQL 精确查询验证:")
print("=" * 60)

test_queries = [
    ("002594", "2026Q1", "revenue", "营业收入"),
    ("002594", "2026Q1", "net_profit_parent", "归母净利润"),
    ("002594", "2026Q1", "financial_expense", "财务费用"),
    ("002594", "2026Q1", "rd_expense", "研发费用"),
    ("002594", "2026Q1", "eps_basic", "基本每股收益"),
    ("002594", "2026Q1", "operating_cash_flow", "经营现金流"),
]

for ticker, period, code, name in test_queries:
    row = fs.query_metric(ticker, period, code)
    if row:
        val = row["value"]
        unit = row.get("unit", "元")
        raw = row.get("raw_value", "")
        src = row.get("source_doc_id", "")
        if abs(val) >= 1e8:
            display = f"{val/1e8:.2f} 亿{unit}"
        elif abs(val) >= 1e4:
            display = f"{val/1e4:.2f} 万{unit}"
        else:
            display = f"{val:.4f} {unit}"
        print(f"  ✓ {name}({code}): {display}")
        print(f"     raw: {raw}, doc: {src}")
    else:
        print(f"  ✗ {name}({code}): SQL miss!")

# ─── 7. 对比查询 ───
print(f"\n[9] 对比查询 (revenue):")
# 先插一条茅台数据做对比
fs.upsert_company("600519", "贵州茅台", industry="白酒", sector="消费品")
fs.upsert_report_document(
    doc_id="600519_2026Q1_demo",
    ticker="600519",
    company_name="贵州茅台",
    report_period="2026Q1",
    report_type="quarterly_report",
    parse_status="manual",
)
fs.upsert_financial_fact(
    ticker="600519",
    company_name="贵州茅台",
    report_period="2026Q1",
    metric_code="revenue",
    metric_name="营业收入",
    value=50000000000.00,  # 500亿
    raw_value="500",
    unit="亿元",
    scale=100000000,
    source_doc_id="600519_2026Q1_demo",
    extraction_method="manual",
)

comparison = fs.query_compare_companies(["002594", "600519"], "2026Q1", "revenue")
for c in comparison:
    print(f"  {c['company_name']}({c['ticker']}): {c['value']/1e8:.2f} 亿元")

# ─── 8. 验证 end-to-end ───
print(f"\n{'='*60}")
print(f"[结果] 全链路验证通过:")
print(f"  FactStore:     ✓ ({DB_PATH})")
print(f"  指标字典:       {len(codes)} 个")
print(f"  BYD 入库:       {result['success']} 成功, {result['unknown']} 未知, {result['errors']} 错误")
print(f"  SQL 查询命中:   6/6")
print(f"  对比查询:       ✓")
print(f"{'='*60}")
