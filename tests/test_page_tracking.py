"""验证页码追踪 + unknown_metric + extraction_error"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.tools.file_processor import FileProcessor
from src.ingestion.report_ingestor import ReportIngestor
import json

fs = FactStore()
fs.init_db()
fs.seed_metric_dictionary()

fp = FileProcessor()
byd_pdf = "/home/wjh/FinIntel-Multi-Agent/data/byd_2026_1.pdf"

# ── 1. 逐页提取 ──
pages = fp._extract_pdf_pages(byd_pdf)
print(f"[1] PDF 页数: {len(pages)}")
for pn, text in pages[:3]:
    print(f"   第{pn}页: {len(text)} 字符")

# ── 2. 逐页指标提取 ──
content = "\n".join(t for _, t in pages)
metrics, metrics_pages = fp._extract_financial_metrics(content, byd_pdf, pages)
print(f"\n[2] 提取指标: {len(metrics)} 个")
print(f"   有页码的: {len(metrics_pages)} 个")
for k, v in list(metrics_pages.items())[:10]:
    print(f"   {k}: 第{v}页")

# ── 3. 入库 (带页码) ──
ri = ReportIngestor(fs)
result = ri.ingest(
    file_path=byd_pdf,
    ticker="002594",
    company_name="比亚迪",
    report_period="2026Q1",
    raw_metrics=metrics,
    raw_text=content,
    metrics_pages=metrics_pages,
)
print(f"\n[3] 入库: {json.dumps(result, ensure_ascii=False)}")

# ── 4. 验证 source_page ──
print(f"\n[4] SQL 中 source_page 验证:")
test_keys = ["revenue", "net_profit", "financial_expense", "rd_expense", "total_assets"]
for mc in test_keys:
    row = fs.query_metric("002594", "2026Q1", mc)
    if row:
        sp = row.get("source_page", "NULL")
        status = f"第{sp}页" if sp else "无页码"
        print(f"   {mc}: {row['value']/1e8:.2f}亿  {status}")
    else:
        print(f"   {mc}: SQL MISS")

# ── 5. 检查 unknown_metric 表 ──
with fs._get_conn() as conn:
    unk = conn.execute("SELECT COUNT(*) as cnt FROM unknown_metric").fetchone()
    errs = conn.execute("SELECT COUNT(*) as cnt FROM extraction_error").fetchone()
print(f"\n[5] unknown_metric 表: {unk['cnt']} 条")
print(f"    extraction_error 表: {errs['cnt']} 条")

# ── 6. 检查前几条 unknown_metric ──
if unk["cnt"] > 0:
    with fs._get_conn() as conn:
        rows = conn.execute(
            "SELECT raw_metric_name, raw_value, source_page FROM unknown_metric LIMIT 5"
        ).fetchall()
    print("    前5条:")
    for r in rows:
        sp = f"第{r['source_page']}页" if r['source_page'] else "无"
        print(f"    - {r['raw_metric_name']}: {r['raw_value']} ({sp})")

print("\n✓ 页码追踪验证完成")
