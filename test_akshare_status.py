import os
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

import requests
requests.sessions.Session.trust_env = False

import akshare as ak

print('=== akshare 测试 ===')
print()

# 测试1: 实时行情
print('1. stock_zh_a_spot_em (实时行情)')
try:
    df = ak.stock_zh_a_spot_em()
    print(f'   成功: {len(df)} 条')
    moutai = df[df['代码'] == '600519']
    if not moutai.empty:
        print(f'   茅台价格: {moutai.iloc[0]["最新价"]}')
except Exception as e:
    print(f'   失败: {e}')

# 测试2: 历史K线
print('\n2. stock_zh_a_hist (历史K线)')
try:
    df = ak.stock_zh_a_hist(symbol='600519', period='daily', start_date='20240401', end_date='20240410', adjust='')
    print(f'   成功: {len(df)} 条')
except Exception as e:
    print(f'   失败: {e}')

# 测试3: 公司信息
print('\n3. stock_individual_info_em (公司信息)')
try:
    df = ak.stock_individual_info_em(symbol='600519')
    print(f'   成功: {len(df)} 条')
except Exception as e:
    print(f'   失败: {e}')

# 测试4: 检查网络连接
print('\n4. 网络连接测试')
try:
    r = requests.get('https://www.baidu.com', timeout=5)
    print(f'   百度: {r.status_code}')
except Exception as e:
    print(f'   百度失败: {e}')

try:
    r = requests.get('https://push2.eastmoney.com', timeout=5)
    print(f'   东方财富: {r.status_code}')
except Exception as e:
    print(f'   东方财富失败: {e}')
