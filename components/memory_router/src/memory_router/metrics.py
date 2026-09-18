from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

REQUESTS = Counter(
    "memory_steward_router_requests_total",
    "Memory Router HTTP operations by operation and outcome.",
    ("operation", "status"),
    registry=REGISTRY,
)
REQUEST_DURATION = Histogram(
    "memory_steward_router_request_duration_seconds",
    "Memory Router HTTP operation latency.",
    ("operation",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60),
    registry=REGISTRY,
)
RESULTS = Counter(
    "memory_steward_router_results_total",
    "Items returned or selected by retrieval operations.",
    ("operation",),
    registry=REGISTRY,
)
RETRIEVAL_CANDIDATES = Counter(
    "memory_steward_router_retrieval_candidates_total",
    "Candidates considered by retrieval operations.",
    ("operation",),
    registry=REGISTRY,
)
RETRIEVAL_SELECTED = Counter(
    "memory_steward_router_retrieval_selected_total",
    "Candidates selected by retrieval operations.",
    ("operation",),
    registry=REGISTRY,
)


def started() -> float:
    return time.monotonic()


def observe(operation: str, status: str, started_at: float, *, results: int | None = None) -> float:
    duration_seconds = max(time.monotonic() - started_at, 0.0)
    REQUESTS.labels(operation=operation, status=status).inc()
    REQUEST_DURATION.labels(operation=operation).observe(duration_seconds)
    if results is not None:
        RESULTS.labels(operation=operation).inc(max(results, 0))
    return duration_seconds * 1000.0


def observe_retrieval(operation: str, *, candidates: int, selected: int) -> None:
    RETRIEVAL_CANDIDATES.labels(operation=operation).inc(max(candidates, 0))
    RETRIEVAL_SELECTED.labels(operation=operation).inc(max(selected, 0))


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
