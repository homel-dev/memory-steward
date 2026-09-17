from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError

from memory_steward_mcp.codegraph_plane import (
    AGENT_CODEGRAPH_TOOLS,
    BASE_AGENT_READ_TOOLS,
    CapabilitySession,
    CapabilitySessionMiddleware,
    CapabilitySessionStore,
    CodeGraphBinding,
    CodeGraphProvider,
    CodeGraphRouter,
    MiddlewareContext,
    _extract_capability_token,
)


def _session() -> CapabilitySession:
    now = datetime.now(timezone.utc)
    return CapabilitySession(
        capability_session_id="00000000-0000-0000-0000-000000000010",
        project_id="rr",
        run_id="run-1",
        realm="workspace",
        repository="homel-dev/relentless-rekrow",
        revision="a" * 40,
        role="coder",
        stage="execute",
        status="active",
        authorized_tools=tuple(
            sorted(BASE_AGENT_READ_TOOLS | {"codegraph_get_callers"})
        ),
        codegraph_registry_id="00000000-0000-0000-0000-000000000020",
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )


def _binding() -> CodeGraphBinding:
    return CodeGraphBinding(
        registry_id="00000000-0000-0000-0000-000000000020",
        worker_generation=3,
        worker_endpoint="http://cg-serve-000000000000-g3.ms.svc.cluster.local:8094",
        project_id="rr",
        run_id="run-1",
        realm="workspace",
        repository="homel-dev/relentless-rekrow",
        revision="a" * 40,
        codegraph_version="0.20.1",
        index_profile="graph-only",
    )


class _Store:
    def resolve_session(self, token: str) -> CapabilitySession:
        assert token == "mscs_test"
        return _session()

    def resolve_backend(self, session: CapabilitySession) -> CodeGraphBinding:
        assert session.capability_session_id == _session().capability_session_id
        return _binding()


def test_capability_token_extraction_does_not_hijack_unrelated_bearer_auth():
    assert (
        _extract_capability_token({"X-Memory-Capability": "mscs_explicit"})
        == "mscs_explicit"
    )
    assert (
        _extract_capability_token({"Authorization": "Bearer mscs_fallback"})
        == "mscs_fallback"
    )
    assert _extract_capability_token({"Authorization": "Bearer ordinary-oauth"}) is None


def test_identity_validation_requires_known_realm_and_full_git_sha():
    assert CapabilitySessionStore.validate_identity(
        realm="workspace", revision="A" * 40
    ) == ("workspace", "a" * 40)
    with pytest.raises(ValueError, match="realm"):
        CapabilitySessionStore.validate_identity(realm="oracle-ish", revision="a" * 40)
    with pytest.raises(ValueError, match="40-character"):
        CapabilitySessionStore.validate_identity(realm="workspace", revision="abc123")


def test_agent_codegraph_allowlist_excludes_mutating_admin_tools():
    assert "codegraph_get_callers" in AGENT_CODEGRAPH_TOOLS
    assert "codegraph_symbol_search" in AGENT_CODEGRAPH_TOOLS
    assert "codegraph_reindex_workspace" not in AGENT_CODEGRAPH_TOOLS
    assert "codegraph_index_files" not in AGENT_CODEGRAPH_TOOLS
    assert "codegraph_memory_store" not in AGENT_CODEGRAPH_TOOLS


@pytest.mark.asyncio
async def test_session_tools_list_is_filtered_to_manifest(monkeypatch):
    middleware = CapabilitySessionMiddleware(_Store())
    monkeypatch.setattr(
        "memory_steward_mcp.codegraph_plane._extract_capability_token",
        lambda: "mscs_test",
    )
    context = MiddlewareContext(message=SimpleNamespace())
    visible = SimpleNamespace(name="codegraph_get_callers")
    hidden = SimpleNamespace(name="memory.submit_agent_outcome")
    call_next = AsyncMock(return_value=[visible, hidden])

    result = await middleware.on_list_tools(context, call_next)

    assert [tool.name for tool in result] == ["codegraph_get_callers"]


@pytest.mark.asyncio
async def test_session_rejects_cross_project_native_tool_call(monkeypatch):
    middleware = CapabilitySessionMiddleware(_Store())
    monkeypatch.setattr(
        "memory_steward_mcp.codegraph_plane._extract_capability_token",
        lambda: "mscs_test",
    )
    context = MiddlewareContext(
        message=SimpleNamespace(
            name="memory.reference.search",
            arguments={"project_id": "other", "query": "x"},
        )
    )
    call_next = AsyncMock()

    with pytest.raises(ToolError, match="project_id"):
        await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_codegraph_direct_call_requires_capability_session(monkeypatch):
    middleware = CapabilitySessionMiddleware(_Store())
    monkeypatch.setattr(
        "memory_steward_mcp.codegraph_plane._extract_capability_token",
        lambda: None,
    )
    context = MiddlewareContext(
        message=SimpleNamespace(
            name="codegraph_get_callers",
            arguments={"name": "main"},
        )
    )
    call_next = AsyncMock()

    with pytest.raises(ToolError, match="capability session"):
        await middleware.on_call_tool(context, call_next)
    call_next.assert_not_awaited()


def test_dynamic_tool_keeps_upstream_input_schema():
    router = CodeGraphRouter(_Store(), proxy_token=None)  # type: ignore[arg-type]
    provider = CodeGraphProvider(router)
    tool = provider._tool_from_descriptor(
        {
            "name": "codegraph_get_callers",
            "description": "Find callers",
            "inputSchema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
    )

    assert tool.name == "codegraph_get_callers"
    assert tool.parameters["required"] == ["name"]
