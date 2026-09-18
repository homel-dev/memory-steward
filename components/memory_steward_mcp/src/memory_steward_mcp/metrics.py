from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

TOOL_CALLS = Counter(
    "memory_steward_mcp_tool_calls_total",
    "Memory Steward MCP tool calls by tool and outcome.",
    ("tool", "status"),
    registry=REGISTRY,
)
TOOL_DURATION = Histogram(
    "memory_steward_mcp_tool_duration_seconds",
    "Memory Steward MCP tool execution latency.",
    ("tool",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
    registry=REGISTRY,
)


def started() -> float:
    return time.monotonic()


def observe(tool: str, status: str, started_at: float) -> float:
    duration_seconds = max(time.monotonic() - started_at, 0.0)
    TOOL_CALLS.labels(tool=tool, status=status).inc()
    TOOL_DURATION.labels(tool=tool).observe(duration_seconds)
    return duration_seconds * 1000.0


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
