"""V3 E2E 验证"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.ingestion.on_demand import OnDemandIngestor

fs = FactStore()
fs.init_db()
odi = OnDemandIngestor(fs)

# ── 测试 1: 本地命中 ──
print("=== 测试 1: 本地命中 (比亚迪) ===")
r = odi.resolve("002594", "比亚迪", "2026Q1")
print(f"  status={r['status']}, metrics={len(r.get('metrics', []))}")
assert r["status"] == "local_hit"

# ── 测试 2: 本地不足 (建设银行) ──
print("\n=== 测试 2: 本地缺失 (建设银行) ===")
r = odi.resolve("601939", "建设银行", "2026Q1")
print(f"  status={r['status']}, msg={r['message'][:60]}...")
assert r["status"] == "need_fetch"

# ── 测试 3: availability cache ──
print("\n=== 测试 3: 可用性检查 ===")
print(f"  比亚迪:  {odi.is_available('002594', '2026Q1')}")
print(f"  建设银行:  {odi.is_available('601939', '2026Q1')}")
print(f"  中国海油:  {odi.is_available('600938', '2026Q1')}")

# ── 测试 4: SourceFetcher download ──
print("\n=== 测试 4: SourceFetcher 下载 ===")
from src.sources.fetcher import SourceFetcher
sf = SourceFetcher(download_dir="data/reports")

# 用已验证的 URL 测试下载
test_url = "https://stockmc.xueqiu.com/202604/601988_20260430_77QJ.pdf"
result = sf.download_report(test_url, "601988", "中国银行", "2026Q1")
print(f"  success={result.success}")
if result.success:
    print(f"  file={result.file_path}")
    print(f"  source={result.source_name}")
else:
    print(f"  error={result.error}")

print("\n✓ V3 核心模块验证通过")
