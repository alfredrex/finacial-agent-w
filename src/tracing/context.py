"""
Trace context propagation via contextvars.

Works across asyncio tasks — each request gets its own trace_id.
"""

from __future__ import annotations

import contextvars
from typing import Optional

# ─── Context Variables ───────────────────────────────

_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_current_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_span_id", default=None
)
_trace_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "trace_enabled", default=False
)


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


def get_trace_id() -> Optional[str]:
    return _trace_id.get()


def set_current_span(span_id: Optional[str]) -> None:
    _current_span_id.set(span_id)


def get_current_span() -> Optional[str]:
    return _current_span_id.get()


def enable() -> None:
    _trace_enabled.set(True)


def disable() -> None:
    _trace_enabled.set(False)


def is_enabled() -> bool:
    return _trace_enabled.get()
