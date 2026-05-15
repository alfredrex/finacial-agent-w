#!/usr/bin/env python3
"""
Eval 脚本示例 — 展示如何复用 trace logger 进行评测和压测。

评测时:
  1. 调用 start_trace() 获得 trace_id
  2. 正常执行业务流程（trace 自动记录各 span）
  3. 调用 end_trace() 结束
  4. 读取 JSONL 分析各组件延迟

Usage:
    python tests/eval_with_trace.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracing import trace_logger, start_trace, end_trace
import json
import statistics


def run_single_eval(query: str) -> dict:
    """模拟一次评测 — 追踪所有 span。"""
    tid = start_trace()
    
    # 模拟业务流程（实际使用时替换为真实调用）
    trace_logger.quick_span("router", 1.2,
        input_summary=query[:200],
        output_summary="type=metric_query, ticker=600519")
    
    trace_logger.quick_span("sql:query_metric", 2.5,
        input_summary="600519/2026Q1/net_profit",
        output_summary="hit")
    
    trace_logger.quick_span("rag:search", 35.0,
        input_summary=query[:200],
        output_summary="3 docs")
    
    trace_logger.quick_span("llm", 1200.0,
        input_summary="QAAgent",
        output_summary="answer=茅台PE为28.5倍")
    
    end_trace()
    return {
        "trace_id": tid,
        "file": str(trace_logger.file_path),
        "span_count": trace_logger.span_count,
    }


def analyze_traces(trace_files: list) -> dict:
    """分析 trace 文件，汇总各组件延迟统计。"""
    stats = {}
    
    for fpath in trace_files:
        with open(fpath) as f:
            for line in f:
                span = json.loads(line)
                name = span["name"]
                if name not in stats:
                    stats[name] = []
                stats[name].append(span["latency_ms"])
    
    result = {}
    for name, latencies in sorted(stats.items()):
        result[name] = {
            "count": len(latencies),
            "p50_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 2) if len(latencies) >= 20 else None,
            "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 2) if len(latencies) >= 100 else None,
            "avg_ms": round(statistics.mean(latencies), 2),
            "total_ms": round(sum(latencies), 2),
        }
    
    return result


if __name__ == "__main__":
    # 模拟 5 轮评测
    results = []
    for i in range(5):
        r = run_single_eval(f"测试问题 {i+1}")
        results.append(r)
        print(f"[{i+1}] trace_id={r['trace_id'][:8]}... spans={r['span_count']}")
    
    print(f"\nTraces written to: logs/traces/")
    
    # 分析
    from pathlib import Path
    traces_dir = Path("logs/traces")
    files = sorted(traces_dir.glob("*.jsonl"))[-5:]
    stats = analyze_traces([str(f) for f in files])
    
    print("\n=== Latency Summary ===")
    for name, s in stats.items():
        print(f"  {name:25s} | n={s['count']:3d} | avg={s['avg_ms']:8.2f}ms | p50={s['p50_ms']:8.2f}ms")
