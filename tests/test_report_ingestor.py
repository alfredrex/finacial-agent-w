"""report_ingestor 单元测试"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.ingestion.report_ingestor import ReportIngestor
import os, json

DB = "/tmp/test_report_ingestor.db"
if os.path.exists(DB):
    os.remove(DB)

fs = FactStore(DB)
fs.init_db()
fs.seed_metric_dictionary()
ri = ReportIngestor(fs)

# ── 测试 1: 正常入库 ──
print("=== 正常入库测试 ===")
raw_metrics = {
    "revenue": "150225314000.00",
    "net_profit": 4084551000.00,
    "financial_expense": 2099923000.00,
    "rd_expense": "11343566000.00",
}
pages = {"revenue": 2, "net_profit": 2, "financial_expense": 3, "rd_expense": 7}

result = ri.ingest(
    file_path="/tmp/test_byd.pdf",
    ticker="002594",
    company_name="比亚迪",
    report_period="2026Q1",
    raw_metrics=raw_metrics,
    metrics_pages=pages,
)
print(f"  {json.dumps(result, ensure_ascii=False)}")
assert result["success"] == 4, f"Expected 4, got {result['success']}"
assert result["unknown"] == 0
assert result["errors"] == 0
print("  ✓ 4/4 成功入库")

# 验证 source_page
for mc, expected_page in pages.items():
    row = fs.query_metric("002594", "2026Q1", mc)
    assert row is not None, f"{mc} not found"
    assert row.get("source_page") == expected_page, \
        f"{mc} page={row.get('source_page')}, expected={expected_page}"
print("  ✓ 页码验证通过")

# ── 测试 2: 未知指标 → unknown_metric ──
print("\n=== 未知指标测试 ===")
result = ri.ingest(
    file_path="/tmp/test_unknown.pdf",
    ticker="002594",
    company_name="比亚迪",
    report_period="2026Q1",
    raw_metrics={"合同负债": "5000000.00", "使用权资产": "3000000.00"},
)
print(f"  {json.dumps(result, ensure_ascii=False)}")
assert result["unknown"] == 2, f"Expected 2 unknown, got {result['unknown']}"
assert result["success"] == 0

# 验证 unknown_metric 表
with fs._get_conn() as conn:
    unk_rows = conn.execute(
        "SELECT raw_metric_name, raw_value FROM unknown_metric"
    ).fetchall()
    unk_names = [r["raw_metric_name"] for r in unk_rows]
    assert "合同负债" in unk_names
    assert "使用权资产" in unk_names
print(f"  ✓ unknown_metric: {[dict(r) for r in unk_rows]}")

# ── 测试 3: 解析错误 → extraction_error ──
print("\n=== 解析错误测试 ===")
result = ri.ingest(
    file_path="/tmp/test_bad.pdf",
    ticker="002594",
    company_name="比亚迪",
    report_period="2026Q1",
    raw_metrics={"bad_metric": "not_a_number"},
)
print(f"  {json.dumps(result, ensure_ascii=False)}")
assert result["errors"] == 1

with fs._get_conn() as conn:
    err_rows = conn.execute(
        "SELECT error_type, message FROM extraction_error"
    ).fetchall()
    assert len(err_rows) == 1
    assert err_rows[0]["error_type"] == "invalid_value"
print(f"  ✓ extraction_error: {[dict(r) for r in err_rows]}")

# ── 测试 4: 防重复入库 ──
print("\n=== 防重复测试 ===")
doc_id = ri._make_doc_id("002594", "2026Q1", "/tmp/test_byd.pdf")
assert ri.is_already_ingested(doc_id), "Should be already ingested"
print(f"  ✓ 防重复: doc_id={doc_id} is ingested")

new_doc_id = ri._make_doc_id("002594", "2026Q1", "/tmp/unknown.pdf")
assert not ri.is_already_ingested(new_doc_id)
print(f"  ✓ 未入库: doc_id={new_doc_id} not ingested")

print(f"\n✓ test_report_ingestor 全部通过")
os.remove(DB)
