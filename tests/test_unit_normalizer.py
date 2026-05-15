"""unit_normalizer 单元测试"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.ingestion.unit_normalizer import UnitNormalizer

un = UnitNormalizer()

print("=== _parse_number 测试 ===")
assert un._parse_number("123.45") == 123.45
assert un._parse_number("1,502,253.14") == 1502253.14
assert un._parse_number("(123.45)") == -123.45
assert un._parse_number("（123.45）") == -123.45
assert un._parse_number("-500") == -500
assert un._parse_number("") is None
assert un._parse_number(None) is None
assert un._parse_number("   ") is None
print("  ✓ 8/8")

print("\n=== normalize 测试 ===")
# 万元 → 元
r = un.normalize("1,502,253.14", "万元")
assert abs(r["value"] - 15022531400.0) < 0.01, f"got {r['value']}"
assert r["scale"] == 10000
print(f"  ✓ 万元: 1502.25万元 = {r['value']/1e8:.2f}亿元")

# 元
r = un.normalize("150225314000.00", "元")
assert r["value"] == 150225314000.00
print(f"  ✓ 元: = {r['value']/1e8:.2f}亿元")

# 亿元
r = un.normalize("1502.25", "亿元")
assert r["value"] == 150225000000.00, f"got {r['value']}"
print(f"  ✓ 亿元: 1502.25亿元 = {r['value']/1e8:.2f}亿元")

# %
r = un.normalize("18.8", "%")
assert r["value"] == 18.8
print(f"  ✓ %: 18.8%")

# 括号负数
r = un.normalize("(50.00)", "万元")
assert r["value"] == -500000.0, f"got {r['value']}"
print(f"  ✓ 括号负数万元: (50.00)万元 = {r['value']:.1f}")

# 千元
r = un.normalize("100", "千元")
assert r["value"] == 100000
print(f"  ✓ 千元: 100千元 = {r['value']}")

print("\n=== detect_unit 测试 ===")
assert un.detect_unit("单位：万元") == "万元"
assert un.detect_unit("单位: 元") == "元"
assert un.detect_unit("普通文本无单位") is None
print("  ✓ 3/3")

print("\n✓ test_unit_normalizer 全部通过")
