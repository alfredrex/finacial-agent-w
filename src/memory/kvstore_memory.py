"""
kvstore 记忆后端 — L1/L2/L3 层管理器

L1 TransientMemory: 会话级瞬时记忆 (Python dict, 可选 kvstore 备份)
L2 UserMemory:      用户级短期记忆 (kvstore Hash + SkipList)
L3 StockMemory:      公共股票结构化记忆 (kvstore Hash)

命名空间规范:
  L1: temp:session:{sid}:*        (会话关闭即清)
  L2: user:{uid}:*                (30天未访问遗忘)
  L3: stock:{code}:*              (行情7天TTL)
"""

from __future__ import annotations

import time
import json
import logging
from typing import Optional, Dict, List, Any, TYPE_CHECKING
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from .kvstore_client import KvstoreClient

logger = logging.getLogger(__name__)


# ─── L1: 瞬时记忆 (TransientMemory) ──────────────────────────

class TransientMemory:
    """L1 会话级瞬时记忆。

    优先使用 Python dict (微秒级)，可选将摘要写入 kvstore (备份/多进程共享)。

    Usage:
        tm = TransientMemory(session_id="sess_001", client=kvstore_client)
        tm.add_turn("user", "茅台PE多少")
        tm.add_turn("assistant", "茅台PE 28.5...")
        ctx = tm.get_context(k=5)  # 最近5轮对话
        tm.track_entity("600519", "贵州茅台")
        last_stock = tm.get_last_entity("stock")  # "600519"
        tm.clear()  # 会话关闭
    """

    MAX_TURNS = 10

    def __init__(self, session_id: str, client: Optional[KvstoreClient] = None):
        self.session_id = session_id
        self._client = client
        # 最近 N 轮对话
        self._turns: List[Dict[str, Any]] = []
        # 实体追踪: {type: [entity_key, ...]}
        self._entities: Dict[str, List[str]] = {}
        # 临时偏好: {key: value}
        self._preferences: Dict[str, str] = {}
        self._created_at = time.time()

    # ── 对话轮次 ────────────────────────────────────────

    def add_turn(self, role: str, content: str):
        """添加一轮对话。"""
        self._turns.append({
            "role": role,
            "content": content[:500],  # 截断
            "timestamp": datetime.now().isoformat(),
        })
        if len(self._turns) > self.MAX_TURNS:
            self._turns = self._turns[-self.MAX_TURNS:]

    def get_context(self, k: int = 5) -> str:
        """获取最近 k 轮对话上下文，格式化为 prompt 文本。"""
        recent = self._turns[-k:]
        if not recent:
            return ""

        lines = ["【当前会话上下文】"]
        for t in recent:
            role_label = "用户" if t["role"] == "user" else "助手"
            lines.append(f"{role_label}: {t['content']}")
        return "\n".join(lines)

    def get_raw_turns(self, k: int = 5) -> List[Dict]:
        """获取原始对话数据。"""
        return self._turns[-k:]

    # ── 实体追踪 ────────────────────────────────────────

    def track_entity(self, entity_type: str, entity_key: str, entity_name: str = ""):
        """追踪会话中出现的实体。用于代词消解。

        Args:
            entity_type: "stock", "sector", "index", "concept"
            entity_key:  "600519"
            entity_name: "贵州茅台"
        """
        if entity_type not in self._entities:
            self._entities[entity_type] = []
        # 去重移到末尾 (LRU)
        lst = self._entities[entity_type]
        if entity_key in lst:
            lst.remove(entity_key)
        lst.append(entity_key)
        # 最多保留 5 个
        if len(lst) > 5:
            lst = lst[-5:]
        self._entities[entity_type] = lst

    def get_last_entity(self, entity_type: str = "stock") -> Optional[str]:
        """获取最近追踪的实体。"""
        lst = self._entities.get(entity_type, [])
        return lst[-1] if lst else None

    def get_entity_context(self) -> str:
        """获取实体上下文文本。"""
        if not self._entities:
            return ""
        parts = []
        for etype, ekeys in self._entities.items():
            parts.append(f"{etype}: {', '.join(ekeys)}")
        return " | ".join(parts)

    # ── 临时偏好 ────────────────────────────────────────

    def set_preference(self, key: str, value: str):
        self._preferences[key] = value

    def get_preference(self, key: str) -> Optional[str]:
        return self._preferences.get(key)

    # ── kvstore 持久化 (可选) ────────────────────────────

    def persist_to_kvstore(self):
        """将会话摘要写入 kvstore (多进程共享用)。"""
        if not self._client:
            return
        prefix = f"temp:session:{self.session_id}:"
        try:
            # 存储最近一轮对话的摘要
            if self._turns:
                last_turn = self._turns[-1]
                self._client.sset(
                    f"{prefix}turn:{len(self._turns)}",
                    json.dumps(last_turn, ensure_ascii=False)
                )
            # 存储实体
            if self._entities:
                self._client.hset(
                    f"{prefix}entities",
                    json.dumps(self._entities, ensure_ascii=False)
                )
        except Exception as e:
            logger.warning(f"L1 persist failed: {e}")

    def load_from_kvstore(self) -> bool:
        """从 kvstore 恢复会话状态 (进程迁移用)。"""
        if not self._client:
            return False
        prefix = f"temp:session:{self.session_id}:"
        try:
            entities_raw = self._client.hget(f"{prefix}entities")
            if entities_raw:
                self._entities = json.loads(entities_raw)
                return True
        except Exception as e:
            logger.warning(f"L1 load failed: {e}")
        return False

    # ── 生命周期 ────────────────────────────────────────

    def clear(self):
        """清空瞬时记忆 (会话关闭时调用)。"""
        self._turns.clear()
        self._entities.clear()
        self._preferences.clear()
        # 清理 kvstore 中的临时数据
        if self._client:
            try:
                prefix = f"temp:session:{self.session_id}:"
                # kvstore 没有 KEYS 命令，无法批量清空前缀。
                # 会话级数据的 key 可通过 _turns 追踪到的 key 逐个 DEL。
                # 如果 persist_to_kvstore 被调用过，这里至少清理已知的 key。
                for i in range(len(self._turns) + 1):
                    self._client.sdel(f"{prefix}turn:{i}")
                self._client.hdel(f"{prefix}entities")
            except Exception:
                pass

    def stats(self) -> Dict:
        return {
            "session_id": self.session_id,
            "turns": len(self._turns),
            "entity_types": list(self._entities.keys()),
            "age_seconds": time.time() - self._created_at,
        }


