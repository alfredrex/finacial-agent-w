"""
混合记忆系统 — 四层记忆统一入口

L1 瞬时 (Python dict) → L2 用户 (kvstore) → L3 股票 (kvstore) → L4 语义 (ChromaDB)
短路检索: 上层命中且足够时不再查下层。

Usage:
    hms = HybridMemorySystem(kvstore_client, chroma_client)
    ctx = await hms.retrieve("茅台PE多少", user_id="default", session_id="sess_1")
    # ctx.transient  → L1 会话上下文
    # ctx.user       → L2 用户画像/关注列表
    # ctx.stock      → L3 股票结构化数据
    # ctx.semantic   → L4 RAG 语义检索结果
    # ctx.layers_hit → ["L1", "L3"]  哪些层被命中
"""

from __future__ import annotations

import re
import logging
from typing import Optional, Dict, List, Any, TYPE_CHECKING
from dataclasses import dataclass, field

from .kvstore_memory import TransientMemory, UserMemory, StockMemory

if TYPE_CHECKING:
    from .kvstore_client import KvstoreClient

logger = logging.getLogger(__name__)


# ─── MemoryContext ────────────────────────────────────────────

@dataclass
class MemoryContext:
    """四层记忆检索结果。"""
    # L1
    transient_context: str = ""              # 会话上下文文本
    transient_entities: Dict[str, List[str]] = field(default_factory=dict)
    last_stock_code: Optional[str] = None    # 最近讨论的股票代码

    # L2
    user_profile: Dict[str, Optional[str]] = field(default_factory=dict)
    user_watchlist: Dict[str, str] = field(default_factory=dict)
    user_strategy: Dict[str, Optional[str]] = field(default_factory=dict)
    user_summary: str = ""                   # L2 综合文本

    # L3
    stock_info: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # stock_info format: {code: {"base": {...}, "quote": {...}, "rag_ids": {...}}}

    # L4
    semantic_results: List[Dict[str, Any]] = field(default_factory=list)
    semantic_summary: str = ""

    # Meta
    layers_hit: List[str] = field(default_factory=list)
    rag_doc_ids: List[str] = field(default_factory=list)  # 精确 RAG 文档 ID 列表

    def get_combined_context(self, max_len: int = 3000) -> str:
        """合并所有层的结果为 prompt 上下文。"""
        parts = []

        if self.transient_context:
            parts.append(self.transient_context)

        if self.user_summary:
            parts.append(self.user_summary)

        for code, info in self.stock_info.items():
            base = info.get("base", {})
            quote = info.get("quote", {})
            if base or quote:
                lines = [f"【{code} {base.get('name', '')}】"]
                if base.get("sector"):
                    lines.append(f"  行业: {base['sector']}")
                if base.get("pe_ttm"):
                    lines.append(f"  PE(TTM): {base['pe_ttm']}")
                if quote.get("price"):
                    lines.append(f"  最新价: {quote['price']}  ({quote.get('change_pct', '')})")
                parts.append("\n".join(lines))

        if self.semantic_summary:
            parts.append(f"【深度研报/财报】\n{self.semantic_summary}")

        combined = "\n\n".join(parts)
        if len(combined) > max_len:
            combined = combined[:max_len] + "\n...(truncated)"
        return combined

    def to_dict(self) -> Dict[str, Any]:
        """转为可序列化 dict (用于 AgentState 传递)。"""
        return {
            "layers_hit": self.layers_hit,
            "transient_context": self.transient_context[:500],
            "user_summary": self.user_summary[:500],
            "stock_codes": list(self.stock_info.keys()),
            "rag_doc_ids": self.rag_doc_ids[:10],
            "semantic_count": len(self.semantic_results),
        }


# ─── Entity Extractor ─────────────────────────────────────────

# 常见 A 股代码模式
_STOCK_CODE_RE = re.compile(r'\b(60\d{4}|00\d{4}|30\d{4}|68\d{4})\b')

# 常见股票名称 → 代码映射 (启动后由 L3 填充)
_KNOWN_NAMES: Dict[str, str] = {}  # "茅台" → "600519"


def extract_entities(query: str) -> Dict[str, List[str]]:
    """从查询文本中提取实体。

    Returns:
        {"stocks": ["600519", "000858"], "sectors": ["白酒"]}
    """
    entities: Dict[str, List[str]] = {"stocks": [], "sectors": [], "concepts": []}

    # 1. 提取股票代码
    codes = _STOCK_CODE_RE.findall(query)
    entities["stocks"].extend(codes)

    # 2. 股票名称模糊匹配
    query_lower = query.lower()
    for name, code in _KNOWN_NAMES.items():
        if name in query or name.lower() in query_lower:
            if code not in entities["stocks"]:
                entities["stocks"].append(code)

    # 3. 板块/行业关键词
    sector_kw = {
        "白酒": "白酒", "新能源": "新能源", "芯片": "半导体",
        "医药": "医药", "银行": "银行", "地产": "房地产",
        "汽车": "汽车", "光伏": "光伏", "锂电": "锂电池",
        "ai": "AI", "人工智能": "人工智能",
    }
    for kw, sector in sector_kw.items():
        if kw in query:
            entities["sectors"].append(sector)

    return entities


