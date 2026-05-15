"""V3: 自动化建设银行 Q1 入库"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.ingestion.on_demand import OnDemandIngestor
from src.sources.fetcher import SourceFetcher

fs = FactStore(); fs.init_db()
odi = OnDemandIngestor(fs)
sf = SourceFetcher(download_dir="data/reports")

# ── Step 1: 检查 ──
print("[1] 检查建设银行 Q1 状态...")
r = odi.resolve("601939", "建设银行", "2026Q1")
print(f"    {r['status']}: {r['message']}")

if r["status"] == "need_fetch":
    # ── Step 2: 使用已知的有效 URL ──
    # 来源: 东方财富
    urls = [
        {"url": "https://pdf.dfcfw.com/pdf/H2_AN202604291821766584_1.pdf", "source": "东方财富"},
        {"url": "https://stockmc.xueqiu.com/202604/601939_20260430_JVLD.pdf", "source": "雪球"},
    ]

    print(f"\n[2] 尝试 {len(urls)} 个 URL...")
    result = odi.search_and_ingest("601939", "建设银行", "2026Q1", pdf_urls=urls)
    print(f"    结果: {result['status']}")
    if result["status"] in ("ingested", "downloaded"):
        print(f"    文件: {result.get('file_path', '?')}")
        print(f"    指标: {result.get('metrics_ingested', 0)}")
    else:
        print(f"    错误: {result.get('message', '?')}")
else:
    print("    已在本地，跳过")

# ── Step 3: 验证 ──
print(f"\n[3] 建设中银行指标数: {len(fs.query_metrics_by_company_period('601939', '2026Q1'))}")
print("✓ V3 on-demand 流程完成")
