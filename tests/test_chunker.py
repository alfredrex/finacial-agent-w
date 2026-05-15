"""测试金融语义分块器"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.rag.financial_chunker import chunk_financial_text

text = """贵州茅台（600519）2025年年报分析

投资要点：
贵州茅台2025年实现营收1700亿元，同比增长12.5%；净利润800亿元，同比增长15.2%。
毛利率92.3%，净利率47.1%，ROE达到35.6%。

财务分析：
营收结构方面，茅台酒营收1450亿元，系列酒营收250亿元。
直销渠道占比提升至55%，批发渠道45%。
国内营收1600亿元，出口100亿元。

估值分析：
当前股价1445元，对应PE（TTM）28.5倍，处于历史估值中位数附近。
我们给予买入评级，目标价1700元。

风险提示：宏观经济下行风险；消费税改革不确定性；高端白酒竞争加剧

免责声明：本报告仅供参考，不构成投资建议。"""

chunks = chunk_financial_text(text)
print(f'Chunks: {len(chunks)}')
for i, c in enumerate(chunks):
    print(f'  [{i+1}] {len(c)}c: {c[:100]}...')
    assert len(c) <= 512, f'Chunk {i+1} exceeds 512: {len(c)}'
print('OK')
