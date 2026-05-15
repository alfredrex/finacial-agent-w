"""kvstore_memory 三层冒烟测试"""
import importlib.util, os, sys, json

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Avoid src.memory.__init__.py import chain (requires pandas)
sys.path.insert(0, base)

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

kc = load_module('kvstore_client', f'{base}/src/memory/kvstore_client.py')
km = load_module('kvstore_memory', f'{base}/src/memory/kvstore_memory.py')

c = kc.KvstoreClient(); c.connect()

# === L1 ===
print('=== L1 TransientMemory ===')
tm = km.TransientMemory('sess_test', c)
tm.add_turn('user', 'maotai PE?')
tm.add_turn('assistant', 'PE 28.5')
tm.track_entity('stock', '600519', 'maotai')
ctx = tm.get_context(2)
assert 'maotai' in ctx, f"L1 context missing entity: {ctx}"
assert tm.get_last_entity('stock') == '600519', "L1 entity tracking failed"
print('PASS')

# === L2 ===
print('=== L2 UserMemory ===')
um = km.UserMemory(c, 'test_u2')
um.update_profile({'name': 'Test', 'style': 'daytrade'})
um.add_to_watchlist('600519', 'maotai')
profile = um.get_profile()
assert profile['name'] == 'Test', f"L2 profile: {profile}"
wl = um.get_watchlist()
assert '600519' in wl, f"L2 watchlist: {wl}"
print('PASS')

# === L3 ===
print('=== L3 StockMemory ===')
sm = km.StockMemory(c)
sm.update_base('600519', {'name': 'maotai', 'sector': 'baijiu', 'pe_ttm': '28.5'})
sm.update_quote('600519', {'price': '1445', 'change_pct': '+1.25'})
sm.add_rag_index('600519', 'rpt_q4', 'chroma:doc:001')
info = sm.get_full_info('600519')
assert info['base']['name'] == 'maotai', f"L3 base: {info['base']}"
assert info['quote']['price'] == '1445', f"L3 quote: {info['quote']}"
assert info['rag_ids']['rpt_q4'] == 'chroma:doc:001', f"L3 rag: {info['rag_ids']}"
assert info['quote_stale'] == False, "L3 should not be stale"
print('PASS')

# cleanup
for k in ['user:test_u2:profile:name','user:test_u2:profile:style','user:test_u2:watchlist:600519',
          'user:test_u2:_watchlist_index','user:test_u2:access_log:600519','user:test_u2:_history_keys']:
    c.delete(k)
sm.delete_stock('600519')
tm.clear()
c.close()
print('\n=== ALL PASSED ===')