def register_stock_name(name: str, code: str):
    """注册股票名称 → 代码映射 (从 L3 加载时调用)。"""
    _KNOWN_NAMES[name] = code


# ─── HybridMemorySystem ───────────────────────────────────────

class HybridMemorySystem:
    """四层混合记忆系统统一入口。

    Usage:
        hms = HybridMemorySystem(
            kvstore_client=client,
            chroma_client=chroma,          # L4
            user_id="default",
        )
        ctx = await hms.retrieve("茅台PE多少")

        # 记录一轮对话
        hms.record_turn("user", "茅台PE多少")
        hms.record_turn("assistant", "28.5")
    """

    def __init__(
        self,
        kvstore_client: KvstoreClient,
        chroma_store: Any = None,  # LangChain Chroma vectorstore or None
        user_id: str = "default",
        session_id: Optional[str] = None,
    ):
        self.client = kvstore_client
        self.chroma_store = chroma_store  # LangChain Chroma instance
        self.user_id = user_id

        import uuid
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:8]}"

        # 初始化各层
        self.l1 = TransientMemory(self.session_id, kvstore_client)
        self.l2 = UserMemory(kvstore_client, user_id)
        self.l3 = StockMemory(kvstore_client)

        # 从 L3 加载已知股票名称 → 代码映射 (用于实体提取)
        self._load_stock_names()

        # L4 就绪状态 (延迟初始化，首次检索时才初始化 vectorstore)
        self._l4_available = chroma_store is not None
        self._l4_initialized = False

    def _load_stock_names(self):
        """从 kvstore L3 加载所有已知股票的名称→代码映射。"""
        codes = self.l3.get_all_codes()
        for code in codes:
            name = self.l3.get_base_field(code, "name")
            if name:
                register_stock_name(name, code)
                # 注册常用的简称变体
                # "贵州茅台" → 注册 "贵州茅台", "贵州", "茅台"
                register_stock_name(name[:2], code) if len(name) >= 2 else None
                register_stock_name(name[-2:], code) if len(name) >= 2 else None
        logger.debug(f"Loaded {len(codes)} stock name mappings")

    # ── 核心检索 ─────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        force_layers: Optional[List[str]] = None,
        max_semantic_results: int = 5,
    ) -> MemoryContext:
        """四层短路检索。

        Args:
            query: 用户查询
            force_layers: 强制检索的层，如 ["L1", "L3"]。None = 自动短路。
            max_semantic_results: L4 最大返回数

        Returns:
            MemoryContext: 检索结果
        """
        ctx = MemoryContext()

        # 提取实体
        entities = extract_entities(query)
        stock_codes = entities.get("stocks", [])

        # 补充 L1 最近讨论的股票
        last_stock = self.l1.get_last_entity("stock")
        if last_stock and last_stock not in stock_codes:
            stock_codes.append(last_stock)

        # ═══ L1: 瞬时记忆 ═══
        ctx.transient_context = self.l1.get_context(k=5)
        ctx.transient_entities = dict(self.l1._entities)
        ctx.last_stock_code = last_stock
        ctx.layers_hit.append("L1")

        if force_layers is None:
            # 代词消解类问题：只有 L1 就够了
            if self._is_pronoun_query(query) and last_stock:
                logger.debug(f"Short-circuit at L1 (pronoun: {query} → {last_stock})")
                # L1 命中后仍需 L2 补充用户偏好
                self._fill_l2(ctx)
                return ctx

        # ═══ L2: 用户记忆 ═══
        self._fill_l2(ctx)
        ctx.layers_hit.append("L2")

        # ═══ L3: 股票公共数据 ═══
        if stock_codes:
            self._fill_l3(ctx, stock_codes)
            ctx.layers_hit.append("L3")

            # 如果是简单行情查询，L3 已足够
            if force_layers is None and self._is_simple_price_query(query):
                logger.debug(f"Short-circuit at L3 (simple price query: {query})")
                return ctx

        # ═══ L4: 语义记忆 (RAG) ═══
        needs_l4 = force_layers and "L4" in force_layers
        if not needs_l4 and force_layers is None:
            needs_l4 = self._needs_semantic(query, ctx)

        if needs_l4 and self._l4_available:
            await self._fill_l4(ctx, query, stock_codes, max_semantic_results)
            ctx.layers_hit.append("L4")
        elif needs_l4 and not self._l4_available:
            logger.warning("L4 requested but ChromaDB not available")

        return ctx

    # ── 各层填充 ─────────────────────────────────────────

    def _fill_l2(self, ctx: MemoryContext):
        """填充 L2 用户记忆。"""
        ctx.user_profile = self.l2.get_profile()
        ctx.user_watchlist = self.l2.get_watchlist()
        # 合并到 summary
        parts = []
        profile_summary = self.l2.get_profile_summary()
        if profile_summary:
            parts.append(profile_summary)
        wl_summary = self.l2.get_watchlist_summary()
        if wl_summary:
            parts.append(wl_summary)
        ctx.user_summary = "\n".join(parts)

    def _fill_l3(self, ctx: MemoryContext, stock_codes: List[str]):
        """填充 L3 股票结构化数据 + 财务指标。"""
        for code in stock_codes[:5]:
            info = self.l3.get_full_info(code)
            if info["base"].get("name") or info["quote"].get("price") or info.get("metrics"):
                ctx.stock_info[code] = info
                for lbl, doc_id in info.get("rag_ids", {}).items():
                    if doc_id and doc_id not in ctx.rag_doc_ids:
                        ctx.rag_doc_ids.append(doc_id)
            if code in ctx.user_watchlist:
                self.l2.update_access_time(code)

        # 注入 L3 财务指标到语义摘要 (QAAgent 可直接读取)
        if ctx.stock_info and any(
            info.get("metrics") for info in ctx.stock_info.values()
        ):
            parts = []
            for code, info in ctx.stock_info.items():
                metrics = info.get("metrics", {})
                if metrics:
                    name = info.get("base", {}).get("name", code)
                    lines = [f"【{code} {name} 财务指标】"]
                    label_map = {
                        "revenue": "营收", "cost": "营业成本",
                        "net_profit": "净利润", "net_profit_dedup": "扣非净利润",
                        "fin_expense": "财务费用", "sell_expense": "销售费用",
                        "admin_expense": "管理费用", "rd_expense": "研发费用",
                        "tax_surcharge": "税金及附加", "invest_income": "投资收益",
                        "oper_profit": "营业利润", "total_profit": "利润总额",
                        "total_assets": "总资产", "total_liability": "总负债",
                        "net_assets": "净资产", "cash": "货币资金",
                        "receivables": "应收账款", "inventory": "存货",
                        "fixed_assets": "固定资产",
                        "short_loan": "短期借款", "long_loan": "长期借款",
                        "oper_cf": "经营现金流", "invest_cf": "投资现金流",
                        "fin_cf": "筹资现金流",
                        "roe": "ROE", "eps": "每股收益",
                        "eps_diluted": "稀释EPS", "gross_margin": "毛利率",
                        "net_margin": "净利率",
                    }
                    for k, v in metrics.items():
                        if v:
                            label = label_map.get(k, k)
                            lines.append(f"  {label}: {v}")
                    parts.append("\n".join(lines))
            if parts:
                # L3 指标优先，放在 L4 前面
                ctx.semantic_summary = "\n".join(parts)

    async def _fill_l4(
        self, ctx: MemoryContext, query: str,
        stock_codes: List[str], max_results: int,
    ):
        """填充 L4 语义记忆。语义搜索 (叙事性问题)。"""
        try:
            fetch_k = min(max_results * 3, 25)
            results = await self._chroma_semantic_search(query, stock_codes, fetch_k)
            if results:
                # 关键词二次排序
                query_words = set(query)
                results.sort(
                    key=lambda r: sum(1 for w in query_words if w in r.get("content", "")),
                    reverse=True
                )
                ctx.semantic_results = results[:max_results]
                self._build_semantic_summary(ctx, results[:max_results])
                return

            # 回退: 按 doc_id 拉取
            if ctx.rag_doc_ids:
                results = await self._chroma_get_by_ids(ctx.rag_doc_ids[:max_results])
                ctx.semantic_results = results
                self._build_semantic_summary(ctx, results)
                ctx.semantic_results = results
                self._build_semantic_summary(ctx, results)

        except Exception as e:
            logger.warning(f"L4 retrieval failed: {e}")

    def _build_semantic_summary(self, ctx: MemoryContext, results: List[Dict]):
        """构建语义摘要 (追加模式，不覆盖已有内容)。"""
        if not results:
            return
        summaries = []
        for r in results[:3]:
            title = r.get("metadata", {}).get("title", "")
            source = r.get("metadata", {}).get("source", "")
            content_preview = (r.get("content", "") or r.get("page_content", ""))[:200]
            summaries.append(f"- [{source}] {title}\n  {content_preview}")
        new_summary = "\n".join(summaries)
        # 追加而非覆盖
        if ctx.semantic_summary:
            ctx.semantic_summary = ctx.semantic_summary + "\n\n" + new_summary
        else:
            ctx.semantic_summary = new_summary

    async def _chroma_get_by_ids(self, doc_ids: List[str]) -> List[Dict]:
        """通过 doc_id 精确获取文档 (LangChain Chroma API)。"""
        if not self.chroma_store:
            return []
        try:
            # LangChain Chroma.get(ids=[...])
            result = self.chroma_store.get(ids=doc_ids)
            if result and result.get("documents"):
                return [
                    {
                        "content": doc,
                        "metadata": meta or {},
                    }
                    for doc, meta in zip(
                        result["documents"],
                        result.get("metadatas", [{}] * len(result["documents"]))
                    )
                ]
        except Exception as e:
            logger.warning(f"ChromaDB get_by_ids failed: {e}")
        return []

    async def _chroma_semantic_search(
        self, query: str, stock_codes: List[str], k: int,
    ) -> List[Dict]:
        """LangChain Chroma 向量语义搜索。"""
        if not self.chroma_store:
            return []
        try:
            # 构建过滤条件: 优先匹配相关股票代码
            search_filter = None
            if stock_codes:
                search_filter = {"stock_codes": {"$in": stock_codes}}

            # LangChain Chroma.similarity_search(query, k, filter)
            docs = self.chroma_store.similarity_search(
                query, k=k
            )

            if docs:
                return [
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata or {},
                    }
                    for doc in docs
                ]
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
        return []

    # ── 短路判断 ─────────────────────────────────────────

    def _is_pronoun_query(self, query: str) -> bool:
        """判断是否为代词指代类问题。"""
        pronouns = ["它", "他", "她", "这个", "那个", "这支", "那只", "继续", "接着"]
        q = query.strip()
        return any(q.startswith(p) or q == p for p in pronouns)

    def _is_simple_price_query(self, query: str) -> bool:
        """判断是否为简单行情查询。"""
        simple_patterns = [
            "股价", "价格", "多少钱", "行情", "涨跌",
            "PE", "PE", "估值", "市值", "代码",
        ]
        # 简单问题通常很短，且不含"分析""报告"等深度词汇
        deep_words = ["分析", "报告", "研报", "财报", "深度", "策略", "原因", "为什么"]
        q = query.strip()
        if len(q) > 30:
            return False
        if any(d in q for d in deep_words):
            return False
        return any(p in q for p in simple_patterns)

    def _needs_semantic(self, query: str, ctx: MemoryContext) -> bool:
        """判断是否需要 L4 语义检索。"""
        deep_triggers = [
            "财报", "年报", "季报", "季度", "报告", "研报",
            "营收结构", "利润来源", "净利润", "财务数据",
            "行业政策", "监管", "产业链", "上下游",
            "深度分析", "详细分析", "全面分析",
            "策略原理", "技术原理", "为什么", "原因",
            "对比分析", "竞争力", "护城河",
        ]
        if any(t in query for t in deep_triggers):
            return True

        # 有三层数据 (L3 股票信息) 且有 RAG 文档索引 → 走 L4
        if ctx.rag_doc_ids:
            return True

        # 前三层数据不足
        if not ctx.stock_info and not ctx.user_watchlist:
            return True

        return False

    # ── 对话记录 ─────────────────────────────────────────

    def record_turn(self, role: str, content: str):
        """记录一轮对话到 L1 + 更新 L2 历史。"""
        self.l1.add_turn(role, content)

        # 提取本轮涉及的股票代码，加入 L1 实体追踪
        entities = extract_entities(content)
        for code in entities.get("stocks", []):
            # 尝试从 L3 获取名称
            name = self.l3.get_base_field(code, "name") or code
            self.l1.track_entity("stock", code, name)
            self.l2.update_access_time(code)

        # 如果是用户消息，记录到 L2 历史
        if role == "user":
            self.l2.add_query_history(content)
        elif role == "assistant":
            self.l2.add_query_history("", content[:200])

    # ── 会话生命周期 ─────────────────────────────────────

    def close_session(self):
        """关闭会话: 清空 L1，保留 L2/L3/L4。"""
        self.l1.clear()
        logger.info(f"Session {self.session_id} closed, L1 cleared")

    # ── 状态快照 ─────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "l1": self.l1.stats(),
            "l4_available": self._l4_available,
        }
