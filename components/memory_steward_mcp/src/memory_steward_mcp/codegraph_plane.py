"""Session-bound CodeGraph MCP routing for Memory Steward.

CodeGraph workers are ephemeral implementation details.  Agent clients receive
an opaque capability credential and keep talking to the stable Memory Steward
MCP endpoint.  Every CodeGraph list/call re-resolves the exact READY registry
binding for the capability session's project/run/realm/revision identity.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

import anyio
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.providers import Provider
from fastmcp.tools.base import Tool, ToolResult
import httpx
import mcp.types as mt
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger("steward-mcp.codegraph")

CAPABILITY_HEADER = "x-memory-capability"
TOKEN_PREFIX = "mscs_"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
REALMS = frozenset({"workspace", "oracle", "candidate"})

# Read-only Memory Steward tools that are safe to expose to ordinary agent
# capability sessions. Project identity is checked against the session on call.
BASE_AGENT_READ_TOOLS = frozenset(
    {
        "memory.retrieve_context",
        "memory.reference.search",
        "memory.reference.get",
    }
)

# Pinned to the read/query surface available in CodeGraph v0.20.1.  Admin,
# indexing, memory-write, and document-mutation tools are intentionally absent.
AGENT_CODEGRAPH_TOOLS = frozenset(
    {
        "codegraph_symbol_search",
        "codegraph_get_symbol_info",
        "codegraph_get_detailed_symbol",
        "codegraph_get_ai_context",
        "codegraph_get_edit_context",
        "codegraph_get_curated_context",
        "codegraph_search_by_pattern",
        "codegraph_search_by_error",
        "codegraph_get_callers",
        "codegraph_get_callees",
        "codegraph_get_call_graph",
        "codegraph_get_dependency_graph",
        "codegraph_analyze_impact",
        "codegraph_analyze_complexity",
        "codegraph_traverse_graph",
        "codegraph_find_circular_deps",
        "codegraph_find_entry_points",
        "codegraph_find_hot_paths",
        "codegraph_find_by_imports",
        "codegraph_find_by_signature",
        "codegraph_find_implementors",
        "codegraph_find_dead_imports",
        "codegraph_get_module_summary",
        "codegraph_find_related_tests",
        "codegraph_pr_context",
    }
)

PROJECT_SCOPED_NATIVE_TOOLS = BASE_AGENT_READ_TOOLS


class CapabilitySessionError(RuntimeError):
    """Base error for capability-session resolution."""


class CapabilityUnauthorized(CapabilitySessionError):
    """The supplied capability credential does not authorize the request."""


class CodeGraphUnavailable(CapabilitySessionError):
    """No exact READY CodeGraph binding is currently available."""


class CodeGraphAmbiguous(CapabilitySessionError):
    """More than one READY graph matches an identity that must be unique."""


@dataclass(frozen=True)
class CodeGraphBinding:
    registry_id: str
    worker_generation: int
    worker_endpoint: str
    project_id: str
    run_id: str
    realm: str
    repository: str | None
    revision: str
    codegraph_version: str
    index_profile: str


@dataclass(frozen=True)
class CapabilitySession:
    capability_session_id: str
    project_id: str
    run_id: str
    realm: str
    repository: str | None
    revision: str
    role: str
    stage: str | None
    status: str
    authorized_tools: tuple[str, ...]
    codegraph_registry_id: str
    created_at: datetime
    expires_at: datetime


class CapabilityIssueRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=256)
    run_id: str = Field(min_length=1, max_length=256)
    realm: str = Field(min_length=1, max_length=64)
    repository: str | None = Field(default=None, max_length=512)
    revision: str = Field(min_length=40, max_length=40)
    role: str = Field(min_length=1, max_length=128)
    stage: str | None = Field(default=None, max_length=128)
    ttl_seconds: int = Field(default=3600, ge=60, le=86400)


class CapabilitySessionStore:
    def __init__(self, postgres_dsn: str):
        self.postgres_dsn = postgres_dsn

    def _connect(self) -> Any:
        return psycopg.connect(self.postgres_dsn, row_factory=dict_row)

    @staticmethod
    def token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def validate_identity(*, realm: str, revision: str) -> tuple[str, str]:
        normalized_realm = realm.strip().lower()
        normalized_revision = revision.strip().lower()
        if normalized_realm not in REALMS:
            raise ValueError(f"unsupported CodeGraph realm: {realm}")
        if not REVISION_RE.fullmatch(normalized_revision):
            raise ValueError("CodeGraph revision must be a full 40-character Git SHA")
        return normalized_realm, normalized_revision

    def find_ready_backend(
        self,
        *,
        project_id: str,
        run_id: str,
        realm: str,
        repository: str | None,
        revision: str,
    ) -> CodeGraphBinding:
        realm, revision = self.validate_identity(realm=realm, revision=revision)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text AS registry_id,
                  worker_generation,
                  worker_endpoint,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  indexed_revision,
                  codegraph_version,
                  index_profile
                FROM codegraph_registry
                WHERE ready = TRUE
                  AND state = 'ready'
                  AND project_id = %s
                  AND run_id = %s
                  AND realm = %s
                  AND indexed_revision = %s
                  AND worker_endpoint IS NOT NULL
                  AND (%s IS NULL OR repository = %s)
                ORDER BY ready_at DESC NULLS LAST, updated_at DESC
                LIMIT 2
                """,
                (project_id, run_id, realm, revision, repository, repository),
            )
            rows = cur.fetchall()
        if not rows:
            raise CodeGraphUnavailable(
                "no READY CodeGraph worker for the exact project/run/realm/revision"
            )
        if len(rows) != 1:
            raise CodeGraphAmbiguous(
                "multiple READY CodeGraph workers match the exact capability identity"
            )
        return self._binding_from_row(rows[0])

    def create_session(
        self,
        *,
        binding: CodeGraphBinding,
        role: str,
        stage: str | None,
        ttl_seconds: int,
        authorized_tools: Sequence[str],
    ) -> tuple[CapabilitySession, str]:
        tools = tuple(sorted(set(authorized_tools)))
        if not tools:
            raise ValueError("capability session must authorize at least one tool")
        raw_token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        digest = self.token_digest(raw_token)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO capability_sessions (
                  token_digest,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  revision,
                  role,
                  stage,
                  status,
                  authorized_tools,
                  codegraph_registry_id,
                  expires_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s,
                  'active', %s, %s::uuid, now() + (%s * interval '1 second')
                )
                RETURNING
                  id::text AS capability_session_id,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  revision,
                  role,
                  stage,
                  status,
                  authorized_tools,
                  codegraph_registry_id::text,
                  created_at,
                  expires_at
                """,
                (
                    digest,
                    binding.project_id,
                    binding.run_id,
                    binding.realm,
                    binding.repository,
                    binding.revision,
                    role,
                    stage,
                    list(tools),
                    binding.registry_id,
                    ttl_seconds,
                ),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:  # pragma: no cover - INSERT ... RETURNING invariant
            raise RuntimeError("capability session insert returned no row")
        return self._session_from_row(row), raw_token

    def resolve_session(self, token: str) -> CapabilitySession:
        if not token.startswith(TOKEN_PREFIX):
            raise CapabilityUnauthorized("invalid capability credential")
        digest = self.token_digest(token)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE capability_sessions
                SET status = 'expired', updated_at = now()
                WHERE token_digest = %s
                  AND status = 'active'
                  AND expires_at <= now()
                """,
                (digest,),
            )
            cur.execute(
                """
                SELECT
                  id::text AS capability_session_id,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  revision,
                  role,
                  stage,
                  status,
                  authorized_tools,
                  codegraph_registry_id::text,
                  created_at,
                  expires_at
                FROM capability_sessions
                WHERE token_digest = %s
                  AND status = 'active'
                  AND expires_at > now()
                """,
                (digest,),
            )
            row = cur.fetchone()
            conn.commit()
        if row is None:
            raise CapabilityUnauthorized("unknown, expired, released, or revoked capability session")
        return self._session_from_row(row)

    def resolve_backend(self, session: CapabilitySession) -> CodeGraphBinding:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text AS registry_id,
                  worker_generation,
                  worker_endpoint,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  indexed_revision,
                  codegraph_version,
                  index_profile
                FROM codegraph_registry
                WHERE id = %s::uuid
                  AND ready = TRUE
                  AND state = 'ready'
                  AND project_id = %s
                  AND run_id = %s
                  AND realm = %s
                  AND indexed_revision = %s
                  AND worker_endpoint IS NOT NULL
                """,
                (
                    session.codegraph_registry_id,
                    session.project_id,
                    session.run_id,
                    session.realm,
                    session.revision,
                ),
            )
            row = cur.fetchone()
        if row is None:
            raise CodeGraphUnavailable(
                "CodeGraph is temporarily unavailable for this capability session revision"
            )
        binding = self._binding_from_row(row)
        if session.repository is not None and binding.repository != session.repository:
            raise CodeGraphUnavailable("CodeGraph repository binding changed")
        return binding

    def release_session(self, session_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE capability_sessions
                SET status = 'released', released_at = now(), updated_at = now()
                WHERE id = %s::uuid
                  AND status = 'active'
                """,
                (session_id,),
            )
            updated = cur.rowcount == 1
            conn.commit()
        return updated

    def record_query(
        self,
        *,
        session: CapabilitySession,
        binding: CodeGraphBinding,
        tool_name: str,
        ok: bool,
        duration_ms: int,
        error_detail: str | None,
    ) -> None:
        try:
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.codegraph_query (
                      capability_session_id,
                      registry_id,
                      worker_generation,
                      tool_name,
                      ok,
                      duration_ms,
                      error_detail
                    )
                    VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s)
                    """,
                    (
                        session.capability_session_id,
                        binding.registry_id,
                        binding.worker_generation,
                        tool_name,
                        ok,
                        duration_ms,
                        error_detail,
                    ),
                )
                conn.commit()
        except Exception:
            log.exception("failed to persist CodeGraph query telemetry")

    @staticmethod
    def _binding_from_row(row: dict[str, Any]) -> CodeGraphBinding:
        return CodeGraphBinding(
            registry_id=str(row["registry_id"]),
            worker_generation=int(row["worker_generation"]),
            worker_endpoint=str(row["worker_endpoint"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            realm=str(row["realm"]),
            repository=(str(row["repository"]) if row.get("repository") else None),
            revision=str(row["indexed_revision"]).lower(),
            codegraph_version=str(row["codegraph_version"]),
            index_profile=str(row["index_profile"]),
        )

    @staticmethod
    def _session_from_row(row: dict[str, Any]) -> CapabilitySession:
        return CapabilitySession(
            capability_session_id=str(row["capability_session_id"]),
            project_id=str(row["project_id"]),
            run_id=str(row["run_id"]),
            realm=str(row["realm"]),
            repository=(str(row["repository"]) if row.get("repository") else None),
            revision=str(row["revision"]).lower(),
            role=str(row["role"]),
            stage=(str(row["stage"]) if row.get("stage") else None),
            status=str(row["status"]),
            authorized_tools=tuple(str(name) for name in row["authorized_tools"]),
            codegraph_registry_id=str(row["codegraph_registry_id"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )


_current_session: ContextVar[CapabilitySession | None] = ContextVar(
    "memory_steward_capability_session", default=None
)
_current_binding: ContextVar[CodeGraphBinding | None] = ContextVar(
    "memory_steward_codegraph_binding", default=None
)


def _extract_capability_token(headers: dict[str, str] | None = None) -> str | None:
    raw_headers = headers if headers is not None else get_http_headers(include_all=True)
    normalized = {str(key).lower(): str(value) for key, value in raw_headers.items()}
    explicit = normalized.get(CAPABILITY_HEADER)
    if explicit:
        return explicit.strip()
    authorization = normalized.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        candidate = authorization[7:].strip()
        if candidate.startswith(TOKEN_PREFIX):
            return candidate
    return None


class CodeGraphRouter:
    def __init__(self, store: CapabilitySessionStore, *, proxy_token: str | None):
        self.store = store
        self.proxy_token = proxy_token

    def _headers(self) -> dict[str, str]:
        if not self.proxy_token:
            return {}
        return {"Authorization": f"Bearer {self.proxy_token}"}

    async def list_tools(self, binding: CodeGraphBinding) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{binding.worker_endpoint.rstrip('/')}/v1/tools",
                headers=self._headers(),
            )
            response.raise_for_status()
            payload = response.json()
        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise CodeGraphUnavailable("CodeGraph worker returned an invalid tools payload")
        return [tool for tool in tools if isinstance(tool, dict)]

    async def call_tool(
        self,
        *,
        session: CapabilitySession,
        binding: CodeGraphBinding,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        started = time.monotonic()
        ok = False
        error_detail: str | None = None
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{binding.worker_endpoint.rstrip('/')}/v1/call",
                    headers=self._headers(),
                    json={"name": name, "arguments": arguments},
                )
                response.raise_for_status()
                payload = response.json()
            parsed = mt.CallToolResult.model_validate(payload)
            structured = getattr(parsed, "structured_content", None)
            if structured is None:
                structured = getattr(parsed, "structuredContent", None)
            is_error = bool(
                getattr(parsed, "is_error", getattr(parsed, "isError", False))
            )
            ok = not is_error
            if is_error:
                error_detail = "CodeGraph tool returned isError=true"
            return ToolResult(
                content=list(parsed.content),
                structured_content=structured,
                meta=getattr(parsed, "meta", None),
                is_error=is_error,
            )
        except Exception as exc:
            error_detail = str(exc)
            raise ToolError(f"CodeGraph backend call failed: {exc}") from exc
        finally:
            duration_ms = max(0, int((time.monotonic() - started) * 1000))
            await anyio.to_thread.run_sync(
                lambda: self.store.record_query(
                    session=session,
                    binding=binding,
                    tool_name=name,
                    ok=ok,
                    duration_ms=duration_ms,
                    error_detail=error_detail,
                )
            )


class CodeGraphTool(Tool):
    router: Any = Field(exclude=True, repr=False)

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        session = _current_session.get()
        binding = _current_binding.get()
        if session is None or binding is None:
            raise ToolError("CodeGraph tool requires an active capability session")
        if self.name not in session.authorized_tools or self.name not in AGENT_CODEGRAPH_TOOLS:
            raise ToolError("CodeGraph tool is not authorized for this capability session")
        return await self.router.call_tool(
            session=session,
            binding=binding,
            name=self.name,
            arguments=arguments,
        )


class CodeGraphProvider(Provider):
    def __init__(self, router: CodeGraphRouter):
        super().__init__()
        self.router = router

    async def _list_tools(self) -> Sequence[Tool]:
        session = _current_session.get()
        binding = _current_binding.get()
        if session is None or binding is None:
            return []
        descriptors = await self.router.list_tools(binding)
        tools: list[Tool] = []
        for descriptor in descriptors:
            name = descriptor.get("name")
            if (
                not isinstance(name, str)
                or name not in AGENT_CODEGRAPH_TOOLS
                or name not in session.authorized_tools
            ):
                continue
            tools.append(self._tool_from_descriptor(descriptor))
        return tools

    async def _get_tool(self, name: str, version: Any = None) -> Tool | None:
        del version
        session = _current_session.get()
        binding = _current_binding.get()
        if (
            session is None
            or binding is None
            or name not in AGENT_CODEGRAPH_TOOLS
            or name not in session.authorized_tools
        ):
            return None
        descriptors = await self.router.list_tools(binding)
        for descriptor in descriptors:
            if descriptor.get("name") == name:
                return self._tool_from_descriptor(descriptor)
        return None

    def _tool_from_descriptor(self, descriptor: dict[str, Any]) -> CodeGraphTool:
        parameters = descriptor.get("inputSchema")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}
        output_schema = descriptor.get("outputSchema")
        if not isinstance(output_schema, dict):
            output_schema = None
        description = descriptor.get("description")
        return CodeGraphTool(
            name=str(descriptor["name"]),
            description=(str(description) if description else None),
            parameters=parameters,
            output_schema=output_schema,
            router=self.router,
        )


class CapabilitySessionMiddleware(Middleware):
    def __init__(self, store: CapabilitySessionStore):
        self.store = store

    async def _resolve(self, token: str) -> CapabilitySession:
        try:
            return await anyio.to_thread.run_sync(lambda: self.store.resolve_session(token))
        except CapabilitySessionError as exc:
            raise ToolError(str(exc)) from exc

    async def _binding_or_none(
        self, session: CapabilitySession
    ) -> CodeGraphBinding | None:
        try:
            return await anyio.to_thread.run_sync(
                lambda: self.store.resolve_backend(session)
            )
        except CodeGraphUnavailable:
            return None

    @staticmethod
    def _set_context(
        session: CapabilitySession,
        binding: CodeGraphBinding | None,
    ) -> tuple[Token[CapabilitySession | None], Token[CodeGraphBinding | None]]:
        return _current_session.set(session), _current_binding.set(binding)

    @staticmethod
    def _reset_context(
        tokens: tuple[Token[CapabilitySession | None], Token[CodeGraphBinding | None]],
    ) -> None:
        session_token, binding_token = tokens
        _current_binding.reset(binding_token)
        _current_session.reset(session_token)

    async def on_list_tools(
        self,
        context: MiddlewareContext[mt.ListToolsRequest],
        call_next: CallNext[mt.ListToolsRequest, Sequence[Tool]],
    ) -> Sequence[Tool]:
        token = _extract_capability_token()
        if token is None:
            return await call_next(context)
        session = await self._resolve(token)
        binding = await self._binding_or_none(session)
        tokens = self._set_context(session, binding)
        try:
            tools = await call_next(context)
            allowed = set(session.authorized_tools)
            return [tool for tool in tools if tool.name in allowed]
        finally:
            self._reset_context(tokens)

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name = context.message.name
        token = _extract_capability_token()
        if token is None:
            if tool_name in AGENT_CODEGRAPH_TOOLS or tool_name.startswith("codegraph_"):
                raise ToolError("CodeGraph tools require a capability session")
            return await call_next(context)

        session = await self._resolve(token)
        if tool_name not in session.authorized_tools:
            raise ToolError("tool is not authorized for this capability session")

        arguments = context.message.arguments or {}
        if tool_name in PROJECT_SCOPED_NATIVE_TOOLS:
            supplied_project = arguments.get("project_id")
            if supplied_project != session.project_id:
                raise ToolError("project_id does not match the capability session")

        binding: CodeGraphBinding | None = None
        if tool_name in AGENT_CODEGRAPH_TOOLS:
            try:
                binding = await anyio.to_thread.run_sync(
                    lambda: self.store.resolve_backend(session)
                )
            except CodeGraphUnavailable as exc:
                raise ToolError(str(exc)) from exc

        tokens = self._set_context(session, binding)
        try:
            return await call_next(context)
        finally:
            self._reset_context(tokens)


@dataclass(frozen=True)
class CodeGraphPlane:
    store: CapabilitySessionStore
    router: CodeGraphRouter
    provider: CodeGraphProvider
    middleware: CapabilitySessionMiddleware


def _issuer_authorized(request: Request, issuer_token: str) -> bool:
    if not issuer_token:
        return False
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return False
    supplied = authorization[7:]
    return secrets.compare_digest(supplied, issuer_token)


def register_codegraph_plane(
    mcp: FastMCP,
    *,
    store: CapabilitySessionStore | None = None,
    proxy_token: str | None = None,
    issuer_token: str | None = None,
    mcp_endpoint: str | None = None,
) -> CodeGraphPlane:
    resolved_store = store or CapabilitySessionStore(os.environ["POSTGRES_DSN"])
    resolved_proxy_token = (
        proxy_token
        if proxy_token is not None
        else (os.environ.get("CODEGRAPH_WORKER_PROXY_TOKEN") or None)
    )
    resolved_issuer_token = (
        issuer_token
        if issuer_token is not None
        else (os.environ.get("CODEGRAPH_SESSION_ISSUER_TOKEN") or "")
    )
    resolved_mcp_endpoint = mcp_endpoint or os.environ.get(
        "MEMORY_STEWARD_MCP_ENDPOINT", "http://memory-steward-mcp:8081/mcp/"
    )

    router = CodeGraphRouter(resolved_store, proxy_token=resolved_proxy_token)
    provider = CodeGraphProvider(router)
    middleware = CapabilitySessionMiddleware(resolved_store)
    plane = CodeGraphPlane(
        store=resolved_store,
        router=router,
        provider=provider,
        middleware=middleware,
    )
    mcp.add_provider(provider)
    mcp.add_middleware(middleware)

    @mcp.custom_route("/v1/codegraph/capability-sessions", methods=["POST"])
    async def issue_codegraph_session(request: Request) -> JSONResponse:
        if not resolved_issuer_token:
            return JSONResponse(
                {"detail": "CODEGRAPH_SESSION_ISSUER_TOKEN is not configured"},
                status_code=503,
            )
        if not _issuer_authorized(request, resolved_issuer_token):
            return JSONResponse({"detail": "invalid issuer token"}, status_code=401)
        try:
            payload = CapabilityIssueRequest.model_validate(await request.json())
            realm, revision = resolved_store.validate_identity(
                realm=payload.realm,
                revision=payload.revision,
            )
        except (ValidationError, ValueError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)

        try:
            binding = await anyio.to_thread.run_sync(
                lambda: resolved_store.find_ready_backend(
                    project_id=payload.project_id,
                    run_id=payload.run_id,
                    realm=realm,
                    repository=payload.repository,
                    revision=revision,
                )
            )
            descriptors = await router.list_tools(binding)
            codegraph_tools = sorted(
                {
                    str(tool["name"])
                    for tool in descriptors
                    if isinstance(tool.get("name"), str)
                    and tool["name"] in AGENT_CODEGRAPH_TOOLS
                }
            )
            if not codegraph_tools:
                raise CodeGraphUnavailable("READY CodeGraph worker exposes no authorized query tools")
            authorized_tools = sorted(BASE_AGENT_READ_TOOLS | set(codegraph_tools))
            session, access_token = await anyio.to_thread.run_sync(
                lambda: resolved_store.create_session(
                    binding=binding,
                    role=payload.role,
                    stage=payload.stage,
                    ttl_seconds=payload.ttl_seconds,
                    authorized_tools=authorized_tools,
                )
            )
        except CodeGraphUnavailable as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except CodeGraphAmbiguous as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except httpx.HTTPError as exc:
            return JSONResponse(
                {"detail": f"CodeGraph worker is not reachable: {exc}"}, status_code=503
            )

        return JSONResponse(
            {
                "capability_session_id": session.capability_session_id,
                "access_token": access_token,
                "credential_header": "X-Memory-Capability",
                "mcp_endpoint": resolved_mcp_endpoint,
                "project_id": session.project_id,
                "run_id": session.run_id,
                "realm": session.realm,
                "repository": session.repository,
                "revision": session.revision,
                "role": session.role,
                "stage": session.stage,
                "expires_at": session.expires_at.isoformat(),
                "capabilities": {
                    "memory_read": {"tools": sorted(BASE_AGENT_READ_TOOLS)},
                    "codegraph": {
                        "ready": True,
                        "registry_id": binding.registry_id,
                        "codegraph_version": binding.codegraph_version,
                        "index_profile": binding.index_profile,
                        "tools": codegraph_tools,
                    },
                },
            },
            status_code=201,
        )

    @mcp.custom_route(
        "/v1/codegraph/capability-sessions/{session_id}/release",
        methods=["POST"],
    )
    async def release_codegraph_session(request: Request) -> JSONResponse:
        if not resolved_issuer_token:
            return JSONResponse(
                {"detail": "CODEGRAPH_SESSION_ISSUER_TOKEN is not configured"},
                status_code=503,
            )
        if not _issuer_authorized(request, resolved_issuer_token):
            return JSONResponse({"detail": "invalid issuer token"}, status_code=401)
        session_id = request.path_params["session_id"]
        try:
            updated = await anyio.to_thread.run_sync(
                lambda: resolved_store.release_session(session_id)
            )
        except psycopg.Error as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        if not updated:
            return JSONResponse(
                {"detail": "active capability session not found"}, status_code=404
            )
        return JSONResponse({"released": True})

    return plane
