"""header_mapper 单元测试"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.ingestion.header_mapper import HeaderMapper

hm = HeaderMapper()

print("=== map_headers 测试 ===")
# 标准利润表
r = hm.map_headers(["项目", "本期金额", "上期金额"])
print(f"  {'项目|本期金额|上期金额'}: {r}")
assert r.get("current") == 1, f"current should be 1, got {r.get('current')}"
assert r.get("previous") == 2, f"previous should be 2, got {r.get('previous')}"

# 标准资产负债表
r = hm.map_headers(["项目", "期末余额", "期初余额"])
print(f"  {'项目|期末余额|期初余额'}: {r}")
assert r.get("current_balance") == 1
assert r.get("previous_balance") == 2

# 带同比列
r = hm.map_headers(["项目", "本期金额", "上期金额", "同比增减"])
print(f"  {'项目|本期|上期|同比'}: {r}")
assert r.get("yoy") == 3
assert r.get("current") == 1

# 带日期格式 (2026年1-3月是current，2025年1-3月是previous)
r = hm.map_headers(["项目", "2026年1-3月", "2025年1-3月"])
print(f"  {'项目|2026年1-3月|2025年1-3月'}: {r}")
assert r.get("current") == 1, f"current expected 1, got {r}"
assert r.get("previous") == 2, f"previous expected 2, got {r}"

# 空表头
r = hm.map_headers([])
print(f"  空: {r}")
assert len(r) == 0

print("  ✓ 5/5")

print("\n=== infer_statement_type 测试 ===")
income_text = "营业收入 营业成本 销售费用 管理费用 研发费用 净利润 利润总额"
assert hm.infer_statement_type(income_text) == "income", hm.infer_statement_type(income_text)
print(f"  ✓ 利润表")

balance_text = "货币资金 应收账款 存货 固定资产 资产总计 负债合计 所有者权益"
assert hm.infer_statement_type(balance_text) == "balance_sheet", hm.infer_statement_type(balance_text)
print(f"  ✓ 资产负债表")

cashflow_text = "经营活动产生的现金流量净额 投资活动产生的现金流量 现金及现金等价物"
assert hm.infer_statement_type(cashflow_text) == "cash_flow", hm.infer_statement_type(cashflow_text)
print(f"  ✓ 现金流量表")

unknown_text = "公司简介 管理层讨论 风险提示"
assert hm.infer_statement_type(unknown_text) is None, hm.infer_statement_type(unknown_text)
print(f"  ✓ 非表格文本")

print("  ✓ 4/4")

print("\n=== detect_period_from_header 测试 ===")
assert hm.detect_period_from_header("2026年1-3月") == "2026Q1"
print(f"  ✓ 2026年1-3月 → 2026Q1")
assert hm.detect_period_from_header("2026年4-6月") == "2026Q2"
print(f"  ✓ 2026年4-6月 → 2026Q2")
assert hm.detect_period_from_header("2025年度") == "2025FY"
print(f"  ✓ 2025年度 → 2025FY")
assert hm.detect_period_from_header("没有日期") is None
print(f"  ✓ 无日期 → None")

print("  ✓ 4/4")

print("\n✓ test_header_mapper 全部通过")
