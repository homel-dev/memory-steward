#!/usr/bin/env python3
# scripts/memory_export.py
"""
memory-steward :: offline memory export

Read-only. Produces a single JSON (or JSONL) bundle describing the managed
memory plus health/efficiency metadata, intended to be handed manually to a
stronger model for analysis and tuning recommendations.

NOT part of the memory subsystem. Writes nothing back. No model in the loop.

Designed to run INSIDE a pod that already has DB + Qdrant connectivity
(e.g. memory-router), driven from the Taskfile:

    cat scripts/memory_export.py | kubectl exec -i deploy/memory-router -- \\
        python3 - --level rich > memory-export.json

Detail levels (each includes the previous):
  basic     manifest + memory summary + records (core fields)
  standard  + distributions, cross-project dup check, Qdrant consistency      [default]
  rich      + telemetry efficiency signals, reference stats, payload cardinality

Safety:
  - git_connections token is NEVER exported (row counts only).
  - Secrets/keys/JWTs/emails in content are redacted unless --raw is given.
  - --raw is intended only for runs that never leave the local network.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import psycopg
import requests

GENERATOR_VERSION = "1.0.0"
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LEVELS = ("basic", "standard", "rich")


@dataclass
class Config:
    level: str = "standard"
    project: Optional[str] = None
    since_days: int = 0            # 0 = no time filter
    limit: int = 0                 # 0 = no cap on records
    max_content_chars: int = 0     # 0 = no truncation
    telemetry_window_days: int = 7
    include_qdrant: bool = True
    include_telemetry: bool = True
    include_records: bool = True
    redact: bool = True
    raw: bool = False              # raw => full content, no redaction
    fmt: str = "json"             # json | jsonl

    # connection (cluster-DNS defaults; override via env)
    pg_host: str = field(default_factory=lambda: os.environ.get("EXPORT_PG_HOST")
                         or os.environ.get("POSTGRES_SERVICE_HOST") or "postgres")
    pg_port: str = field(default_factory=lambda: os.environ.get("EXPORT_PG_PORT")
                         or os.environ.get("POSTGRES_SERVICE_PORT") or "5432")
    pg_user: str = field(default_factory=lambda: os.environ.get("POSTGRES_USER", "homel"))
    pg_pass: str = field(default_factory=lambda: os.environ.get("POSTGRES_PASSWORD", "homel"))
    pg_db: str = field(default_factory=lambda: os.environ.get("POSTGRES_DB", "homel"))
    qdrant_url: str = field(default_factory=lambda: os.environ.get("QDRANT_URL", "http://qdrant:6333"))
    qdrant_collection: str = field(default_factory=lambda: os.environ.get("QDRANT_COLLECTION", "homel_memory"))

    def at_least(self, lvl: str) -> bool:
        return LEVELS.index(self.level) >= LEVELS.index(lvl)


def parse_args(argv: List[str]) -> Config:
    p = argparse.ArgumentParser(description="Export memory-steward memory for offline analysis.")
    p.add_argument("--level", choices=LEVELS, default="standard")
    p.add_argument("--project", default=None, help="restrict to a single project_id")
    p.add_argument("--since", type=int, default=0, dest="since_days",
                   help="only records created in the last N days (0 = all)")
    p.add_argument("--limit", type=int, default=0, help="cap exported records (0 = no cap)")
    p.add_argument("--max-content-chars", type=int, default=0,
                   help="truncate each content field to N chars (0 = no truncation)")
    p.add_argument("--telemetry-window-days", type=int, default=7)
    p.add_argument("--no-qdrant", action="store_true")
    p.add_argument("--no-telemetry", action="store_true")
    p.add_argument("--no-records", action="store_true", help="summary only")
    p.add_argument("--raw", action="store_true", help="full content, NO redaction (local-only!)")
    p.add_argument("--format", choices=("json", "jsonl"), default="json", dest="fmt")
    a = p.parse_args(argv)

    cfg = Config(
        level=a.level, project=a.project, since_days=a.since_days, limit=a.limit,
        max_content_chars=a.max_content_chars, telemetry_window_days=a.telemetry_window_days,
        include_qdrant=not a.no_qdrant, include_telemetry=not a.no_telemetry,
        include_records=not a.no_records, raw=a.raw, redact=not a.raw, fmt=a.fmt,
    )
    # Level gating of optional sections
    if not cfg.at_least("standard"):
        cfg.include_qdrant = cfg.include_qdrant and False if cfg.level == "basic" else cfg.include_qdrant
    if not cfg.at_least("rich"):
        cfg.include_telemetry = False
    return cfg


# ---------------------------------------------------------------------------
# Sanitisation
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{16,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{16,}")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("assigned_secret", re.compile(r"(?i)\b(?:token|secret|password|passwd|api[_-]?key)\b\s*[:=]\s*\S+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]


def sanitize(text: Optional[str], cfg: Config) -> (Optional[str], int):
    """Return (text, redaction_count). No-op when --raw."""
    if text is None:
        return None, 0
    if not cfg.redact:
        out = text
    else:
        out = text
        n = 0
        for name, rx in _SECRET_PATTERNS:
            out, k = rx.subn(f"[REDACTED:{name}]", out)
            n += k
    redactions = 0 if not cfg.redact else n
    if cfg.max_content_chars and len(out) > cfg.max_content_chars:
        out = out[: cfg.max_content_chars] + "…[truncated]"
    return out, redactions


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------

def pg_connect(cfg: Config):
    dsn = (f"postgresql://{cfg.pg_user}:{cfg.pg_pass}@{cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db}"
           f"?application_name=memory-export")
    return psycopg.connect(dsn)


def _since_clause(cfg: Config, col: str = "created_at") -> str:
    return f" AND {col} >= now() - interval '{int(cfg.since_days)} days'" if cfg.since_days else ""


def _proj_clause(cfg: Config, col: str = "project_id") -> str:
    return f" AND {col} = %(project)s" if cfg.project else ""


def _params(cfg: Config) -> Dict[str, Any]:
    return {"project": cfg.project} if cfg.project else {}


def fetch_summary(conn, cfg: Config) -> Dict[str, Any]:
    out: Dict[str, Any] = {"static": {}, "dynamic": {}}
    with conn.cursor() as cur:
        # static_memory (no project_id column)
        cur.execute(f"SELECT count(*), count(*) FILTER (WHERE is_active) FROM static_memory "
                    f"WHERE TRUE{_since_clause(cfg)}")
        total, active = cur.fetchone()
        out["static"] = {"total": total, "active": active}

        base = f"FROM dynamic_memory WHERE TRUE{_proj_clause(cfg)}{_since_clause(cfg)}"
        cur.execute(f"SELECT count(*) {base}", _params(cfg))
        out["dynamic"]["total"] = cur.fetchone()[0]

        if cfg.at_least("standard"):
            cur.execute(f"SELECT project_id, count(*) {base} GROUP BY 1 ORDER BY 2 DESC", _params(cfg))
            out["dynamic"]["by_project"] = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute(f"SELECT type, count(*) {base} GROUP BY 1 ORDER BY 2 DESC", _params(cfg))
            out["dynamic"]["by_type"] = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute(f"SELECT COALESCE(scope,'<null>'), count(*) {base} GROUP BY 1 ORDER BY 2 DESC", _params(cfg))
            out["dynamic"]["by_scope"] = {r[0]: r[1] for r in cur.fetchall()}
            cur.execute(f"SELECT count(*) FILTER (WHERE high_confidence), "
                        f"count(*) FILTER (WHERE NOT high_confidence) {base}", _params(cfg))
            hi, lo = cur.fetchone()
            out["dynamic"]["confidence"] = {"high": hi, "low": lo}
            # age buckets
            cur.execute(f"""
                SELECT
                  count(*) FILTER (WHERE created_at >= now()-interval '1 day'),
                  count(*) FILTER (WHERE created_at <  now()-interval '1 day'  AND created_at >= now()-interval '7 days'),
                  count(*) FILTER (WHERE created_at <  now()-interval '7 days' AND created_at >= now()-interval '30 days'),
                  count(*) FILTER (WHERE created_at <  now()-interval '30 days' AND created_at >= now()-interval '90 days'),
                  count(*) FILTER (WHERE created_at <  now()-interval '90 days')
                {base}""", _params(cfg))
            d1, d7, d30, d90, older = cur.fetchone()
            out["dynamic"]["age_buckets"] = {"<=1d": d1, "1-7d": d7, "7-30d": d30, "30-90d": d90, ">90d": older}
            # cross-project exact duplicates (same content_hash across >1 project)
            cur.execute("""
                SELECT count(*) FROM (
                  SELECT content_hash FROM dynamic_memory
                  GROUP BY content_hash HAVING count(DISTINCT project_id) > 1
                ) t""")
            out["dynamic"]["cross_project_hash_collisions"] = cur.fetchone()[0]
    return out


def fetch_records(conn, cfg: Config, qdrant_ids: Optional[Set[str]]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    limit_sql = f" LIMIT {int(cfg.limit)}" if cfg.limit else ""
    with conn.cursor() as cur:
        # dynamic memory
        cur.execute(f"""
            SELECT id, project_id, scope, type, content, content_hash,
                   high_confidence, evidence_type, evidence_ref, qdrant_point_id, created_at
            FROM dynamic_memory
            WHERE TRUE{_proj_clause(cfg)}{_since_clause(cfg)}
            ORDER BY created_at DESC{limit_sql}""", _params(cfg))
        for row in cur.fetchall():
            (rid, pid, scope, typ, content, chash, hi, etype, eref, pointid, created) = row
            sanitized, red = sanitize(content, cfg)
            rec = {
                "source": "dynamic",
                "id": str(rid),
                "project_id": pid,
                "scope": scope,
                "type": typ,
                "high_confidence": hi,
                "evidence_type": etype,
                "content": sanitized,
                "content_hash": chash,
                "created_at": created.isoformat() if created else None,
                "age_days": round((datetime.now(timezone.utc) - created).total_seconds() / 86400, 2) if created else None,
            }
            if cfg.redact:
                rec["redactions"] = red
            if qdrant_ids is not None:
                rec["vector_exists"] = pointid in qdrant_ids
            records.append(rec)

        # static memory (no project filter; respect since + limit budget)
        if not cfg.project:  # static is global; skip when scoping to a project
            cur.execute(f"""
                SELECT id, content, mode, is_active, created_at
                FROM static_memory
                WHERE TRUE{_since_clause(cfg)}
                ORDER BY created_at DESC{limit_sql}""")
            for row in cur.fetchall():
                (rid, content, mode, active, created) = row
                sanitized, red = sanitize(content, cfg)
                rec = {
                    "source": "static",
                    "id": str(rid),
                    "mode": mode,
                    "is_active": active,
                    "content": sanitized,
                    "created_at": created.isoformat() if created else None,
                }
                if cfg.redact:
                    rec["redactions"] = red
                records.append(rec)
    return records


def fetch_runtime_config(conn, cfg: Config) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM runtime_config")
            for k, v in cur.fetchall():
                if re.search(r"(?i)token|secret|password|key", k):
                    out[k] = "[REDACTED]"
                else:
                    out[k] = v
    except Exception as e:
        out["_error"] = f"runtime_config unavailable: {e}"
    return out


def fetch_reference_stats(conn) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), COALESCE(sum(chunk_count),0), COALESCE(sum(upserted_count),0) "
                        "FROM reference_ingestion")
            n, chunks, upserts = cur.fetchone()
            out = {"ingestion_events": n, "total_chunks": chunks, "total_upserts": upserts}
            cur.execute("SELECT product, version, count(*) FROM reference_ingestion "
                        "GROUP BY 1,2 ORDER BY 3 DESC LIMIT 25")
            out["by_product_version"] = [{"product": p, "version": v, "events": c} for p, v, c in cur.fetchall()]
    except Exception as e:
        out["_error"] = f"reference_ingestion unavailable: {e}"
    return out


def fetch_telemetry(conn, cfg: Config) -> Dict[str, Any]:
    """System efficiency signals. Best-effort; guarded so a partial/empty
    telemetry schema never breaks the export."""
    win = int(cfg.telemetry_window_days)
    out: Dict[str, Any] = {"window_days": win}
    pj = " AND project_id = %(project)s" if cfg.project else ""
    prm = _params(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT count(*),
                       count(*) FILTER (WHERE http_status >= 400 OR error_kind IS NOT NULL),
                       avg(total_tokens)::int, avg(prompt_tokens)::int, avg(completion_tokens)::int,
                       avg(static_tokens_est)::int, avg(dynamic_tokens_est)::int, avg(context_budget_max)::int
                FROM telemetry.request
                WHERE t_begin >= now() - interval '{win} days'{pj}""", prm)
            (n, errs, tot, pr, comp, stat, dyn, budg) = cur.fetchone()
            out["requests"] = n
            out["error_rate"] = round(errs / n, 4) if n else None
            denom = (stat or 0) + (dyn or 0)
            out["tokens"] = {
                "avg_total": tot, "avg_prompt": pr, "avg_completion": comp,
                "avg_static_est": stat, "avg_dynamic_est": dyn, "avg_budget_max": budg,
                "dynamic_share_of_memory": round((dyn or 0) / denom, 4) if denom else None,
            }
    except Exception as e:
        out["request"] = {"_error": str(e)}

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT avg(dense_candidates)::numeric(10,2), avg(selected_topk)::numeric(10,2),
                       avg(context_tokens_est)::int,
                       sum(dropped_budget), sum(dropped_no_content), sum(dropped_other),
                       sum(dense_candidates)
                FROM telemetry.retrieval
                WHERE project_id IS NOT NULL{pj}""", prm)
            (avg_dense, avg_sel, avg_ctx, db, dnc, do, total_cand) = cur.fetchone()
            sel_ratio = float(avg_sel) / float(avg_dense) if avg_dense and float(avg_dense) > 0 else None
            tc = total_cand or 0
            out["retrieval"] = {
                "avg_dense_candidates": float(avg_dense) if avg_dense is not None else None,
                "avg_selected_topk": float(avg_sel) if avg_sel is not None else None,
                "select_ratio": round(sel_ratio, 4) if sel_ratio is not None else None,
                "avg_context_tokens_est": avg_ctx,
                "drop_rate_budget": round((db or 0) / tc, 4) if tc else None,
                "drop_rate_no_content": round((dnc or 0) / tc, 4) if tc else None,
                "drop_rate_other": round((do or 0) / tc, 4) if tc else None,
            }
    except Exception as e:
        out["retrieval"] = {"_error": str(e)}

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT avg(fragments_extracted)::numeric(10,2), avg(fragments_inserted)::numeric(10,2),
                       avg(qdrant_upserts)::numeric(10,2), avg(admission_lag_ms)::int,
                       avg(CASE WHEN ok THEN 1 ELSE 0 END)::numeric(5,4)
                FROM telemetry.admission
                WHERE t_begin >= now() - interval '{win} days'{pj}""", prm)
            (fe, fi, up, lag, okr) = cur.fetchone()
            out["admission"] = {
                "avg_fragments_extracted": float(fe) if fe is not None else None,
                "avg_fragments_inserted": float(fi) if fi is not None else None,
                "insertion_ratio": round(float(fi) / float(fe), 4) if fe and float(fe) > 0 else None,
                "avg_qdrant_upserts": float(up) if up is not None else None,
                "avg_admission_lag_ms": lag,
                "ok_rate": float(okr) if okr is not None else None,
            }
    except Exception as e:
        out["admission"] = {"_error": str(e)}

    try:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT name, percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::int, count(*)
                FROM telemetry.step
                WHERE duration_ms IS NOT NULL AND t_begin >= now() - interval '{win} days'{pj}
                GROUP BY name ORDER BY 2 DESC NULLS LAST""", prm)
            out["step_latency_p95_ms"] = {r[0]: {"p95_ms": r[1], "n": r[2]} for r in cur.fetchall()}
    except Exception as e:
        out["step_latency_p95_ms"] = {"_error": str(e)}

    return out


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

QDRANT_SCROLL_CAP = 50000  # safety cap for the consistency / cardinality scan


def fetch_qdrant(conn, cfg: Config) -> (Dict[str, Any], Optional[Set[str]]):
    info: Dict[str, Any] = {"collection": cfg.qdrant_collection}
    point_ids: Optional[Set[str]] = None
    base = f"{cfg.qdrant_url.rstrip('/')}/collections/{cfg.qdrant_collection}"
    try:
        r = requests.get(base, timeout=15)
        r.raise_for_status()
        res = r.json().get("result", {})
        info["points_count"] = res.get("points_count")
        info["status"] = res.get("status")
    except Exception as e:
        info["_error"] = f"collection info unavailable: {e}"
        return info, None

    # Scroll point ids (and payloads at rich level) for consistency + cardinality.
    want_payload = cfg.at_least("rich")
    ids: Set[str] = set()
    payload_vals: Dict[str, Set[str]] = {}
    next_page = None
    capped = False
    try:
        while True:
            body: Dict[str, Any] = {"limit": 1000, "with_payload": want_payload, "with_vector": False}
            if next_page is not None:
                body["offset"] = next_page
            r = requests.post(f"{base}/points/scroll", json=body, timeout=30)
            r.raise_for_status()
            result = r.json().get("result", {})
            pts = result.get("points", [])
            for p in pts:
                ids.add(str(p.get("id")))
                if want_payload:
                    pl = p.get("payload") or {}
                    for k in ("project_id", "memory_type", "scope", "source", "product", "version"):
                        if k in pl and pl[k] is not None:
                            payload_vals.setdefault(k, set()).add(str(pl[k]))
            next_page = result.get("next_page_offset")
            if next_page is None:
                break
            if len(ids) >= QDRANT_SCROLL_CAP:
                capped = True
                break
        point_ids = ids
        info["scanned_points"] = len(ids)
        if capped:
            info["scan_capped_at"] = QDRANT_SCROLL_CAP
        if want_payload:
            info["payload_cardinality"] = {k: len(v) for k, v in payload_vals.items()}
    except Exception as e:
        info["scroll_error"] = str(e)
        return info, None

    # Consistency: PG point ids vs Qdrant ids (best-effort, only if not capped)
    if not capped:
        try:
            with conn.cursor() as cur:
                q = "SELECT qdrant_point_id FROM dynamic_memory WHERE TRUE"
                if cfg.project:
                    q += " AND project_id = %(project)s"
                cur.execute(q, _params(cfg))
                pg_ids = {str(r[0]) for r in cur.fetchall()}
            info["consistency"] = {
                "pg_pointers": len(pg_ids),
                "qdrant_points": len(ids),
                "pg_pointers_missing_in_qdrant": len(pg_ids - ids),
                "qdrant_points_missing_in_pg": len(ids - pg_ids),
            }
        except Exception as e:
            info["consistency"] = {"_error": str(e)}
    else:
        info["consistency"] = {"_skipped": "scroll capped; consistency check unreliable"}

    return info, point_ids


# ---------------------------------------------------------------------------
# Bundle assembly
# ---------------------------------------------------------------------------

def build_bundle(cfg: Config) -> Dict[str, Any]:
    conn = pg_connect(cfg)
    try:
        qdrant_info: Optional[Dict[str, Any]] = None
        qdrant_ids: Optional[Set[str]] = None
        if cfg.include_qdrant and cfg.at_least("standard"):
            qdrant_info, qdrant_ids = fetch_qdrant(conn, cfg)

        summary = fetch_summary(conn, cfg)
        bundle: Dict[str, Any] = {
            "manifest": {
                "generator": "memory_export",
                "generator_version": GENERATOR_VERSION,
                "schema_version": SCHEMA_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "level": cfg.level,
                "redacted": cfg.redact,
                "filters": {
                    "project": cfg.project,
                    "since_days": cfg.since_days or None,
                    "limit": cfg.limit or None,
                },
            },
            "config": fetch_runtime_config(conn, cfg),
            "summary": {"memory": summary},
        }
        if qdrant_info is not None:
            bundle["summary"]["qdrant"] = qdrant_info
        if cfg.include_telemetry and cfg.at_least("rich"):
            bundle["summary"]["telemetry"] = fetch_telemetry(conn, cfg)
        if cfg.at_least("rich"):
            bundle["summary"]["reference"] = fetch_reference_stats(conn)
        if cfg.include_records:
            recs = fetch_records(conn, cfg, qdrant_ids)
            bundle["manifest"]["record_count"] = len(recs)
            bundle["records"] = recs
        return bundle
    finally:
        conn.close()


def main(argv: List[str]) -> int:
    cfg = parse_args(argv)
    bundle = build_bundle(cfg)
    if cfg.fmt == "jsonl":
        # manifest + summary as first line, then one line per record
        head = {k: v for k, v in bundle.items() if k != "records"}
        sys.stdout.write(json.dumps(head, default=str) + "\n")
        for rec in bundle.get("records", []):
            sys.stdout.write(json.dumps(rec, default=str) + "\n")
    else:
        sys.stdout.write(json.dumps(bundle, indent=2, default=str) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
