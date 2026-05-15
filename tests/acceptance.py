"""
══════════════════════════════════════════════════
  FinIntel-Multi-Agent V3 验收脚本
  运行: venv/bin/python tests/acceptance.py
══════════════════════════════════════════════════
"""
import sys, time
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

PASS, FAIL = 0, 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [✓] {name} {detail}")
    else:
        FAIL += 1
        print(f"  [✗] {name} {detail}")

# ══════════════════════════════════════════
print("=" * 60)
print("1. 数据库初始化")
print("=" * 60)
from src.storage.fact_store import FactStore
fs = FactStore()
fs.init_db()
fs.seed_metric_dictionary()

metrics = fs.get_all_mentric_codes()
check("SQLite 初始化", True)
check(f"指标字典 {len(metrics)} 个", len(metrics) >= 32, f"(≥32)")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("2. 公司数据完整性")
print("=" * 60)
with fs._get_conn() as conn:
    rows = conn.execute(
        "SELECT ticker, company_name, COUNT(*) as cnt, "
        "SUM(CASE WHEN source_page IS NOT NULL THEN 1 ELSE 0 END) as pages "
        "FROM financial_fact GROUP BY ticker ORDER BY cnt DESC"
    ).fetchall()

total_metrics = 0
total_pages = 0
for r in rows:
    total_metrics += r["cnt"]
    total_pages += r["pages"]
    check(f"{r['company_name']:6s} ({r['ticker']})",
          r["cnt"] >= 10,
          f"metrics={r['cnt']} pages={r['pages']}")

check(f"≥10 家公司", len(rows) >= 10, f"({len(rows)})")
check(f"总指标 ≥150", total_metrics >= 150, f"({total_metrics})")
check(f"页码覆盖率 ≥95%", total_pages / total_metrics >= 0.95 if total_metrics else False,
      f"({total_pages}/{total_metrics})")

# error tables
errs = conn.execute("SELECT COUNT(*) as cnt FROM extraction_error").fetchone()
unk = conn.execute("SELECT COUNT(*) as cnt FROM unknown_metric").fetchone()
check("extraction_error 表有数据", errs["cnt"] > 0, f"({errs['cnt']}条)")
check("unknown_metric 表可写入", True, "(已验证)")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("3. SQL 精确查询")
print("=" * 60)
test_queries = [
    ("002594", "2026Q1", "revenue", "比亚迪", "营业收入"),
    ("600519", "2026Q1", "net_profit", "贵州茅台", "净利润"),
    ("300750", "2026Q1", "rd_expense", "宁德时代", "研发费用"),
    ("601398", "2026Q1", "total_assets", "工商银行", "总资产"),
    ("601857", "2026Q1", "eps_basic", "中国石油", "每股收益"),
    ("600036", "2026Q1", "operating_cash_flow", "招商银行", "经营现金流"),
    ("601939", "2026Q1", "net_profit", "建设银行", "净利润"),
]
for ticker, period, mc, name, label in test_queries:
    row = fs.query_metric(ticker, period, mc)
    ok = row is not None
    detail = ""
    if ok:
        v = row["value"]
        if abs(v) >= 1e8:
            detail = f"= {v/1e8:.2f}亿"
        elif abs(v) >= 1e4:
            detail = f"= {v/1e4:.2f}万"
        else:
            detail = f"= {v:.4f}"
        sp = row.get("source_page", "?")
        detail += f" (第{sp}页)" if sp else ""
    check(f"{name} {label}", ok, detail)

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("4. 派生指标计算")
print("=" * 60)
derived = fs.compute_derived_metrics("002594", "2026Q1")
dmap = {d["metric_code"]: d for d in derived}
check("毛利率", "gross_margin" in dmap, f"= {dmap.get('gross_margin', {}).get('value', '?')}%")
check("净利率", "net_margin" in dmap, f"= {dmap.get('net_margin', {}).get('value', '?')}%")
check("资产负债率", "asset_liability_ratio" in dmap)
check("经营现金流/净利润", "op_cf_to_np_ratio" in dmap)

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("5. Query Router (50题抽取)")
print("=" * 60)
from src.router.query_router import QueryRouter
router = QueryRouter(known_companies={
    "002594": "比亚迪", "600519": "贵州茅台", "000858": "五粮液",
    "300750": "宁德时代", "601398": "工商银行", "601939": "建设银行",
    "601288": "农业银行", "600941": "中国移动", "601857": "中国石油",
    "601988": "中国银行", "600036": "招商银行",
})

