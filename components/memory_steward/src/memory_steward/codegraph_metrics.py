from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

from memory_steward.codegraph_builds import BuildTelemetrySnapshot

REGISTRY = CollectorRegistry(auto_describe=True)

EVENTS = Counter(
    "memory_steward_codegraph_events_total",
    "Flux events handled by the CodeGraph ingress, by outcome.",
    ("outcome",),
    registry=REGISTRY,
)
WORKFLOW_OPERATIONS = Counter(
    "memory_steward_codegraph_workflow_operations_total",
    "CodeGraph build controller operations, by operation and outcome.",
    ("operation", "outcome"),
    registry=REGISTRY,
)
BUILDS = Gauge(
    "memory_steward_codegraph_builds",
    "Durable CodeGraph build rows by current state (queried from PostgreSQL).",
    ("state",),
    registry=REGISTRY,
)
LAST_RECEIVED = Gauge(
    "memory_steward_codegraph_last_received_timestamp_seconds",
    "Unix timestamp of the latest durable CodeGraph build received; zero if none.",
    registry=REGISTRY,
)
LAST_SUCCEEDED = Gauge(
    "memory_steward_codegraph_last_succeeded_timestamp_seconds",
    "Unix timestamp of the latest successful CodeGraph build; zero if none.",
    registry=REGISTRY,
)
OLDEST_ACTIVE_AGE = Gauge(
    "memory_steward_codegraph_oldest_active_age_seconds",
    "Age of the oldest received, submitted, or running CodeGraph build; zero if none.",
    registry=REGISTRY,
)
WORKER_DURATION = Histogram(
    "memory_steward_codegraph_worker_duration_seconds",
    "Successful Flux CodeGraph worker duration, including fetch, index and publish.",
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
    registry=REGISTRY,
)

STATES = ("received", "submitted", "running", "succeeded", "failed", "superseded")

for state in STATES:
    BUILDS.labels(state=state).set(0)
for outcome in ("accepted", "duplicate", "ignored", "invalid", "unauthorized"):
    EVENTS.labels(outcome=outcome).inc(0)
for operation in ("submit", "observe"):
    for outcome in ("succeeded", "failed", "superseded", "running", "error"):
        WORKFLOW_OPERATIONS.labels(operation=operation, outcome=outcome).inc(0)


def refresh(snapshot: BuildTelemetrySnapshot) -> None:
    for state in STATES:
        BUILDS.labels(state=state).set(snapshot.counts.get(state, 0))
    LAST_RECEIVED.set(snapshot.last_received_timestamp)
    LAST_SUCCEEDED.set(snapshot.last_succeeded_timestamp)
    OLDEST_ACTIVE_AGE.set(snapshot.oldest_active_age_seconds)


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