# ─── L2: 用户短期记忆 (UserMemory) ──────────────────────────

class UserMemory:
    """L2 用户级短期记忆。

    存储用户画像、关注列表、策略参数、查询历史。
    底层: kvstore Hash (字段级) + SkipList (时间有序)。

    Key 命名:
      user:{uid}:profile:name              → "张总"
      user:{uid}:profile:philosophy        → "价值投资"
      user:{uid}:profile:style             → "长期持有"
      user:{uid}:watchlist:600519          → "贵州茅台"
      user:{uid}:watchlist:000858          → "五粮液"
      user:{uid}:strategy:ma_short         → "5"
      user:{uid}:history:{timestamp}       → query_abstract (SkipList)
      user:{uid}:_keys                     → JSON list of all owned keys (for cleanup)

    Usage:
        um = UserMemory(client, user_id="default")
        um.update_profile({"name": "张总", "philosophy": "价值投资"})
        um.add_to_watchlist("600519", "贵州茅台")
        profile = um.get_profile()
        watchlist = um.get_watchlist()
    """

    PROFILE_FIELDS = [
        "name", "philosophy", "style", "experience",
        "risk_tolerance", "max_position_pct", "stop_loss_pct",
        "take_profit_pct", "preferred_sectors", "update_frequency",
    ]

    def __init__(self, client: KvstoreClient, user_id: str = "default"):
        self.client = client
        self.user_id = user_id
        self._ns = f"user:{user_id}"

    def _k(self, sub: str) -> str:
        return f"{self._ns}:{sub}"

    # ── 画像 (Profile) ─────────────────────────────────

    def update_profile(self, fields: Dict[str, str]) -> int:
        """更新用户画像。只更新传入的字段，不清空其他字段。"""
        mapping = {self._k(f"profile:{k}"): v for k, v in fields.items()}
        return self.client.hupsert_multi(mapping)

    def get_profile(self) -> Dict[str, Optional[str]]:
        """获取完整用户画像。"""
        keys = [self._k(f"profile:{f}") for f in self.PROFILE_FIELDS]
        result = self.client.hget_multi(keys)
        return {
            f: result.get(k)
            for f, k in zip(self.PROFILE_FIELDS, keys)
        }

    def get_profile_field(self, field: str) -> Optional[str]:
        return self.client.hget(self._k(f"profile:{field}"))

    def get_profile_summary(self) -> str:
        """获取画像摘要文本，注入 Agent prompt。"""
        profile = self.get_profile()
        filled = {k: v for k, v in profile.items() if v}
        if not filled:
            return "暂无用户画像"

        label_map = {
            "name": "称呼", "philosophy": "投资理念", "style": "交易风格",
            "risk_tolerance": "风险偏好", "max_position_pct": "最大仓位",
            "stop_loss_pct": "止损线", "take_profit_pct": "止盈线",
            "preferred_sectors": "偏好板块",
        }
        lines = ["【用户画像】"]
        for k, v in filled.items():
            label = label_map.get(k, k)
            lines.append(f"  {label}: {v}")
        return "\n".join(lines)

    # ── 关注列表 (Watchlist) ────────────────────────────

    def add_to_watchlist(self, stock_code: str, stock_name: str):
        """添加关注股票。"""
        key = self._k(f"watchlist:{stock_code}")
        self.client.hset(key, stock_name)
        # 同时记录访问时间 (用于遗忘机制)
        self.client.hset(
            self._k(f"access_log:{stock_code}"),
            datetime.now().strftime("%Y%m%d")
        )

    def remove_from_watchlist(self, stock_code: str):
        """移除关注股票。"""
        self.client.hdel(self._k(f"watchlist:{stock_code}"))

    def get_watchlist(self) -> Dict[str, str]:
        """获取完整关注列表。"""
        code_list = self._get_watchlist_codes()
        if not code_list:
            return {}
        result = self.client.hget_multi(
            [self._k(f"watchlist:{c}") for c in code_list]
        )
        out = {}
        for code in code_list:
            k = self._k(f"watchlist:{code}")
            name = result.get(k)
            if name is not None:
                out[code] = name
        return out

    def _get_watchlist_codes(self) -> List[str]:
        """从访问日志中恢复关注股票代码列表。"""
        # kvstore 没有 KEYS 命令的变通方案：
        # 从 access_log 索引中恢复代码列表
        index_raw = self.client.hget(self._k("_watchlist_index"))
        if index_raw:
            try:
                return json.loads(index_raw)
            except json.JSONDecodeError:
                return []
        return []

    def _save_watchlist_codes(self, codes: List[str]):
        """保存关注代码索引。"""
        self.client.hupsert(
            self._k("_watchlist_index"),
            json.dumps(codes, ensure_ascii=False)
        )

    def add_to_watchlist(self, stock_code: str, stock_name: str):
        """添加关注股票。"""
        key = self._k(f"watchlist:{stock_code}")
        ok = self.client.hset(key, stock_name)
        if not ok:
            # key 已存在，用 HMOD
            self.client.hmod(key, stock_name)
        # 更新索引
        codes = self._get_watchlist_codes()
        if stock_code not in codes:
            codes.append(stock_code)
            self._save_watchlist_codes(codes)
        # 访问日志 (首次 HSET, 后续 HMOD)
        self.client.hupsert(
            self._k(f"access_log:{stock_code}"),
            datetime.now().strftime("%Y%m%d")
        )

    def get_watchlist_summary(self) -> str:
        """获取关注列表摘要。"""
        wl = self.get_watchlist()
        if not wl:
            return ""
        lines = ["【用户关注股票】"]
        for code, name in wl.items():
            lines.append(f"  {code} {name}")
        return "\n".join(lines)

    # ── 策略参数 (Strategy) ─────────────────────────────

    def update_strategy(self, params: Dict[str, str]):
        """更新策略参数。"""
        mapping = {self._k(f"strategy:{k}"): v for k, v in params.items()}
        self.client.hset_multi(mapping)

    def get_strategy(self) -> Dict[str, Optional[str]]:
        """获取所有策略参数。"""
        # 读取所有已知策略 key
        strategy_keys = self.client.hget(self._k("_strategy_keys"))
        if not strategy_keys:
            return {}
        try:
            fields = json.loads(strategy_keys)
        except json.JSONDecodeError:
            return {}

        keys = [self._k(f"strategy:{f}") for f in fields]
        result = self.client.hget_multi(keys)
        return {f: result.get(k) for f, k in zip(fields, keys)}

    def update_strategy(self, params: Dict[str, str]):
        mapping = {self._k(f"strategy:{k}"): v for k, v in params.items()}
        self.client.hupsert_multi(mapping)
        # 更新 key 索引
        existing_raw = self.client.hget(self._k("_strategy_keys"))
        existing = json.loads(existing_raw) if existing_raw else []
        for k in params:
            if k not in existing:
                existing.append(k)
        self.client.hupsert(self._k("_strategy_keys"), json.dumps(existing))

    def get_strategy_summary(self) -> str:
        strategy = self.get_strategy()
        if not strategy:
            return ""
        lines = ["【用户策略参数】"]
        for k, v in strategy.items():
            if v:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    # ── 查询历史 (Query History, SkipList) ──────────────

    MAX_HISTORY = 100

    def add_query_history(self, query: str, answer_summary: str = ""):
        """记录查询摘要到历史 (SkipList 按时间排序)。"""
        timestamp = datetime.now().strftime("%Y%m%d:%H%M%S")
        key = self._k(f"history:{timestamp}")
        data = json.dumps({
            "query": query[:200],
            "answer": answer_summary[:200],
        }, ensure_ascii=False)
        self.client.sset(key, data)

    def get_recent_queries(self, limit: int = 10) -> List[Dict]:
        """获取最近查询摘要 (最近 N 条)。"""
        # kvstore 没有 SSCAN/REVRANGE, 无法高效获取最新N条。
        # 变通方案: 通过一个辅助列表追踪历史 key。
        index_raw = self.client.hget(self._k("_history_keys"))
        if not index_raw:
            return []
        try:
            all_keys = json.loads(index_raw)
        except json.JSONDecodeError:
            return []

        recent_keys = all_keys[-limit:]
        results = []
        for k in recent_keys:
            val = self.client.sget(k)
            if val:
                try:
                    results.append(json.loads(val))
                except json.JSONDecodeError:
                    results.append({"raw": val})
        return results

    def add_query_history(self, query: str, answer_summary: str = ""):
        timestamp = datetime.now().strftime("%Y%m%d:%H%M%S")
        key = self._k(f"history:{timestamp}")
        data = json.dumps({
            "query": query[:200],
            "answer": answer_summary[:200],
        }, ensure_ascii=False)
        self.client.sset(key, data)

        # 维护历史 key 索引
        index_raw = self.client.hget(self._k("_history_keys"))
        all_keys = json.loads(index_raw) if index_raw else []
        all_keys.append(key)
        if len(all_keys) > self.MAX_HISTORY:
            # 删除最旧的
            oldest = all_keys.pop(0)
            self.client.sdel(oldest)
        self.client.hupsert(self._k("_history_keys"), json.dumps(all_keys))

    # ── 遗忘机制辅助 ────────────────────────────────────

    def get_access_log(self) -> Dict[str, str]:
        """获取访问日志 {stock_code: last_date}。"""
        codes = self._get_watchlist_codes()
        result = {}
        for code in codes:
            date = self.client.hget(self._k(f"access_log:{code}"))
            if date:
                result[code] = date
        return result

    def update_access_time(self, stock_code: str):
        """更新访问时间。"""
        self.client.hupsert(
            self._k(f"access_log:{stock_code}"),
            datetime.now().strftime("%Y%m%d")
        )

    # ── 综合摘要 ─────────────────────────────────────────

    def get_full_summary(self) -> str:
        """获取 L2 全部信息的摘要文本。"""
        parts = [
            self.get_profile_summary(),
            self.get_watchlist_summary(),
            self.get_strategy_summary(),
        ]
        return "\n\n".join(p for p in parts if p)


