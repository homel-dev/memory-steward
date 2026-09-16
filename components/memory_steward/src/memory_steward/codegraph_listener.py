from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import unquote_plus

import uvicorn
from fastapi import FastAPI, Header, HTTPException

from memory_steward.codegraph_registry import (
    CodeGraphRegistry,
    DiscoveryRecord,
    postgres_dsn_from_env,
    source_identity,
)

log = logging.getLogger("memory-steward.codegraph-listener")


def _csv_set(name: str) -> set[str]:
    return {value.strip() for value in os.environ.get(name, "").split(",") if value.strip()}


def _metadata_value(metadata: dict[str, Any], key: str) -> str | None:
    wanted = key.lower().replace("-", "_")
    for raw_key, raw_value in metadata.items():
        normalized = str(raw_key).lower()
        if normalized.startswith("x-amz-meta-"):
            normalized = normalized.removeprefix("x-amz-meta-")
        normalized = normalized.replace("-", "_")
        if normalized == wanted and raw_value is not None:
            return str(raw_value)
    return None


def _parse_event_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _discovery_record(record: dict[str, Any]) -> DiscoveryRecord | None:
    event_name = str(record.get("eventName") or "")
    if not event_name.startswith("s3:ObjectCreated:"):
        return None

    s3 = record.get("s3")
    if not isinstance(s3, dict):
        return None
    bucket_data = s3.get("bucket")
    object_data = s3.get("object")
    if not isinstance(bucket_data, dict) or not isinstance(object_data, dict):
        return None

    bucket = bucket_data.get("name")
    raw_key = object_data.get("key")
    if not isinstance(bucket, str) or not bucket or not isinstance(raw_key, str) or not raw_key:
        return None

    object_key = unquote_plus(raw_key)
    version_id = object_data.get("versionId")
    etag = object_data.get("eTag")
    size = object_data.get("size")
    sequencer = object_data.get("sequencer")
    metadata = object_data.get("userMetadata")
    if not isinstance(metadata, dict):
        metadata = {}

    return DiscoveryRecord(
        source_identity=source_identity(
            bucket=bucket,
            object_key=object_key,
            version_id=str(version_id) if version_id is not None else None,
            sequencer=str(sequencer) if sequencer is not None else None,
            etag=str(etag) if etag is not None else None,
        ),
        source_bucket=bucket,
        source_object_key=object_key,
        source_version_id=str(version_id) if version_id is not None else None,
        source_etag=str(etag) if etag is not None else None,
        source_size_bytes=int(size) if isinstance(size, int) else None,
        source_event_name=event_name,
        source_event_time=_parse_event_time(record.get("eventTime")),
        source_sequencer=str(sequencer) if sequencer is not None else None,
        source_metadata=metadata,
        source_event=record,
        project_id=_metadata_value(metadata, "project_id"),
        run_id=_metadata_value(metadata, "run_id"),
        realm=_metadata_value(metadata, "realm"),
        repository=_metadata_value(metadata, "repository"),
    )


def create_app(registry: CodeGraphRegistry | None = None) -> FastAPI:
    app = FastAPI(title="memory-steward-codegraph-listener", version="0.1")
    app.state.registry = registry or CodeGraphRegistry(
        postgres_dsn_from_env("memory-steward-codegraph-listener")
    )
    app.state.allowed_buckets = _csv_set("CODEGRAPH_MINIO_BUCKETS")
    app.state.allowed_prefixes = _csv_set("CODEGRAPH_MINIO_PREFIXES")
    app.state.webhook_token = os.environ.get("CODEGRAPH_MINIO_WEBHOOK_TOKEN", "")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/events/minio")
    def minio_event(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, int]:
        token = app.state.webhook_token
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid webhook token")

        records = payload.get("Records")
        if not isinstance(records, list):
            raise HTTPException(status_code=400, detail="MinIO event must contain Records")

        accepted = 0
        duplicates = 0
        ignored = 0
        for raw_record in records:
            if not isinstance(raw_record, dict):
                ignored += 1
                continue
            record = _discovery_record(raw_record)
            if record is None:
                ignored += 1
                continue
            if app.state.allowed_buckets and record.source_bucket not in app.state.allowed_buckets:
                ignored += 1
                continue
            if app.state.allowed_prefixes and not any(
                record.source_object_key.startswith(prefix) for prefix in app.state.allowed_prefixes
            ):
                ignored += 1
                continue

            result = app.state.registry.discover(record)
            if result.inserted:
                accepted += 1
                log.info(
                    "codegraph object discovered registry_id=%s bucket=%s key=%s",
                    result.registry_id,
                    record.source_bucket,
                    record.source_object_key,
                )
            else:
                duplicates += 1

        return {"accepted": accepted, "duplicates": duplicates, "ignored": ignored}

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("CODEGRAPH_LISTENER_PORT", "8092"))
    uvicorn.run("memory_steward.codegraph_listener:app", host="0.0.0.0", port=port)
