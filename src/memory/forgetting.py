"""
遗忘机制

管理四层记忆的数据生命周期，防止记忆膨胀和过时数据误导。

触发时机:
  - L1: 会话关闭 → 全清
  - L2: 每次 retrieve() 调用时检查 → 30天未访问的股票移除
  - L3: 每次读取行情时检查 → 7天过期 → 标记刷新
  - L4: 定时任务 → 1年以上研报复查 → 归档

Usage:
    fm = ForgettingManager(kvstore_client, chroma_client)
    fm.on_session_close(session_id)
    fm.check_l2_user("default")       # 检查 L2 遗忘
    fm.check_l3_quotes(["600519"])    # 检查 L3 行情过期
    await fm.check_l4_archive()       # L4 归档检查
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


class ForgettingManager:
    """统一遗忘管理。

    Retention 配置:
      L2_RETENTION_DAYS: 关注股票 30 天未访问 → 移除
      L2_HISTORY_MAX:    查询历史上限 100 条
      L3_PRICE_TTL_DAYS: 行情快照 7 天过期
      L4_ARCHIVE_DAYS:   研报/财报 365 天归档
    """

    L2_RETENTION_DAYS = 30
    L2_HISTORY_MAX = 100
    L3_PRICE_TTL_DAYS = 7
    L4_ARCHIVE_DAYS = 365

    def __init__(
        self,
        kvstore_client: KvstoreClient,
        chroma_store: Any = None,  # LangChain Chroma vectorstore
    ):
        self.client = kvstore_client
        self.chroma_store = chroma_store

    # ── L1 瞬时记忆遗忘 ──────────────────────────────

    def on_session_close(self, session_id: str):
        """L1 遗忘: 清空会话级数据。"""
        # L1 数据在 Python dict 中，调用者需自行调用 l1.clear()
        # 这里清理可能的 kvstore 残留
        prefix = f"temp:session:{session_id}:"
        try:
            # kvstore 不支持 KEYS，清理已知 key
            # 会话实体
            self.client.hdel(f"{prefix}entities")
            # 对话轮次 (最多清理 20 轮)
            for i in range(20):
                self.client.sdel(f"{prefix}turn:{i}")
            logger.info(f"L1 遗忘: session={session_id}")
        except Exception as e:
            logger.warning(f"L1 cleanup failed: {e}")

    # ── L2 用户记忆遗忘 ──────────────────────────────

    def check_l2_user(self, user_id: str) -> Dict[str, Any]:
        """检查 L2 用户数据是否需要遗忘。

        Returns:
            {"removed_stocks": [...], "trimmed_history": N}
        """
        result = {"removed_stocks": [], "trimmed_history": 0}
        ns = f"user:{user_id}"

        # 1. 检查关注股票 (30天未访问 → 移除)
        codes_raw = self.client.hget(f"{ns}:_watchlist_index")
        codes = json.loads(codes_raw) if codes_raw else []

        now = datetime.now()
        remaining_codes = []

        for code in codes:
            access_date_str = self.client.hget(f"{ns}:access_log:{code}")
            if access_date_str:
                try:
                    access_date = datetime.strptime(access_date_str, "%Y%m%d")
                    days_since = (now - access_date).days
                    if days_since > self.L2_RETENTION_DAYS:
                        # 移除
                        self.client.hdel(f"{ns}:watchlist:{code}")
                        self.client.hdel(f"{ns}:access_log:{code}")
                        result["removed_stocks"].append(code)
                        logger.info(
                            f"L2 遗忘: user={user_id} stock={code} "
                            f"(last_access={days_since}d ago)"
                        )
                        continue
                except ValueError:
                    pass
            remaining_codes.append(code)

        # 更新索引
        if remaining_codes != codes:
            self.client.hset(
                f"{ns}:_watchlist_index",
                json.dumps(remaining_codes)
            )

        # 2. 查询历史裁剪 (保留最近 100 条)
        history_keys_raw = self.client.hget(f"{ns}:_history_keys")
        if history_keys_raw:
            try:
                all_keys = json.loads(history_keys_raw)
                if len(all_keys) > self.L2_HISTORY_MAX:
                    excess = len(all_keys) - self.L2_HISTORY_MAX
                    for old_key in all_keys[:excess]:
                        self.client.sdel(old_key)
                    remaining = all_keys[excess:]
                    self.client.hset(
                        f"{ns}:_history_keys",
                        json.dumps(remaining)
                    )
                    result["trimmed_history"] = excess
            except json.JSONDecodeError:
                pass

        return result

    # ── L3 股票行情过期检查 ──────────────────────────

    def check_l3_quotes(self, stock_codes: List[str]) -> Dict[str, bool]:
        """检查 L3 行情快照是否过期。

        Returns:
            {code: is_stale} 过期则需调用者异步刷新
        """
        result = {}
        for code in stock_codes:
            update_time = self.client.hget(f"stock:{code}:quote:update_time")
            if not update_time:
                result[code] = True
                continue
            try:
                t = datetime.strptime(update_time, "%Y%m%d:%H%M%S")
                days_since = (datetime.now() - t).days
                result[code] = days_since > self.L3_PRICE_TTL_DAYS
            except ValueError:
                result[code] = True
        return result

    def mark_l3_stale(self, stock_codes: List[str]):
        """标记 L3 行情为过期 (强制下次刷新)。"""
        for code in stock_codes:
            self.client.hset(
                f"stock:{code}:quote:update_time",
                "20000101:000000"  # 远古时间戳
            )

    # ── L4 RAG 归档 ──────────────────────────────────

    async def check_l4_archive(self) -> Dict[str, Any]:
        """检查 L4 文档是否需要归档。"""
        if not self.chroma_store:
            return {"archived": [], "error": "ChromaDB not available"}

        try:
            # LangChain Chroma.get() — 获取所有文档
            result = self.chroma_store.get()
            if not result or not result.get("metadatas"):
                return {"archived": [], "count": 0}

            cutoff = datetime.now() - timedelta(days=self.L4_ARCHIVE_DAYS)
            to_archive = []

            for i, (doc_id, meta) in enumerate(
                zip(result.get("ids", []), result["metadatas"])
            ):
                date_str = meta.get("date", "") if meta else ""
                if date_str:
                    try:
                        doc_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
                        if doc_date < cutoff:
                            to_archive.append({
                                "doc_id": doc_id,
                                "title": meta.get("title", ""),
                                "date": date_str,
                                "source": meta.get("source", ""),
                            })
                    except ValueError:
                        pass

            logger.info(f"L4 归档检查: {len(to_archive)} 个文档超过 {self.L4_ARCHIVE_DAYS} 天")
            return {"to_archive": to_archive, "count": len(to_archive)}

        except Exception as e:
            logger.warning(f"L4 archive check failed: {e}")
            return {"archived": [], "error": str(e)}

    async def archive_documents(self, doc_ids: List[str]) -> int:
        """将指定文档从 ChromaDB 移到归档。

        L3 RAG 索引联动清理由调用者完成。
        """
        if not self.chroma_store or not doc_ids:
            return 0

        try:
            # LangChain Chroma.get(ids=...) + delete(ids=...)
            result = self.chroma_store.get(ids=doc_ids)
            if result and result.get("documents"):
                import os
                archive_dir = "data_cache/rag_archive"
                os.makedirs(archive_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                for doc_id, doc, meta in zip(
                    doc_ids,
                    result["documents"],
                    result.get("metadatas", [{}] * len(doc_ids)),
                ):
                    archive_file = f"{archive_dir}/{timestamp}_{doc_id}.json"
                    with open(archive_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "doc_id": doc_id,
                            "content": doc[:5000],
                            "metadata": meta,
                            "archived_at": timestamp,
                        }, f, ensure_ascii=False, indent=2)

                # 从 ChromaDB 删除
                self.chroma_store.delete(ids=doc_ids)
                logger.info(f"L4 归档: {len(doc_ids)} docs → {archive_dir}/")
                return len(doc_ids)

        except Exception as e:
            logger.warning(f"L4 archive failed: {e}")
            return 0

    # ── 全量遗忘运行 ──────────────────────────────────

    async def run_full_cycle(self, user_id: str = "default") -> Dict[str, Any]:
        """执行完整遗忘周期 (可配置为 cron 定时任务)。

        调用顺序:
          1. L2 用户遗忘检查
          2. L3 全局股票行情过期检查
          3. L4 归档检查
        """
        results = {}

        # L2
        l2_result = self.check_l2_user(user_id)
        results["l2"] = l2_result

        # L3: 全量检查所有已知股票
        codes_raw = self.client.hget("stock:_index:_codes")
        all_codes = json.loads(codes_raw) if codes_raw else []
        if all_codes:
            stale_map = self.check_l3_quotes(all_codes[:200])  # 一次最多 200
            stale_codes = [c for c, is_stale in stale_map.items() if is_stale]
            results["l3"] = {"checked": len(all_codes[:200]), "stale": len(stale_codes)}

        # L4
        if self.chroma_store:
            l4_result = await self.check_l4_archive()
            results["l4"] = l4_result

        return results
