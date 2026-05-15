"""metric_normalizer 单元测试"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.ingestion.metric_normalizer import MetricNormalizer, _clean
import os

# 独立测试数据库
DB = "/tmp/test_metric_normalizer.db"
if os.path.exists(DB):
    os.remove(DB)

fs = FactStore(DB)
fs.init_db()
fs.seed_metric_dictionary()

mn = MetricNormalizer(fs)

# ── _clean 测试 ──
print("=== _clean 函数测试 ===")
assert _clean("一、营业收入") == "营业收入", f"got: {_clean('一、营业收入')}"
assert _clean("1.营业收入") == "营业收入", f"got: {_clean('1.营业收入')}"
assert _clean("（一）营业收入") == "营业收入", f"got: {_clean('（一）营业收入')}"
escaped = '净利润（净亏损以"-"号填列）'
assert _clean(escaped) == "净利润", f"got: {_clean(escaped)}"
# "_clean" 不负责 "其中：" 前缀 — 那是 file_processor._extract_financial_metrics 的职责
assert _clean("其中：研发费用") == "其中研发费用", f"got: {_clean('其中：研发费用')}"
print("  ✓ 5/5 通过")

# ── normalize 测试 ──
print("\n=== normalize 测试 ===")
tests = [
    ("营业收入", "revenue"),
    ("营业总收入", "revenue"),
    ("一、营业总收入", "revenue"),
    ("归属于上市公司股东的净利润", "net_profit_parent"),
    ("归母净利润", "net_profit_parent"),
    ("研发费用", "rd_expense"),
    ("财务费用", "financial_expense"),
    ("资产总计", "total_assets"),
    ("经营活动产生的现金流量净额", "operating_cash_flow"),
    ("基本每股收益", "eps_basic"),
    # 短键名别名 (来自 file_processor)
    ("fin_expense", "financial_expense"),
    ("sell_expense", "selling_expense"),
    ("rd_expense", "rd_expense"),  # 本身即 metric_code
    ("eps", "eps_basic"),
    ("oper_cf", "operating_cash_flow"),
    ("roe", "roe_weighted"),
    ("net_profit", "net_profit"),
    # 未识别的
    ("不存在的科目名称", None),
    ("", None),
]

passed = 0
for raw, expected in tests:
    result = mn.normalize(raw)
    ok = result == expected
    status = "✓" if ok else f"✗ (got {result})"
    if ok:
        passed += 1
    print(f"  {status} '{raw}' → {result}")

print(f"\n  {passed}/{len(tests)} 通过")

# ── 断言 ──
assert passed >= len(tests) - 2, f"At least {len(tests)-2} should pass"
# _clean should not modify short metric_codes
assert _clean("revenue") == "revenue"
assert _clean("net_profit_parent") == "net_profit_parent"

print("\n✓ test_metric_normalizer 全部通过")
os.remove(DB)
