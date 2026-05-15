"""五粮液 on-demand 入库"""
import sys, os, requests
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.storage.fact_store import FactStore
from src.ingestion.on_demand import OnDemandIngestor
from src.sources.fetcher import SourceFetcher

fs = FactStore(); fs.init_db()
sf = SourceFetcher(download_dir="data/reports")
odi = OnDemandIngestor(fs)

# 1. 检查
print("[1] 五粮液状态...")
r = odi.resolve("000858", "五粮液", "2026Q1")
print(f"    {r['status']}: {r['message']}")

# 2. 下载
print("\n[2] 下载 PDF...")
url = "http://static.cninfo.com.cn/finalpage/2026-04-30/1225273099.PDF"
result = sf.download_report(url, "000858", "五粮液", "2026Q1")
print(f"    success={result.success} file={result.file_path} source={result.source_name}")
if result.error:
    print(f"    error={result.error}")

# 3. 入库
if result.success:
    print("\n[3] 入库...")
    from src.ingestion.batch_ingestor import BatchIngestor
    bi = BatchIngestor(reports_dir="data/reports")
    pdfs = [p for p in bi.discover_pdfs() if p['ticker']=='000858']
    for p in pdfs:
        r = bi.ingest_one(p)
        print(f"    {r['company_name']}: metrics={r.get('metrics_ingested',0)}/{r.get('metrics_extracted',0)}")

# 4. 查询验证
print("\n[4] 查询验证:")
test = [("revenue","营收"),("net_profit","净利润"),("eps_basic","每股收益"),("total_assets","总资产")]
for mc,label in test:
    row = fs.query_metric("000858", "2026Q1", mc)
    if row:
        v=row["value"]
        print(f"    ✓ {label}: {v/1e8:.2f}亿元" if abs(v)>=1e8 else f"    ✓ {label}: {v:.4f}")
    else:
        print(f"    ✗ {label}: SQL miss")

total = len(fs.query_metrics_by_company_period("000858","2026Q1"))
print(f"\n  五粮液 Q1 总指标: {total}")
