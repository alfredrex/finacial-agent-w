"""V1 批量入库运行脚本 — 处理 data/reports/ 下所有 PDF"""
import sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
from src.ingestion.batch_ingestor import BatchIngestor

ingestor = BatchIngestor()
summary = ingestor.run()

print("\n" + "=" * 60)
print("批量入库完成")
print("=" * 60)
print(f"  总文件:    {summary['total']}")
print(f"  成功:      {summary['success']}")
print(f"  失败:      {summary['failed']}")
print(f"  跳过(已入库): {summary['skipped']}")
print(f"  指标入库:   {summary['total_metrics_ingested']}")
print(f"  未知指标:   {summary['total_unknown_metrics']}")
print(f"  解析错误:   {summary['total_extraction_errors']}")
print(f"  RAG分块:    {summary['total_rag_chunks']}")

# 排名
print(f"\n  各公司指标数排名:")
ranked = sorted(summary['results'], key=lambda r: r.get('metrics_ingested', 0), reverse=True)
for r in ranked:
    icon = {"done":"✓","partial":"~","failed":"✗","skipped":"⏭","error":"✗"}.get(r.get("status",""),"?")
    print(f"    {icon} {r['company_name']:8s} metrics={r.get('metrics_ingested',0)}/{r.get('metrics_extracted',0)}  unknown={r.get('unknown_metrics',0)}  chunks={r.get('chunks_rag',0)}")
