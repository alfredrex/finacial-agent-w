import requests, os
url = "https://stockmc.xueqiu.com/202604/600036_20260429_IO3O.pdf"
fpath = "/home/wjh/FinIntel-Multi-Agent/data/reports/600036_招商银行_2026Q1.pdf"
r = requests.get(url, timeout=60, stream=True, headers={"User-Agent": "Mozilla/5.0"})
r.raise_for_status()
with open(fpath, "wb") as f:
    for c in r.iter_content(8192): f.write(c)
print(f"OK {os.path.getsize(fpath)} bytes")
