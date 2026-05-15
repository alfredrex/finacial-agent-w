"""验证: FileProcessor 指标抽取 + kvstore L3 存入"""
import sys, os
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")

from src.tools.file_processor import file_processor
from src.memory.kvstore_client import KvstoreClient
from src.memory.kvstore_memory import StockMemory

# 1. 抽取
info = file_processor.process_file("data/byd_2026_1.pdf")
metrics = info.get("metrics", {})
print(f"Extracted metrics: {len(metrics)}")
for k, v in metrics.items():
    print(f"  {k}: {v}")

# 2. 存 kvstore L3
kv = KvstoreClient(host="127.0.0.1", port=2000)
kv.connect()
sm = StockMemory(kv)
sm.update_base("002594", {"name": "比亚迪", "sector": "新能源汽车"})
sm.update_metrics("002594", metrics)

# 3. 验证读取 O(1)
print(f"\nkvstore L3 readback:")
print(f"  fin_expense: {sm.get_metric('002594', 'fin_expense')}")
print(f"  net_profit:  {sm.get_metric('002594', 'net_profit')}")
print(f"  revenue:     {sm.get_metric('002594', 'revenue')}")

kv.close()
print("\nDone.")
