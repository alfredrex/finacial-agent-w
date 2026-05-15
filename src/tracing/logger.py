"""
Unified Trace Logger — non-invasive JSONL trace recording.

Features:
  - Per-request trace_id (UUID4)
  - Span-based latency recording for: router, SQL, RAG, LLM, tool, agent
  - Each span records: status, error, input_summary, output_summary, latency_ms
  - Thread-safe JSONL output to logs/traces/
  - contextvars propagation across asyncio tasks
  - Zero overhead when not initialized (all calls are no-ops)
  - Reusable by eval scripts and load tests

Usage:
    from src.tracing import trace_logger, Span, start_trace

    # In main entry point:
    start_trace()  # generates trace_id, enables context propagation

    # In any component:
    async with Span("router", input_summary="茅台2026Q1净利润") as span:
        result = router.route(query)
        span.set_output(str(result)[:200])

    # Or sync:
    with trace_logger.span("sql", input_summary="SELECT ...") as span:
        rows = cursor.fetchall()
        span.set_output(f"{len(rows)} rows")

    # After request ends:
    trace_logger.flush()
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

from . import context as ctx

# ─── Constants ────────────────────────────────────────

TRACES_DIR = Path(__file__).parent.parent.parent / "logs" / "traces"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(obj: Any, max_len: int = 300) -> str:
    """Summarize any object to a short string."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj[:max_len]
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, (list, tuple)):
        return f"[{len(obj)} items]"
    if isinstance(obj, dict):
        keys = list(obj.keys())[:5]
        return f"dict({', '.join(str(k) for k in keys)}{'...' if len(obj) > 5 else ''})"
    s = str(obj)
    return s[:max_len]


# ─── Span ─────────────────────────────────────────────


