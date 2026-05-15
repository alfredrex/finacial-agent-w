"""
金融文本语义分块器

5 步法:
  1. 预处理: 去噪、表格转文本
  2. 按天然分隔符分层切
  3. 自适应合并/拆分
  4. 兜底长度 + 小重叠
  5. 金融关键信息保护

原则: 每个 chunk = 一个完整逻辑 (一组财务数据 / 一个投资逻辑 / 一个评级)
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    max_chars: int = 400       # 最大字符数
    min_chars: int = 50        # 最小字符数 (短于则合并)
    overlap: int = 60          # 重叠字符数
    hard_limit: int = 512      # 绝对上限 (BGE 窗口 = 512 tokens ≈ ~512 汉字)


# ─── Step 1: 预处理 ─────────────────────────────────────────

# 免责声明/广告尾部匹配模式
_TAIL_PATTERNS = [
    r'免责声明.*$', r'风险提示.*$', r'本报告仅供.*$',
    r'分析师声明.*$', r'评级说明.*$', r'重要声明.*$',
    r'扫码关注.*$', r'更多研报.*$', r'添加微信.*$',
    r'关注公众号.*$', r'客服电话.*$',
]

# 页眉页脚
_HEADER_FOOTER_PATTERNS = [
    r'^\d+/\d+\s*$',           # 页码 如 "1/15"
    r'^第\s*\d+\s*页',          # 第 X 页
    r'^请务必阅读.*$',           # 请务必阅读...
    r'^证券研究报告.*$',         # 券商报告头
]


def preprocess(text: str) -> str:
    """Step 1: 清洗金融文本。

    - 去掉页眉页脚、券商 logo、广告、免责声明
    - 去掉乱码、多余空格和换行
    - 表格转纯文本 (财务表格 → 科目:数值格式)
    """
    lines = text.split('\n')
    cleaned = []

    for line in lines:
        line = line.strip()
        if not line:
            cleaned.append('')
            continue

        # 去掉页眉页脚
        skip = False
        for pat in _HEADER_FOOTER_PATTERNS:
            if re.match(pat, line):
                skip = True
                break
        if skip:
            continue

        # 去掉免责声明/广告行 (匹配行首)
        skip = False
        for pat in _TAIL_PATTERNS:
            if re.match(pat, line):
                skip = True
                break
        if skip:
            continue

        # 表格转文本: 如果行中包含多个 | 或连续数字列
        if line.count('|') >= 3:
            # 表格行 → "科目:数值" 格式
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if len(cells) >= 2:
                line = ' '.join(f"{cells[0]}:{c}" if i > 0 else c
                                for i, c in enumerate(cells))
        elif re.match(r'^\s*[\d,.\-+%]+\s+[\d,.\-+%]', line):
            # 多列数字行 → 空格连接
            pass

        # 清理乱码字符 (保留中英文/数字/常用标点)
        line = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffef'
                      r'a-zA-Z0-9.,;:!?()（）、。，；：！？""''%+\-=/<>@#$&*\[\]{}'
                      r'\s]+', '', line)

        # 合并多余空格
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            cleaned.append(line)

    text = '\n'.join(cleaned)

    # 压缩连续空行: 3+ 换行 → 2换行 (保留章节边界), 保留 2换行
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    # 清理行首行尾空白
    text = '\n'.join(line.strip() for line in text.split('\n'))

    return text.strip()


# ─── Step 2: 按金融文本天然分隔符分层切 ────────────────────

# 分隔符优先级 (从高到低)
_SEPARATORS = [
    # 大章节分隔 (研报大章节)
    r'\n{3,}',
    # 二级标题/段落分隔
    r'\n{2}',
    # 一级换行
    r'\n',
    # 完整句子结束 (中英文)
    r'[。！？；](?=[^\w])',
    # 分号分隔
    r'；(?=[^\w])',
    # 逗号 (最后使用)
    r'，(?=[^\w])',
]


def _split_by_separator(text: str, sep_pattern: str) -> List[str]:
    """按分隔符模式拆分文本。"""
    parts = re.split(f'({sep_pattern})', text)
    # 合并回分隔符到前一部分
    chunks = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts) and re.match(sep_pattern, parts[i + 1]):
            chunk += parts[i + 1]
            i += 1
        i += 1
        chunk = chunk.strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _split_hierarchical(text: str, config: ChunkConfig) -> List[str]:
    """Step 2: 分层递归切分。

    按分隔符优先级从高到低: 先尝试大分隔符，再逐级下降。
    每个 chunk 如果超过 hard_limit 才用下一级分隔符继续切。
    """
    # 已经够短，不再切
    if len(text) <= config.max_chars:
        return [text] if text.strip() else []

    for sep_pat in _SEPARATORS:
        parts = _split_by_separator(text, sep_pat)
        if len(parts) > 1:
            # 成功切分，递归处理每个子块
            result = []
            for part in parts:
                result.extend(_split_hierarchical(part, config))
            return result

    # 所有分隔符都失败 → 兜底按字符硬切
    return _hard_split(text, config)


# ─── Step 3: 自适应合并/拆分 ────────────────────────────────

def _adaptive_merge(chunks: List[str], config: ChunkConfig) -> List[str]:
    """Step 3: 自适应合并 (小语义块合并) + 拆分 (超大块)。

    规则:
    - 小语义块 (< min_chars): 合并到前一个 chunk
    - 超大块 (> max_chars): 保持 (已在上层递归切分)
    """
    if not chunks:
        return chunks

    merged = []
    buffer = ""

    for chunk in chunks:
        combined = buffer + (" " if buffer else "") + chunk

        if len(combined) <= config.max_chars:
            buffer = combined
        else:
            if buffer and len(buffer) >= config.min_chars:
                merged.append(buffer)
            elif buffer:
                # buffer 太短 (< min_chars)，合并到下一个 chunk
                buffer = combined
            buffer = chunk

    if buffer:
        if merged and len(buffer) < config.min_chars:
            # 最后的短 buffer 合并到上一个
            merged[-1] = merged[-1] + " " + buffer
        else:
            merged.append(buffer)

    return merged


# ─── Step 4: 兜底 + 重叠 ────────────────────────────────────

def _hard_split(text: str, config: ChunkConfig) -> List[str]:
    """兜底硬切分 (当所有语义分隔符都失败时)。"""
    chunks = []
    pos = 0
    while pos < len(text):
        end = min(pos + config.max_chars, len(text))
        chunks.append(text[pos:end])
        pos = end - config.overlap if end < len(text) else len(text)
    return chunks


def _add_overlap(chunks: List[str], config: ChunkConfig) -> List[str]:
    """Step 4: 添加小块重叠，防止语义断裂。

    只在句子级边界添加重叠，不打断关键数据。
    """
    if config.overlap <= 0 or len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        curr = chunks[i]

        # 从前一个 chunk 末尾取 overlap 长度的文本
        overlap_text = prev[-config.overlap:] if len(prev) > config.overlap else prev

        # 只在句子边界 (。！？) 处截断 overlap
        for sep in ['。', '！', '？', '；']:
            idx = overlap_text.rfind(sep)
            if idx > config.overlap // 2:
                overlap_text = overlap_text[idx + 1:]
                break

        if overlap_text and not curr.startswith(overlap_text):
            curr = overlap_text + curr

        result.append(curr)

    return result


# ─── Step 5: 金融关键信息保护 ───────────────────────────────

# 禁止切断的模式 (这些内容必须在一个 chunk 内)
_PROTECTED_PATTERNS = [
    # 财务数据块
    r'(?:营收|净利润|毛利润|ROE|ROA|PE|PB|PS|EPS|毛利率|净利率)\s*[:：]?\s*[\d,.\-+%万亿美元]+',
    # 投资评级 + 目标价
    r'(?:买入|增持|中性|减持|卖出|强烈推荐|推荐|谨慎推荐|观望)\s*[（(]?\s*(?:目标价\s*[:：]?\s*[\d,.]+元?)?\s*[）)]?',
    # 核心结论句
    r'(?:我们认为|预计|判断|看好|看淡|综上|总结|核心观点)',
    # 政策/事件影响
    r'(?:政策|监管|利好|利空|影响|冲击)(?:[^。！？\n]{0,50})',
]


def _is_protected_content(chunk: str) -> bool:
    """检查 chunk 是否包含受保护的金融关键信息。"""
    for pat in _PROTECTED_PATTERNS:
        if re.search(pat, chunk):
            return True
    return False


def _protect_split(chunks: List[str], text: str, config: ChunkConfig) -> List[str]:
    """Step 5: 保护关键信息不被切断。

    如果切分点落在受保护内容中间，调整切分边界。
    """
    # 主要保护策略在 _split_hierarchical 中:
    # 使用句子级分隔符 (。！？) 而非字符级切分，天然保护完整句子。
    # 此处做最后一道检查: 如果有 chunk 超过 hard_limit，强制保护。
    result = []
    for chunk in chunks:
        if len(chunk) > config.hard_limit and _is_protected_content(chunk):
            # 找一个更安全的切分点 (在最近的句子边界切)
            split_pos = config.hard_limit
            for sep in ['。', '！', '？', '；', '\n']:
                idx = chunk.rfind(sep, 0, config.hard_limit)
                if idx > config.hard_limit // 2:
                    split_pos = idx + 1
                    break
            result.append(chunk[:split_pos])
            result.append(chunk[split_pos:])
        else:
            result.append(chunk)
    return result


# ─── 主入口 ─────────────────────────────────────────────────

def chunk_financial_text(
    text: str,
    max_chars: int = 400,
    min_chars: int = 50,
    overlap: int = 60,
    hard_limit: int = 512,
) -> List[str]:
    """对金融文本执行 5 步语义分块。

    Args:
        text: 原始金融文本 (研报、财报、政策等)
        max_chars: 目标最大字符数 (默认 400)
        min_chars: 最小字符数 (短于此则合并)
        overlap: 块间重叠字符数 (默认 60)
        hard_limit: 绝对上限 (默认 512, 不超过 BGE 窗口)

    Returns:
        chunk 列表，每个 chunk 是一个完整逻辑单元
    """
    config = ChunkConfig(
        max_chars=max_chars,
        min_chars=min_chars,
        overlap=overlap,
        hard_limit=hard_limit,
    )

    # Step 1: 预处理
    clean = preprocess(text)

    # Step 2: 分层语义切分
    chunks = _split_hierarchical(clean, config)

    # Step 3: 自适应合并
    chunks = _adaptive_merge(chunks, config)

    # Step 4: 兜底长度 + 重叠
    chunks = _add_overlap(chunks, config)

    # Step 5: 保护关键信息
    chunks = _protect_split(chunks, clean, config)

    # 后处理: 去空白、去重
    chunks = [c.strip() for c in chunks if c.strip() and len(c.strip()) >= 5]
    # 去重: 完全相同的内容只保留一份
    seen = set()
    unique = []
    for c in chunks:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return unique


# ─── 便捷方法 ───────────────────────────────────────────────

def chunk_with_metadata(
    text: str,
    metadata: Optional[Dict] = None,
    **kwargs,
) -> List[Dict[str, any]]:
    """分块并附加元数据。

    Returns:
        [{"content": "...", "metadata": {...}}, ...]
    """
    chunks = chunk_financial_text(text, **kwargs)
    base_meta = metadata or {}
    return [
        {"content": c, "metadata": {**base_meta, "chunk_index": i, "chunk_count": len(chunks)}}
        for i, c in enumerate(chunks)
    ]