# ─── L3: 股票公共结构化记忆 (StockMemory) ──────────────────

class StockMemory:
    """L3 公共股票结构化记忆。

    存储所有股票的:
      - 基础信息 (名称、行业、市值、PE、PB 等)
      - 行情快照 (最新价、涨跌幅，1~5分钟刷新)
      - RAG 索引 (指向 ChromaDB 的 doc_id)

    Key 命名:
      stock:{code}:base:name           → "贵州茅台"
      stock:{code}:base:sector         → "白酒"
      stock:{code}:base:pe_ttm         → "28.5"
      stock:{code}:quote:price         → "1445.00"
      stock:{code}:quote:change_pct    → "+1.25"
      stock:{code}:quote:update_time   → "20260512:143000"
      stock:{code}:rag:report_2025q4   → "chroma:doc:rep_600519_2025q4"

    Usage:
        sm = StockMemory(client)
        sm.update_base("600519", {"name": "贵州茅台", "sector": "白酒", "pe_ttm": "28.5"})
        sm.update_quote("600519", {"price": "1445.00", "change_pct": "+1.25"})
        info = sm.get_full_info("600519")
        sm.add_rag_index("600519", "report_2025q4", "chroma:doc:rep_600519_2025q4")
        rag_ids = sm.get_rag_ids("600519")
    """

    BASE_FIELDS = [
        "name", "sector", "industry", "market_cap",
        "pe_ttm", "pb", "turnover_rate", "listing_date",
    ]
    QUOTE_FIELDS = [
        "price", "change_pct", "volume", "high", "low", "update_time",
    ]

    def __init__(self, client: KvstoreClient):
        self.client = client

    def _k(self, code: str, sub: str) -> str:
        return f"stock:{code}:{sub}"

    # ── 基础信息 ────────────────────────────────────────

    def update_base(self, code: str, fields: Dict[str, str]):
        """更新股票基础信息。"""
        mapping = {self._k(code, f"base:{k}"): v for k, v in fields.items()}
        self.client.hupsert_multi(mapping)
        # 维护股票代码索引
        self._index_code(code)

    def get_base(self, code: str) -> Dict[str, Optional[str]]:
        keys = [self._k(code, f"base:{f}") for f in self.BASE_FIELDS]
        result = self.client.hget_multi(keys)
        return {f: result.get(k) for f, k in zip(self.BASE_FIELDS, keys)}

    def get_base_field(self, code: str, field: str) -> Optional[str]:
        return self.client.hget(self._k(code, f"base:{field}"))

    # ── 行情快照 ────────────────────────────────────────

    def update_quote(self, code: str, fields: Dict[str, str]):
        """更新行情快照。自动打时间戳。"""
        fields = dict(fields)
        fields["update_time"] = datetime.now().strftime("%Y%m%d:%H%M%S")
        mapping = {self._k(code, f"quote:{k}"): v for k, v in fields.items()}
        self.client.hupsert_multi(mapping)
        self._index_code(code)

    def get_quote(self, code: str) -> Dict[str, Optional[str]]:
        keys = [self._k(code, f"quote:{f}") for f in self.QUOTE_FIELDS]
        result = self.client.hget_multi(keys)
        return {f: result.get(k) for f, k in zip(self.QUOTE_FIELDS, keys)}

    def is_quote_stale(self, code: str, ttl_minutes: int = 7 * 24 * 60) -> bool:
        """检查行情是否过期 (默认 7 天)。"""
        update_time = self.client.hget(self._k(code, "quote:update_time"))
        if not update_time:
            return True
        try:
            t = datetime.strptime(update_time, "%Y%m%d:%H%M%S")
            return (datetime.now() - t) > timedelta(minutes=ttl_minutes)
        except ValueError:
            return True

    # ── RAG 索引 ────────────────────────────────────────

    def add_rag_index(self, code: str, doc_label: str, chroma_doc_id: str):
        """添加 RAG 文档索引: stock:{code}:rag:{label} → chroma_doc_id。"""
        self.client.hset(self._k(code, f"rag:{doc_label}"), chroma_doc_id)
        self._index_code(code)

    def get_rag_ids(self, code: str) -> Dict[str, str]:
        """获取某只股票的所有 RAG 文档索引。"""
        labels_raw = self.client.hget(self._k(code, "_rag_labels"))
        if not labels_raw:
            return {}
        try:
            labels = json.loads(labels_raw)
        except json.JSONDecodeError:
            return {}
        keys = [self._k(code, f"rag:{lbl}") for lbl in labels]
        result = self.client.hget_multi(keys)
        out = {}
        for lbl in labels:
            k = self._k(code, f"rag:{lbl}")
            doc_id = result.get(k)
            if doc_id is not None:
                out[lbl] = doc_id
        return out

    def add_rag_index(self, code: str, doc_label: str, chroma_doc_id: str):
        self.client.hupsert(self._k(code, f"rag:{doc_label}"), chroma_doc_id)
        # 维护标签索引
        labels_raw = self.client.hget(self._k(code, "_rag_labels"))
        labels = json.loads(labels_raw) if labels_raw else []
        if doc_label not in labels:
            labels.append(doc_label)
            self.client.hupsert(self._k(code, "_rag_labels"), json.dumps(labels))
        self._index_code(code)

    def remove_rag_index(self, code: str, doc_label: str):
        """删除 RAG 文档索引 (ChromaDB 删文档时联动调用)。"""
        self.client.hdel(self._k(code, f"rag:{doc_label}"))
        labels_raw = self.client.hget(self._k(code, "_rag_labels"))
        if labels_raw:
            try:
                labels = json.loads(labels_raw)
                if doc_label in labels:
                    labels.remove(doc_label)
                    self.client.hupsert(self._k(code, "_rag_labels"), json.dumps(labels))
            except json.JSONDecodeError:
                pass

    # ── 综合查询 ────────────────────────────────────────

    def get_full_info(self, code: str) -> Dict[str, Any]:
        """获取某只股票的全部信息。"""
        return {
            "code": code,
            "base": self.get_base(code),
            "quote": self.get_quote(code),
            "rag_ids": self.get_rag_ids(code),
            "quote_stale": self.is_quote_stale(code),
            "metrics": self.get_metrics(code),
        }

    # ── 财务指标 (L3 结构化数据) ────────────────────────

    METRIC_KEYS = [
        "revenue", "cost", "net_profit", "net_profit_dedup",
        "fin_expense", "sell_expense", "admin_expense", "rd_expense",
        "tax_surcharge", "invest_income", "oper_profit", "total_profit",
        "total_assets", "total_liability", "net_assets",
        "cash", "receivables", "inventory", "fixed_assets",
        "short_loan", "long_loan",
        "oper_cf", "invest_cf", "fin_cf",
        "roe", "eps", "eps_diluted", "gross_margin", "net_margin",
    ]

    def update_metrics(self, code: str, metrics: dict):
        """存储结构化财务指标到 kvstore。"""
        if not metrics:
            return
        mapping = {self._k(code, f"metric:{k}"): v for k, v in metrics.items() if v}
        if mapping:
            self.client.hupsert_multi(mapping)

    def get_metrics(self, code: str) -> Dict[str, Optional[str]]:
        """获取某只股票的所有结构化财务指标。O(1) 精确查询。"""
        keys = [self._k(code, f"metric:{k}") for k in self.METRIC_KEYS]
        result = self.client.hget_multi(keys)
        return {k: result.get(self._k(code, f"metric:{k}"))
                for k in self.METRIC_KEYS}

    def get_metric(self, code: str, metric_key: str) -> Optional[str]:
        """获取单个财务指标。O(1)。"""
        return self.client.hget(self._k(code, f"metric:{metric_key}"))

    # ── 代码索引 (维护已知股票代码列表) ─────────────────

    def _index_code(self, code: str):
        """将股票代码加入全局索引。"""
        existing_raw = self.client.hget("stock:_index:_codes")
        codes = json.loads(existing_raw) if existing_raw else []
        if code not in codes:
            codes.append(code)
            self.client.hupsert("stock:_index:_codes", json.dumps(codes))

    def get_all_codes(self) -> List[str]:
        """获取所有已缓存的股票代码。"""
        raw = self.client.hget("stock:_index:_codes")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    def delete_stock(self, code: str):
        """删除某只股票的全部缓存数据。"""
        codes = self.get_all_codes()
        if code in codes:
            codes.remove(code)
            self.client.hupsert("stock:_index:_codes", json.dumps(codes))
        # 清理基础字段
        for f in self.BASE_FIELDS:
            self.client.hdel(self._k(code, f"base:{f}"))
        for f in self.QUOTE_FIELDS:
            self.client.hdel(self._k(code, f"quote:{f}"))
        # 清理 RAG 索引
        labels_raw = self.client.hget(self._k(code, "_rag_labels"))
        if labels_raw:
            try:
                labels = json.loads(labels_raw)
                for lbl in labels:
                    self.client.hdel(self._k(code, f"rag:{lbl}"))
            except json.JSONDecodeError:
                pass
        self.client.hdel(self._k(code, "_rag_labels"))