class Span:
    """A single operation span within a trace.

    Use as context manager:
        async with Span("tool", input_summary="get_stock_realtime(600519)") as span:
            result = tool.call(...)
            span.set_output(str(result)[:200])
    """

    __slots__ = (
        "trace_id", "span_id", "parent_span_id", "name",
        "input_summary", "output_summary", "status", "error",
        "_start", "latency_ms", "timestamp", "metadata",
    )

    def __init__(
        self,
        name: str,
        input_summary: str = "",
        parent_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.trace_id = ctx.get_trace_id() or ""
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_span_id = parent_span_id or ctx.get_current_span() or ""
        self.name = name
        self.input_summary = input_summary
        self.output_summary = ""
        self.status = "ok"
        self.error = ""
        self._start: Optional[float] = None
        self.latency_ms: float = 0.0
        self.timestamp = ""
        self.metadata = metadata or {}

    def start(self) -> None:
        self._start = time.monotonic()
        self.timestamp = _utcnow_iso()

    def stop(self) -> None:
        if self._start is not None:
            self.latency_ms = (time.monotonic() - self._start) * 1000

    def set_output(self, output: Any) -> None:
        self.output_summary = _summarize(output)

    def set_error(self, error: str) -> None:
        self.status = "error"
        self.error = error

    def set_status(self, status: str) -> None:
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "status": self.status,
            "error": self.error,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "latency_ms": round(self.latency_ms, 3),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


# ─── TraceLogger ──────────────────────────────────────


class TraceLogger:
    """Singleton JSONL trace logger.

    Thread-safe. Auto-creates logs/traces/ directory.
    Flushes on every write for durability (configurable).
    """

    _instance: Optional["TraceLogger"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    cls._instance = obj
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._file = None
        self._file_path: Optional[Path] = None
        self._write_lock = threading.Lock()
        self._auto_flush = True
        self._span_count = 0

    # ─── Lifecycle ────────────────────────────────────

    def init(self, trace_id: Optional[str] = None) -> str:
        """Initialize a trace session. Returns trace_id."""
        trace_id = trace_id or uuid.uuid4().hex
        TRACES_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file_path = TRACES_DIR / f"trace_{timestamp}_{trace_id[:8]}.jsonl"
        self._file = open(str(self._file_path), "a", encoding="utf-8")
        self._span_count = 0

        ctx.set_trace_id(trace_id)
        ctx.enable()
        return trace_id

    def close(self) -> None:
        """Close trace file."""
        with self._write_lock:
            if self._file:
                self._file.close()
                self._file = None
        ctx.disable()
        ctx.set_trace_id(None)

    def flush(self) -> None:
        """Flush pending writes to disk."""
        with self._write_lock:
            if self._file:
                self._file.flush()
                os.fsync(self._file.fileno())

    # ─── Span Management ──────────────────────────────

    def write_span(self, span: Span) -> None:
        """Write a span to JSONL. Called automatically on span exit."""
        if not ctx.is_enabled() or not self._file:
            return
        with self._write_lock:
            line = json.dumps(span.to_dict(), ensure_ascii=False)
            self._file.write(line + "\n")
            self._span_count += 1
            if self._auto_flush:
                self._file.flush()

    @contextmanager
    def span(
        self,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Sync span context manager.

        Usage:
            with trace_logger.span("sql", input_summary="SELECT...") as span:
                result = db.query(...)
                span.set_output(str(result)[:200])
        """
        if not ctx.is_enabled():
            yield None
            return

        span = Span(name=name, input_summary=input_summary, metadata=metadata)
        span.start()
        prev_span = ctx.get_current_span()
        ctx.set_current_span(span.span_id)
        try:
            yield span
        except Exception as e:
            span.set_error(str(e))
            raise
        finally:
            span.stop()
            self.write_span(span)
            ctx.set_current_span(prev_span)

    @asynccontextmanager
    async def async_span(
        self,
        name: str,
        input_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Async span context manager.

        Usage:
            async with trace_logger.async_span("llm", input_summary="call deepseek") as span:
                result = await llm.ainvoke(...)
                span.set_output(str(result)[:200])
        """
        if not ctx.is_enabled():
            yield None
            return

        span = Span(name=name, input_summary=input_summary, metadata=metadata)
        span.start()
        prev_span = ctx.get_current_span()
        ctx.set_current_span(span.span_id)
        try:
            yield span
        except Exception as e:
            span.set_error(str(e))
            raise
        finally:
            span.stop()
            self.write_span(span)
            ctx.set_current_span(prev_span)

    # ─── Convenience Methods ──────────────────────────

    def quick_span(
        self,
        name: str,
        latency_ms: float,
        status: str = "ok",
        input_summary: str = "",
        output_summary: str = "",
        error: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write a span directly without context manager.

        For simple cases where you already have timing data.
        """
        if not ctx.is_enabled() or not self._file:
            return
        span = Span(name=name, input_summary=input_summary, metadata=metadata)
        span.timestamp = _utcnow_iso()
        span.latency_ms = latency_ms
        span.status = status
        span.output_summary = output_summary
        span.error = error
        span.trace_id = ctx.get_trace_id() or ""
        span.parent_span_id = ctx.get_current_span() or ""
        self.write_span(span)

    def record_error(
        self,
        name: str,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an error span."""
        self.quick_span(
            name=name,
            latency_ms=0,
            status="error",
            error=error,
            metadata=metadata,
        )

    # ─── Properties ───────────────────────────────────

    @property
    def span_count(self) -> int:
        return self._span_count

    @property
    def file_path(self) -> Optional[Path]:
        return self._file_path


# ─── Global Instance ──────────────────────────────────

trace_logger = TraceLogger()


# ─── High-level API ───────────────────────────────────


def start_trace(trace_id: Optional[str] = None) -> str:
    """Start a new trace session. Call at the beginning of each request.

    Returns the trace_id.
    """
    return trace_logger.init(trace_id)


def end_trace() -> None:
    """End the current trace session. Call after request completes."""
    trace_logger.flush()
    trace_logger.close()


def trace_async_span(name: str, **kwargs):
    """Decorator-free helper: returns an async context manager."""
    return trace_logger.async_span(name, **kwargs)


def trace_span(name: str, **kwargs):
    """Decorator-free helper: returns a sync context manager."""
    return trace_logger.span(name, **kwargs)
