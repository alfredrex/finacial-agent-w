"""
记忆合并器 (Memory Consolidator)
定期后台任务：合并相似记忆、衰减重要性、删除低价值/过期记忆
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta

from src.memory.episodic_memory import episodic_memory_manager


logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """记忆合并器 """

    def __init__(self, interval_hours: float = 24.0):
        self.interval_hours = interval_hours
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_stats: dict = {}

    async def consolidate(self):
        """执行一次合并"""
        deleted = episodic_memory_manager.consolidate(
            max_age_days=90, min_importance=0.1
        )
        self.last_run = datetime.now()
        self.last_stats = {
            "deleted": deleted,
            "timestamp": self.last_run.isoformat(),
        }
        if deleted > 0:
            logger.info(f"MemoryConsolidator: 清理了 {deleted} 条过期低价值记忆")

    async def run_loop(self):
        """后台循环运行"""
        self._running = True
        while self._running:
            await asyncio.sleep(self.interval_hours * 3600)
            try:
                await self.consolidate()
            except Exception as e:
                logger.error(f"MemoryConsolidator 合并失败: {e}")

    def start(self):
        """以后台任务启动合并循环（无 event loop 时静默跳过，async 下自动重试）"""
        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return  # no running event loop, start() will be called again from run()
            self._task = loop.create_task(self.run_loop())

    def stop(self):
        """停止合并循环"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


# 全局实例
consolidator = MemoryConsolidator()
