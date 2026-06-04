# diagnostics_plane.py
"""
Diagnostics Plane: health, explain, metrics, Qdrant visibility, memory audit.
Implements the full Doc 06 Section 5.3 blame trace and adds genuine observability.
"""

import os
import json
import logging
import psycopg
import requests
from fastmcp import FastMCP
from memory_steward_mcp.config import (
    POSTGRES_DSN, LOG_DIR, QDRANT_URL, MAX_CONTEXT_TOKENS,
    HYSTERESIS_WINDOW, APP_VERSION, QDRANT_COLLECTION, EMBEDDINGS_URL
)

log = logging.getLogger("memory-steward-mcp.diagnostics")


def register_diagnostics_tools(mcp: FastMCP, qdrant):

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_system_health() -> str:
        """[Diagnostics] Connectivity and liveness check for all services."""
        health = {}

        # Qdrant
        try:
            info = qdrant.get_collection(QDRANT_COLLECTION)
            count = info.points_count if hasattr(info, "points_count") else "?"
            health["qdrant"] = f"ok (points={count})"
        except Exception as e:
            health["qdrant"] = f"error: {e}"

        # Postgres
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM dynamic_memory")
                dm_count = cur.fetchone()[0]
                cur.execute("SELECT count(*) FROM static_memory WHERE is_active = true")
                sm_count = cur.fetchone()[0]
            health["postgres"] = f"ok (dynamic_memory={dm_count}, active_static={sm_count})"
        except Exception as e:
            health["postgres"] = f"error: {e}"

        # Embeddings
        try:
            r = requests.get(f"{EMBEDDINGS_URL}/healthz", timeout=2)
            health["embeddings"] = "ok" if r.ok else f"degraded: {r.status_code}"
        except Exception as e:
            health["embeddings"] = f"error: {e}"

        # LIST (STT)
        list_base = os.environ.get("LIST_URL", "http://memory-steward-list:8001")
        try:
            r = requests.get(f"{list_base.rstrip('/')}/healthz", timeout=2)
            health["list_stt"] = "ok" if r.ok else f"degraded: {r.status_code}"
        except Exception as e:
            health["list_stt"] = f"error: {e}"

        # Memory Router
        router_base = os.environ.get("ROUTER_URL", "http://memory-router:8080")
        try:
            r = requests.get(f"{router_base.rstrip('/')}/healthz", timeout=2)
            health["memory_router"] = "ok" if r.ok else f"degraded: {r.status_code}"
        except Exception as e:
            health["memory_router"] = f"error: {e}"

        lines = ["### System Health"]
        for svc, status in health.items():
            icon = "✅" if status.startswith("ok") else "❌"
            lines.append(f"{icon} **{svc}**: {status}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # FULL BLAME TRACE (Doc 06 Section 5.3)
    # ------------------------------------------------------------------

    @mcp.tool()
    def explain_decision(request_id: str) -> str:
        """[Diagnostics] Full Doc 06 blame trace for a specific request_id.
        Shows token accounting, retrieval drops, step latencies, and admission outcome."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:

                # Request row
                cur.execute("""
                    SELECT project_id, t_begin, t_end, decided_mode,
                           model_requested, model_sent_to_builder,
                           http_status, error_kind, error_detail,
                           prompt_tokens, completion_tokens, total_tokens,
                           context_budget_max, static_tokens_est, dynamic_tokens_est
                    FROM telemetry.request WHERE request_id = %s
                """, (request_id,))
                req = cur.fetchone()
                if not req:
                    return f"No telemetry found for request_id={request_id}"

                (project_id, t_begin, t_end, mode,
                 model_req, model_sent, http_status, err_kind, err_detail,
                 prompt_tok, comp_tok, total_tok,
                 budget_max, static_est, dynamic_est) = req

                latency_ms = int((t_end - t_begin).total_seconds() * 1000) if t_end else "in-flight"

                # Retrieval row
                cur.execute("""
                    SELECT dense_candidates, selected_topk, context_tokens_est,
                           dropped_budget, dropped_no_content, dropped_other
                    FROM telemetry.retrieval WHERE request_id = %s
                """, (request_id,))
                ret = cur.fetchone()

                # Steps
                cur.execute("""
                    SELECT name, duration_ms, ok, http_status, error_detail
                    FROM telemetry.step
                    WHERE request_id = %s ORDER BY t_begin ASC
                """, (request_id,))
                steps = cur.fetchall()

                # Admission
                cur.execute("""
                    SELECT fragments_extracted, fragments_inserted, qdrant_upserts,
                           admission_lag_ms, ok, error_detail
                    FROM telemetry.admission WHERE request_id = %s
                """, (request_id,))
                adm = cur.fetchone()

        except Exception as e:
            return f"DB error: {e}"

        lines = [
            f"## Blame Trace: `{request_id}`",
            f"- **Project:** {project_id}",
            f"- **Mode:** {mode or 'unset'}",
            f"- **Latency:** {latency_ms}ms",
            f"- **HTTP:** {http_status}  error_kind={err_kind or 'none'}",
            err_detail and f"- **Error detail:** {err_detail}" or "",
            "",
            "### Token Accounting",
            f"- prompt={prompt_tok}  completion={comp_tok}  total={total_tok}",
            f"- budget_max={budget_max}  static_est={static_est}  dynamic_est={dynamic_est}",
            f"- model_requested={model_req}  model_sent={model_sent}",
        ]

        lines += ["", "### Retrieval"]
        if ret:
            dense, topk, ctx_tok, d_budget, d_no_content, d_other = ret
            budget_pct = round(d_budget / dense * 100) if dense else 0
            lines += [
                f"- dense_candidates={dense}  selected_topk={topk}  ctx_tokens={ctx_tok}",
                f"- dropped_budget={d_budget} ({budget_pct}%)  dropped_no_content={d_no_content}  dropped_other={d_other}",
            ]
        else:
            lines.append("- Retrieval telemetry missing (not executed or not recorded).")

        lines += ["", "### Step Latencies"]
        for name, dur, ok, hstatus, edetail in steps:
            status_icon = "✅" if ok else "❌"
            lines.append(f"- {status_icon} `{name}`: {dur}ms  http={hstatus or '-'}  {edetail or ''}")

        lines += ["", "### Admission"]
        if adm:
            ext, ins, upserts, lag, adm_ok, adm_err = adm
            lines += [
                f"- ok={adm_ok}  extracted={ext}  inserted={ins}  qdrant_upserts={upserts}",
                f"- admission_lag_ms={lag}",
                adm_err and f"- error: {adm_err}" or "",
            ]
        else:
            lines.append("- Admission telemetry missing (not executed or not recorded).")

        return "\n".join(l for l in lines if l is not None)

    @mcp.tool()
    def explain_last_decision() -> str:
        """[Diagnostics] Full blame trace for the most recent request."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("SELECT request_id FROM telemetry.request ORDER BY t_begin DESC LIMIT 1")
                row = cur.fetchone()
                if not row:
                    return "No telemetry recorded yet."
                return explain_decision(row[0])
        except Exception as e:
            return f"DB error: {e}"

    # ------------------------------------------------------------------
    # PERFORMANCE METRICS SUMMARY
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_metrics(window_minutes: int = 60, project_id: str = None) -> str:
        """[Diagnostics] Request throughput, latency p95, error rate, token economy,
        retrieval blind-spot rate, and admission health over a time window."""
        pid_filter = "AND project_id = %(pid)s" if project_id else ""
        params = {"window": f"{window_minutes} minutes", "pid": project_id}

        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:

                # Request summary
                cur.execute(f"""
                    SELECT
                        count(*) AS total,
                        count(*) FILTER (WHERE http_status >= 500 OR error_kind IS NOT NULL) AS errors,
                        round(percentile_cont(0.5) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (t_end - t_begin)) * 1000
                        )::numeric, 0) AS p50_ms,
                        round(percentile_cont(0.95) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (t_end - t_begin)) * 1000
                        )::numeric, 0) AS p95_ms,
                        round(avg(total_tokens)::numeric, 0) AS avg_tokens,
                        round(avg(static_tokens_est)::numeric, 0) AS avg_static,
                        round(avg(dynamic_tokens_est)::numeric, 0) AS avg_dynamic,
                        round(avg(context_budget_max)::numeric, 0) AS avg_budget
                    FROM telemetry.request
                    WHERE t_begin >= now() - %(window)s::interval
                      AND t_end IS NOT NULL
                      {pid_filter}
                """, params)
                req = cur.fetchone()

                # Retrieval blind spots (zero candidates)
                cur.execute(f"""
                    SELECT
                        count(*) AS total_retrievals,
                        count(*) FILTER (WHERE dense_candidates = 0) AS blind_spots,
                        round(avg(dropped_budget)::numeric, 1) AS avg_dropped_budget,
                        round(avg(selected_topk)::numeric, 1) AS avg_selected
                    FROM telemetry.retrieval r
                    JOIN telemetry.request rq USING (request_id)
                    WHERE rq.t_begin >= now() - %(window)s::interval
                      {pid_filter.replace('project_id', 'rq.project_id')}
                """, params)
                ret = cur.fetchone()

                # Admission health
                cur.execute(f"""
                    SELECT
                        count(*) AS total,
                        count(*) FILTER (WHERE ok = false) AS failures,
                        round(avg(fragments_extracted)::numeric, 2) AS avg_extracted,
                        round(avg(fragments_inserted)::numeric, 2) AS avg_inserted,
                        round(avg(admission_lag_ms)::numeric, 0) AS avg_lag_ms
                    FROM telemetry.admission a
                    JOIN telemetry.request rq USING (request_id)
                    WHERE rq.t_begin >= now() - %(window)s::interval
                      {pid_filter.replace('project_id', 'rq.project_id')}
                """, params)
                adm = cur.fetchone()

                # Step p95 hotspots
                cur.execute(f"""
                    SELECT name,
                        round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 0) AS p95_ms,
                        count(*) AS n
                    FROM telemetry.step s
                    JOIN telemetry.request rq USING (request_id)
                    WHERE rq.t_begin >= now() - %(window)s::interval
                      AND s.duration_ms IS NOT NULL
                      {pid_filter.replace('project_id', 'rq.project_id')}
                    GROUP BY name ORDER BY p95_ms DESC
                """, params)
                steps = cur.fetchall()

        except Exception as e:
            return f"DB error: {e}"

        total, errors, p50, p95, avg_tok, avg_static, avg_dynamic, avg_budget = req
        error_rate = round(errors / total * 100, 1) if total else 0
        static_pct = round(avg_static / avg_budget * 100) if avg_budget else "?"
        dynamic_pct = round(avg_dynamic / avg_budget * 100) if avg_budget else "?"

        ret_total, blind_spots, avg_dropped_budget, avg_selected = ret
        blind_pct = round(blind_spots / ret_total * 100, 1) if ret_total else 0

        adm_total, adm_failures, avg_ext, avg_ins, avg_lag = adm
        adm_fail_pct = round(adm_failures / adm_total * 100, 1) if adm_total else 0

        lines = [
            f"## Metrics (last {window_minutes}m{' · ' + project_id if project_id else ''})",
            "",
            "### Requests",
            f"- total={total}  errors={errors} ({error_rate}%)",
            f"- latency p50={p50}ms  p95={p95}ms",
            f"- avg_tokens={avg_tok}  budget={avg_budget}  static={avg_static} ({static_pct}%)  dynamic={avg_dynamic} ({dynamic_pct}%)",
            "",
            "### Retrieval",
            f"- total={ret_total}  blind_spots={blind_spots} ({blind_pct}%)",
            f"- avg_selected={avg_selected}  avg_dropped_budget={avg_dropped_budget}",
            "",
            "### Admission",
            f"- total={adm_total}  failures={adm_failures} ({adm_fail_pct}%)",
            f"- avg_extracted={avg_ext}  avg_inserted={avg_ins}  avg_lag={avg_lag}ms",
            "",
            "### Step p95 Latencies",
        ]
        for name, p95_ms, n in steps:
            lines.append(f"- `{name}`: p95={p95_ms}ms  n={n}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # QDRANT COLLECTION VISIBILITY
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_qdrant_stats() -> str:
        """[Diagnostics] Qdrant collection health: point counts by memory type,
        index status, and collection config."""
        try:
            info = qdrant.get_collection(QDRANT_COLLECTION)
        except Exception as e:
            return f"Qdrant error: {e}"

        try:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue

            def count_by_type(memory_type: str) -> int:
                res = qdrant.count(
                    collection_name=QDRANT_COLLECTION,
                    count_filter=Filter(must=[
                        FieldCondition(key="memory_type", match=MatchValue(value=memory_type))
                    ]),
                    exact=True,
                )
                return res.count

            dynamic_count = count_by_type("dynamic_memory")
            reference_count = count_by_type("reference_memory")
            static_count = count_by_type("static_global") + count_by_type("static_mode_conditioned")

        except Exception as e:
            dynamic_count = reference_count = static_count = f"err({e})"

        cfg = info.config.params if hasattr(info, "config") else {}
        status = info.status if hasattr(info, "status") else "unknown"

        lines = [
            "## Qdrant Collection Stats",
            f"- **collection:** {QDRANT_COLLECTION}",
            f"- **status:** {status}",
            f"- **total_points:** {info.points_count}",
            f"- **indexed_vectors:** {info.indexed_vectors_count if hasattr(info, 'indexed_vectors_count') else '?'}",
            "",
            "### Points by Memory Type",
            f"- dynamic_memory: {dynamic_count}",
            f"- reference_memory: {reference_count}",
            f"- static: {static_count}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # DYNAMIC MEMORY AUDIT (per project)
    # ------------------------------------------------------------------

    @mcp.tool()
    def get_project_memory(project_id: str, limit: int = 50, high_confidence_only: bool = False) -> str:
        """[Diagnostics] Show everything remembered about a project from Postgres.
        Ordered by recency. Use high_confidence_only=true to filter noise."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT content, high_confidence, scope, created_at
                    FROM dynamic_memory
                    WHERE project_id = %s
                      AND (%s = false OR high_confidence = true)
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (project_id, high_confidence_only, limit))
                rows = cur.fetchall()

                cur.execute("""
                    SELECT count(*), count(*) FILTER (WHERE high_confidence)
                    FROM dynamic_memory WHERE project_id = %s
                """, (project_id,))
                total, high_conf = cur.fetchone()

        except Exception as e:
            return f"DB error: {e}"

        if not rows:
            return f"No dynamic memory found for project_id={project_id}"

        lines = [
            f"## Memory Audit: `{project_id}`",
            f"- total={total}  high_confidence={high_conf}  showing={len(rows)}",
            "",
        ]
        for content, hc, scope, created_at in rows:
            icon = "🔒" if hc else "〰️"
            lines.append(f"{icon} [{created_at.strftime('%m-%d %H:%M')}] ({scope or 'general'}) {content}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # RETRIEVAL SIMULATION
    # ------------------------------------------------------------------

    @mcp.tool()
    def simulate_retrieval(project_id: str, query: str, top_k: int = 8) -> str:
        """[Diagnostics] Simulate what the router would retrieve for a given query
        and project. Shows ranked candidates without touching memory or telemetry."""
        try:
            r = requests.post(
                f"{EMBEDDINGS_URL}/embed",
                json={"texts": [query], "normalize": True},
                timeout=10,
            )
            r.raise_for_status()
            vec = r.json()["vectors"][0]
        except Exception as e:
            return f"Embedding failed: {e}"

        try:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            results = qdrant.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=("dense", vec),
                query_filter=Filter(must=[
                    FieldCondition(key="project_id", match=MatchValue(value=project_id))
                ]),
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            return f"Qdrant search failed: {e}"

        if not results:
            return f"No candidates found for project_id={project_id} — retrieval blind spot."

        lines = [
            f"## Simulated Retrieval",
            f"- project={project_id}  query=`{query}`  top_k={top_k}",
            "",
        ]
        for i, hit in enumerate(results, 1):
            content = (hit.payload or {}).get("content", "?")
            mem_type = (hit.payload or {}).get("memory_type", "?")
            score = round(hit.score, 4)
            lines.append(f"{i}. [{mem_type}] score={score}  `{content[:120]}`")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LOGS
    # ------------------------------------------------------------------

    @mcp.tool(name="diagnostics.logs.read")
    def logs_read(service: str, lines: int = 200) -> str:
        """[Diagnostics] Read bounded tail of container logs for a service.
        Valid services: memory-router, memory-steward, memory-steward-mcp,
        memory-steward-list, embeddings, qdrant, postgres, vllm-steward."""
        max_lines = min(lines, 1000)
        log_path = os.path.join(LOG_DIR, f"{service}.log")
        try:
            with open(log_path, "r") as f:
                tail = f.readlines()[-max_lines:]
                return "".join(tail)
        except FileNotFoundError:
            return f"Log file not found: {log_path}"
        except Exception as e:
            return f"Log read failed: {e}"

    # ------------------------------------------------------------------
    # RUNTIME CONTRACT
    # ------------------------------------------------------------------

    @mcp.resource("diagnostics://contract")
    def get_runtime_contract() -> str:
        """[Diagnostics] Read-only view of current runtime configuration."""
        return json.dumps({
            "QDRANT_URL": QDRANT_URL,
            "QDRANT_COLLECTION": QDRANT_COLLECTION,
            "MAX_CONTEXT_TOKENS": MAX_CONTEXT_TOKENS,
            "HYSTERESIS_WINDOW": HYSTERESIS_WINDOW,
            "VERSION": APP_VERSION,
        }, indent=2)
