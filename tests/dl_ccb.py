import requests, os
url = "https://pdf.dfcfw.com/pdf/H2_AN202604291821766584_1.pdf"
fpath = "/home/wjh/FinIntel-Multi-Agent/data/reports/601939_建设银行_2026Q1.pdf"
r = requests.get(url, timeout=60, stream=True, headers={"User-Agent": "Mozilla/5.0"})
r.raise_for_status()
with open(fpath, "wb") as f:
    for c in r.iter_content(8192): f.write(c)
print(f"OK {os.path.getsize(fpath)} bytes")
