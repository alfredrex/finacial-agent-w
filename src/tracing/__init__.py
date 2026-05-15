"""
Unified Trace Logging Module

Provides non-invasive span-based tracing for:
  - router, SQL, RAG, LLM, tool call, agent execution
  - Each span records latency, status, error, input/output summary
  - JSONL output to logs/traces/
  - Reusable by eval scripts and load tests.

Quick Start:
    from src.tracing import trace_logger, Span, start_trace, end_trace

    # In main entry (once per request):
    trace_id = start_trace()

    # In any component:
    with trace_logger.span("router", "茅台2026Q1净利润") as span:
        plan = router.route(query)
        span.set_output(str(plan))

    # After request:
    end_trace()
"""

from .logger import (
    TraceLogger,
    Span,
    trace_logger,
    start_trace,
    end_trace,
    trace_async_span,
    trace_span,
)
from .context import (
    is_enabled,
    get_trace_id,
    get_current_span,
)

__all__ = [
    "TraceLogger",
    "Span",
    "trace_logger",
    "start_trace",
    "end_trace",
    "trace_async_span",
    "trace_span",
    "is_enabled",
    "get_trace_id",
    "get_current_span",
]
