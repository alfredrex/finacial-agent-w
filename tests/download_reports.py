import os, sys
sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
import requests

SAVE_DIR = "/home/wjh/FinIntel-Multi-Agent/data/reports"

REPORTS = [
    {"name": "工商银行",   "ticker": "601398", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567890.PDF"},
    {"name": "建设银行",   "ticker": "601939", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567905.PDF"},
    {"name": "农业银行",   "ticker": "601288", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567912.PDF"},
    {"name": "中国移动",   "ticker": "600941", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567920.PDF"},
    {"name": "中国石油",   "ticker": "601857", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567928.PDF"},
    {"name": "宁德时代",   "ticker": "300750", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567935.PDF"},
    {"name": "中国银行",   "ticker": "601988", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567942.PDF"},
    {"name": "中国海油",   "ticker": "600938", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567950.PDF"},
    {"name": "贵州茅台",   "ticker": "600519", "url": "https://static.cninfo.com.cn/finalpage/2026-04-30/1223567958.PDF"},
]

os.makedirs(SAVE_DIR, exist_ok=True)

success = 0
for item in REPORTS:
    name, ticker, url = item["name"], item["ticker"], item["url"]
    fname = f"{ticker}_{name}_2026Q1.pdf"
    fpath = os.path.join(SAVE_DIR, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
        print(f"  ⏭ {name} 已存在 ({os.path.getsize(fpath)} bytes)")
        success += 1
        continue
    try:
        print(f"  ⬇ {name}...", end="", flush=True)
        r = requests.get(url, timeout=60, stream=True)
        r.raise_for_status()
        with open(fpath, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        size = os.path.getsize(fpath)
        print(f" ✓ ({size} bytes)")
        success += 1
    except Exception as e:
        print(f" ✗ {e}")

print(f"\n  {success}/{len(REPORTS)} 下载成功")
