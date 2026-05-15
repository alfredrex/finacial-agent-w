import os, sys, requests, time

SAVE_DIR = "/home/wjh/FinIntel-Multi-Agent/data/reports"
os.makedirs(SAVE_DIR, exist_ok=True)

# 已验证/推测的链接
REPORTS = [
    # 已有 BYD: 002594
    ("601398", "工商银行", "https://stockmc.xueqiu.com/202604/601398_20260430_VX32.pdf"),
    ("601939", "建设银行", "https://stockmc.xueqiu.com/202604/601939_20260428_JVLD.pdf"),
    ("601288", "农业银行", "https://stockmc.xueqiu.com/202604/601288_20260430_9L8M.pdf"),
    ("600941", "中国移动", "https://stockmc.xueqiu.com/202604/600941_20260423_PG7K.pdf"),
    ("601857", "中国石油", "https://stockmc.xueqiu.com/202604/601857_20260429_T2WN.pdf"),
    ("300750", "宁德时代", "https://stockmc.xueqiu.com/202604/300750_20260416_N6VK.pdf"),
    ("601988", "中国银行", "https://stockmc.xueqiu.com/202604/601988_20260430_Z4XJ.pdf"),
    ("600938", "中国海油", "https://stockmc.xueqiu.com/202604/600938_20260425_H3YP.pdf"),
    ("600519", "贵州茅台", "https://stockmc.xueqiu.com/202604/600519_20260425_G9JL.pdf"),
]

success = 0
for ticker, name, url in REPORTS:
    fname = f"{ticker}_{name}_2026Q1.pdf"
    fpath = os.path.join(SAVE_DIR, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
        print(f"  ⏭ {name} 已存在")
        success += 1
        continue
    try:
        print(f"  ⬇ {name} ({ticker})...", end="", flush=True)
        r = requests.get(url, timeout=60, stream=True, headers={"User-Agent": "Mozilla/5.0"})
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