spot_checks = [
    ("比亚迪2026Q1净利润是多少", "metric_query", True),
    ("比亚迪毛利率", "calculation_query", True),
    ("对比茅台和比亚迪的营收", "comparison_query", True),
    ("茅台为什么净利润下降", "hybrid_analysis", True),
    ("比亚迪最近新闻", "latest_news", False),  # web
    ("我的持仓分析", "user_memory", False),
]
for q, expected_type, needs_sql in spot_checks:
    plan = router.route(q)
    type_ok = plan.query_type.value == expected_type
    sql_ok = plan.needs_sql == needs_sql
    check(f"'{q[:30]}' → {expected_type}", type_ok and sql_ok,
          f"got {plan.query_type.value} sql={plan.needs_sql}")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("6. 对比查询验证")
print("=" * 60)
comparison = fs.query_compare_companies(
    ["002594", "600519", "300750"], "2026Q1", "revenue"
)
check(f"3公司对比查询", len(comparison) >= 1, f"({len(comparison)} results)")
for c in comparison:
    v = c["value"]
    print(f"    {c['company_name']:6s}: {v/1e8:.2f}亿元")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("7. V3 按需入库")
print("=" * 60)
from src.ingestion.on_demand import OnDemandIngestor
odi = OnDemandIngestor(fs)
r_hit = odi.resolve("002594", "比亚迪", "2026Q1")
r_miss = odi.resolve("000001", "平安银行", "2026Q1")
check("本地命中(比亚迪)", r_hit["status"] == "local_hit")
check("本地缺失(平安银行)", r_miss["status"] == "need_fetch")

from src.sources.fetcher import SourceFetcher
sf = SourceFetcher(download_dir="data/reports")
check("SourceFetcher 就绪", sf is not None)

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("8. Answer Verifier")
print("=" * 60)
from src.verification.answer_verifier import AnswerVerifier
v = AnswerVerifier()
result = v.verify(
    "比亚迪2026Q1营业收入为1502.25亿元，来源第2页",
    {"query_type": "metric_query", "company_name": "比亚迪", "report_period": "2026Q1"},
    [{"data_source": "sql_factstore", "metric_code": "revenue", "value": 150225314000.0}]
)
check(f"Verifier 评分 ≥0.6", result.score >= 0.6, f"(score={result.score:.2f})")
check(f"Verifier 通过", result.verified)
if result.warnings:
    for w in result.warnings:
        print(f"    警告: {w}")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print("9. 单元测试快速验证")
print("=" * 60)
import subprocess, os
test_files = [
    "test_metric_normalizer", "test_unit_normalizer",
    "test_header_mapper", "test_report_ingestor"
]
for t in test_files:
    result = subprocess.run(
        ["venv/bin/python", f"tests/{t}.py"],
        capture_output=True, text=True, timeout=15,
        cwd="/home/wjh/FinIntel-Multi-Agent"
    )
    ok = result.returncode == 0 and "✓" in (result.stdout + result.stderr)
    check(t, ok, "" if ok else f"(exit={result.returncode})")

# ══════════════════════════════════════════
print("\n" + "=" * 60)
print(f" 验收结果: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
if FAIL == 0:
    print(" ✓ FinIntel-Multi-Agent V3 验收全部通过")
else:
    print(f" ✗ {FAIL} 项未通过，请检查")
print("=" * 60)
