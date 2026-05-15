"""测试东方财富 API 连通性"""
import sys; sys.path.insert(0, "/home/wjh/FinIntel-Multi-Agent")
import requests, json

# 用 enhanced_data_collector 的 session 配置
s = requests.Session()
s.trust_env = False
s.proxies = {'http': None, 'https': None}
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://finance.sina.com.cn/',
})

# 测试1: HTTP push2 实时行情
print("Test 1: HTTP push2.eastmoney.com ...")
try:
    r = s.get("http://push2.eastmoney.com/api/qt/stock/get?secid=1.600519&fields=f43,f57,f58", timeout=8)
    print(f"  status={r.status_code} len={len(r.text)} body={r.text[:200]}")
except Exception as e:
    print(f"  FAIL: {e}")

# 测试2: HTTPS datacenter 财报
print("Test 2: HTTPS datacenter.eastmoney.com ...")
try:
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_FN_INCOME&columns=ALL&filter=(SECUCODE=%22600519.SH%22)&pageSize=2&sortColumns=REPORT_DATE&sortTypes=-1"
    r = s.get(url, timeout=10)
    print(f"  status={r.status_code} len={len(r.text)}")
    if r.status_code == 200:
        data = r.json()
        items = data.get("result", {}).get("data", [])
        print(f"  records={len(items)}")
        for item in items[:1]:
            print(f"  {item.get('REPORT_DATE','')}: revenue={item.get('TOTAL_OPERATE_INCOME',0)/1e8:.2f}亿 net={item.get('PARENT_NETPROFIT',0)/1e8:.2f}亿")
except Exception as e:
    print(f"  FAIL: {e}")

# 测试3: HTTP Sina 财经
print("Test 3: HTTP sina ...")
try:
    r = s.get("https://hq.sinajs.cn/list=sh600519", timeout=8, headers={"Referer":"https://finance.sina.com.cn"})
    print(f"  status={r.status_code} len={len(r.text)} body={r.text[:100]}")
except Exception as e:
    print(f"  FAIL: {e}")
