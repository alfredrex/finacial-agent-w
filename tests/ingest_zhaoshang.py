"""单独入库招商银行"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.ingestion.batch_ingestor import BatchIngestor

bi = BatchIngestor(reports_dir="/home/wjh/FinIntel-Multi-Agent/data/reports")
# 只处理招商银行
pdfs = [p for p in bi.discover_pdfs() if p["ticker"] == "600036"]
for pdf in pdfs:
    r = bi.ingest_one(pdf)
    print(f"\n结果: {r['company_name']} metrics={r.get('metrics_ingested',0)}/{r.get('metrics_extracted',0)} status={r.get('status','?')}")
