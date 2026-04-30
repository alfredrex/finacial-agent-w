"""
黑板模式 (Blackboard)
结构化共享工作区：命名空间分区 + 版本化更新 + 变更通知
"""
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from collections import defaultdict

from src.communication.models import BlackboardEntry


class Blackboard:
    """Agent 协作黑板"""

    def __init__(self):
        self._store: Dict[str, Dict[str, BlackboardEntry]] = defaultdict(dict)
        self._watchers: Dict[str, List[Callable]] = defaultdict(list)

    def write(self, namespace: str, key: str, value: Any,
              updated_by: Optional[str] = None) -> BlackboardEntry:
        """写入数据到黑板"""
        existing = self._store[namespace].get(key)
        version = (existing.version + 1) if existing else 1
        entry = BlackboardEntry(
            namespace=namespace,
            key=key,
            value=value,
            version=version,
            updated_by=updated_by,
        )
        self._store[namespace][key] = entry
        # 通知监听者
        full_key = f"{namespace}.{key}"
        for callback in self._watchers.get(full_key, []):
            try:
                callback(entry)
            except Exception:
                pass
        return entry

    def read(self, namespace: str, key: str) -> Optional[Any]:
        """读取数据"""
        entry = self._store.get(namespace, {}).get(key)
        return entry.value if entry else None

    def read_entry(self, namespace: str, key: str) -> Optional[BlackboardEntry]:
        """读取完整条目 (含版本号)"""
        return self._store.get(namespace, {}).get(key)

    def watch(self, namespace_key: str, callback: Callable):
        """监听特定键的变化 (格式: "namespace.key")"""
        self._watchers[namespace_key].append(callback)

    def get_namespace(self, namespace: str) -> Dict[str, BlackboardEntry]:
        """获取整个命名空间"""
        return dict(self._store.get(namespace, {}))

    def get_history(self, namespace: str, key: str) -> List[BlackboardEntry]:
        """获取变更历史 (当前只保留最新版本)"""
        entry = self.read_entry(namespace, key)
        return [entry] if entry else []

    def clear_namespace(self, namespace: str):
        """清除命名空间"""
        if namespace in self._store:
            del self._store[namespace]

    def clear_all(self):
        self._store.clear()


# 全局实例
blackboard = Blackboard()
