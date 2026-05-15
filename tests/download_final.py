import os, requests

SAVE = "/home/wjh/FinIntel-Multi-Agent/data/reports"
os.makedirs(SAVE, exist_ok=True)

# 所有真实链接
REPORTS = [
    ("601398", "工商银行", "https://stockmc.xueqiu.com/202604/601398_20260430_VX32.pdf"),
    ("601939", "建设银行", "https://stockmc.xueqiu.com/202604/601939_20260428_JVLD.pdf"),
    ("601288", "农业银行", "https://stockmc.xueqiu.com/202604/601288_20260430_4VKP.pdf"),
    ("600941", "中国移动", "https://stockmc.xueqiu.com/202604/600941_20260421_7CDU.pdf"),
    ("601857", "中国石油", "https://www.petrochina.com.cn/petrochina/rdxx/202604/47aa45c6dead441ea8014bf8f9e5dde1/files/1c4bd94b4b474d6e84308190776b06c2.pdf"),
    ("300750", "宁德时代", "https://static.cninfo.com.cn/finalpage/2026-04-16/1225107946.PDF"),
    ("601988", "中国银行", "https://stockmc.xueqiu.com/202604/601988_20260430_77QJ.pdf"),
    ("600938", "中国海油", "https://stockmc.xueqiu.com/202604/600938_20260428_M4SP.pdf"),
    ("600519", "贵州茅台", "https://stockmc.xueqiu.com/202604/600519_20260425_G9JL.pdf"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

ok = 0
for ticker, name, url in REPORTS:
    fname = f"{ticker}_{name}_2026Q1.pdf"
    fpath = os.path.join(SAVE, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 5000:
        print(f"  ⏭ {name} 已存在")
        ok += 1
        continue
    try:
        print(f"  ⬇ {name}...", end="", flush=True)
        r = requests.get(url, timeout=120, stream=True, headers=HEADERS)
        if r.status_code == 404:
            print(f" ✗ 404")
            continue
        r.raise_for_status()
        with open(fpath, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        sz = os.path.getsize(fpath)
        print(f" ✓ {sz} bytes")
        ok += 1
    except Exception as e:
        print(f" ✗ {e}")

print(f"\n  {ok}/{len(REPORTS)} 成功")
