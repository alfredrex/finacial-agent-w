"""向 kvstore 注入测试记忆数据"""
import sys, os, importlib.util

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_mod(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

kc = load_mod('kc', f'{base}/src/memory/kvstore_client.py')
km = load_mod('km', f'{base}/src/memory/kvstore_memory.py')

c = kc.KvstoreClient(); c.connect()
print("Connected to kvstore\n")

# ─── L2: 用户数据 ───
um = km.UserMemory(c, "default")
um.update_profile({
    "name": "张总",
    "philosophy": "价值投资",
    "style": "长期持有",
    "risk_tolerance": "中高",
    "max_position_pct": "30",
    "stop_loss_pct": "8",
    "take_profit_pct": "25",
    "preferred_sectors": "白酒,新能源,银行",
})
um.add_to_watchlist("600519", "贵州茅台")
um.add_to_watchlist("000858", "五粮液")
um.add_to_watchlist("300750", "宁德时代")
um.update_strategy({"ma_short": "5", "ma_long": "20", "rsi_period": "14"})
print("[L2] 用户画像 + 3只关注股 + 策略参数 → OK")

# ─── L3: 股票数据 ───
sm = km.StockMemory(c)

sm.update_base("600519", {
    "name": "贵州茅台", "sector": "白酒", "industry": "食品饮料",
    "market_cap": "2350000000000", "pe_ttm": "28.5", "pb": "9.2",
    "turnover_rate": "0.35", "listing_date": "2001-08-27",
})
sm.update_quote("600519", {"price": "1445.00", "change_pct": "+1.25",
    "volume": "2456789", "high": "1450.00", "low": "1430.00"})
sm.add_rag_index("600519", "report_2025q4", "chroma:doc:rep_600519_2025q4")
sm.add_rag_index("600519", "research_citic", "chroma:doc:res_citic_202603")

sm.update_base("000858", {
    "name": "五粮液", "sector": "白酒", "industry": "食品饮料",
    "market_cap": "680000000000", "pe_ttm": "22.1", "pb": "5.8",
    "turnover_rate": "0.42", "listing_date": "1998-04-27",
})
sm.update_quote("000858", {"price": "168.50", "change_pct": "-0.35",
    "volume": "1234567", "high": "170.20", "low": "167.80"})
sm.add_rag_index("000858", "annual_2024", "chroma:doc:ann_000858_2024")

sm.update_base("300750", {
    "name": "宁德时代", "sector": "新能源", "industry": "电力设备",
    "market_cap": "980000000000", "pe_ttm": "32.8", "pb": "6.5",
    "turnover_rate": "0.68", "listing_date": "2018-06-11",
})
sm.update_quote("300750", {"price": "215.30", "change_pct": "+2.15",
    "volume": "3456789", "high": "218.00", "low": "212.50"})
sm.add_rag_index("300750", "policy_2025", "chroma:doc:pol_newenergy_2025")

print("[L3] 3只股票基础信息 + 行情 + RAG索引 → OK")

# ─── 验证 ───
print("\n─── 验证 L2 ───")
p = um.get_profile()
print(f"  用户: {p.get('name')} | 理念: {p.get('philosophy')} | 风格: {p.get('style')}")
wl = um.get_watchlist()
print(f"  关注: {list(wl.keys())}")

print("\n─── 验证 L3 ───")
for code in ["600519", "000858", "300750"]:
    info = sm.get_full_info(code)
    print(f"  {code} {info['base'].get('name')}: PE={info['base'].get('pe_ttm')} "
          f"价格={info['quote'].get('price')} RAG={len(info.get('rag_ids',{}))}文档")

c.close()
print("\n=== 种子数据写入完成 ===")
