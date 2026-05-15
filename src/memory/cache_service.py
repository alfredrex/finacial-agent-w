"""
KVStore CacheService — 带逻辑 TTL 的缓存服务

在 value 中嵌入 meta 层实现 TTL，不修改 kvstore 底层。

TTL 策略:
  quote:           60-300 秒
  news:            30 分钟-2 小时
  announcement:    1 天
  policy_search:   1-7 天
  user_profile:    不过期

Usage:
    from src.memory.cache_service import CacheService
    cs = CacheService(kvstore_client)
    cs.set("cache:quote:002594", {"price": 1445.0}, ttl=300)
    data = cs.get("cache:quote:002594")  # None if expired
"""

from __future__ import annotations

import json
import time
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory.kvstore_client import KvstoreClient

logger = logging.getLogger(__name__)

# ─── TTL 策略 ───────────────────────────────────────

DEFAULT_TTL = {
    "quote": 300,           # 5 分钟
    "news": 3600,           # 1 小时
    "announcement": 86400,  # 1 天
    "policy": 604800,       # 7 天
    "report_index": 86400,  # 1 天
    "user_profile": 0,      # 不过期
    "doc_status": 0,        # 不过期
}


class CacheService:
    """基于 kvstore 的缓存服务，带逻辑 TTL。"""

    def __init__(self, kvstore_client: KvstoreClient):
        self._kv = kvstore_client

    def set(self, key: str, data: Any, ttl: int = None,
            data_type: str = "generic", source: str = "") -> bool:
        """
        写入缓存。
        Args:
            key:     kvstore key
            data:    要缓存的数据 (dict/list/str)
            ttl:     过期秒数。0=永不过期, None=使用 data_type 默认值
            data_type: quote/news/announcement/policy/report_index
            source:  数据来源标记 (URL/API名)
        """
        if ttl is None:
            ttl = DEFAULT_TTL.get(data_type, 3600)

        now = int(time.time())
        expire_at = now + ttl if ttl > 0 else 0

        payload = {
            "data": data,
            "meta": {
                "created_at": now,
                "expire_at": expire_at,
                "source": source,
                "data_type": data_type,
            },
        }

        raw = json.dumps(payload, ensure_ascii=False)
        return self._kv.set(key, raw)

    def get(self, key: str) -> Optional[Any]:
        """读取缓存。过期返回 None。"""
        raw = self._kv.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw  # 旧格式，无 meta

        meta = payload.get("meta", {})
        expire_at = meta.get("expire_at", 0)

        if expire_at > 0 and int(time.time()) > expire_at:
            logger.debug(f"Cache expired: {key}")
            return None

        return payload.get("data")

    def get_meta(self, key: str) -> Optional[dict]:
        """读取缓存元信息（不检查过期）。"""
        raw = self._kv.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return payload.get("meta")

    def is_fresh(self, key: str) -> bool:
        """检查缓存是否新鲜。"""
        return self.get(key) is not None

    def is_stale(self, key: str) -> bool:
        """检查缓存是否过期。"""
        return not self.is_fresh(key)

    def delete(self, key: str) -> bool:
        """删除缓存项。"""
        return self._kv.delete(key)

    def get_or_set(self, key: str, factory, ttl: int = None,
                   data_type: str = "generic", source: str = "") -> Any:
        """缓存命中返回，未命中则调用 factory() 生成并缓存。"""
        data = self.get(key)
        if data is not None:
            return data
        data = factory()
        if data is not None:
            self.set(key, data, ttl=ttl, data_type=data_type, source=source)
        return data
