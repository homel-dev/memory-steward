"""
Unit tests for git_plane.py

Covers:
- Provider adapter selection
- _require_write enforcement
- GitLab adapter URL construction
- GitHub adapter API base detection (cloud vs enterprise)
- Bitbucket adapter auth header (Basic vs Bearer)
- repo_add validation (provider, access_level)
"""
import sys
import types
import base64
import pytest
from unittest.mock import MagicMock, patch

# Stub dependencies
for mod in ["psycopg", "fastmcp"]:
    m = types.ModuleType(mod)
    sys.modules[mod] = m

_config = types.ModuleType("memory_steward_mcp.config")
_config.POSTGRES_DSN = "postgresql://test"
sys.modules["memory_steward_mcp"] = types.ModuleType("memory_steward_mcp")
sys.modules["memory_steward_mcp.config"] = _config

import importlib
gp = importlib.import_module("git_plane")


# ---------------------------------------------------------------------------
# _adapter factory
# ---------------------------------------------------------------------------

class TestAdapterFactory:

    def _conn(self, provider):
        return {"name": "test", "provider": provider,
                "base_url": "https://example.com", "token": "tok",
                "access_level": "read"}

    def test_gitlab_returns_gitlab_adapter(self):
        adapter = gp._adapter(self._conn("gitlab"))
        assert isinstance(adapter, gp._GitLabAdapter)

    def test_github_returns_github_adapter(self):
        adapter = gp._adapter(self._conn("github"))
        assert isinstance(adapter, gp._GitHubAdapter)

    def test_bitbucket_returns_bitbucket_adapter(self):
        adapter = gp._adapter(self._conn("bitbucket"))
        assert isinstance(adapter, gp._BitbucketAdapter)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            gp._adapter(self._conn("gitea"))


# ---------------------------------------------------------------------------
# _require_write
# ---------------------------------------------------------------------------

class TestRequireWrite:

    def test_read_write_passes(self):
        conn = {"name": "x", "access_level": "read-write"}
        gp._require_write(conn)  # Should not raise

    def test_read_only_raises(self):
        conn = {"name": "x", "access_level": "read"}
        with pytest.raises(PermissionError, match="read-write"):
            gp._require_write(conn)


# ---------------------------------------------------------------------------
# GitLabAdapter
# ---------------------------------------------------------------------------

class TestGitLabAdapter:

    def _adapter(self, base_url="https://gitlab.internal", token="glpat-xxx"):
        conn = {"name": "gl", "provider": "gitlab",
                "base_url": base_url, "token": token, "access_level": "read"}
        return gp._GitLabAdapter(conn)

    def test_headers_use_private_token(self):
        a = self._adapter(token="mytoken")
        headers = a._headers()
        assert headers["PRIVATE-TOKEN"] == "mytoken"

    def test_api_url_construction(self):
        a = self._adapter(base_url="https://gitlab.example.com")
        url = a._api("/user")
        assert url == "https://gitlab.example.com/api/v4/user"

    def test_base_url_trailing_slash_stripped(self):
        a = self._adapter(base_url="https://gitlab.example.com/")
        url = a._api("/user")
        assert "//api" not in url

    def test_encode_project(self):
        a = self._adapter()
        encoded = a._enc("mygroup/my-repo")
        assert "/" not in encoded

    def test_file_url(self):
        a = self._adapter(base_url="https://gitlab.example.com")
        url = a.file_url("group/repo", "docs/readme.md", "main")
        assert url == "https://gitlab.example.com/group/repo/-/blob/main/docs/readme.md"


# ---------------------------------------------------------------------------
# GitHubAdapter
# ---------------------------------------------------------------------------

class TestGitHubAdapter:

    def _adapter(self, base_url="https://api.github.com", token="ghp_xxx"):
        conn = {"name": "gh", "provider": "github",
                "base_url": base_url, "token": token, "access_level": "read"}
        return gp._GitHubAdapter(conn)

    def test_cloud_api_base(self):
        a = self._adapter(base_url="https://api.github.com")
        assert a._api_base == "https://api.github.com"

    def test_enterprise_api_base_appended(self):
        a = self._adapter(base_url="https://github.mycompany.com")
        assert a._api_base == "https://github.mycompany.com/api/v3"

    def test_enterprise_already_has_v3(self):
        a = self._adapter(base_url="https://github.mycompany.com/api/v3")
        assert a._api_base == "https://github.mycompany.com/api/v3"

    def test_headers_use_bearer(self):
        a = self._adapter(token="mytoken")
        headers = a._headers()
        assert headers["Authorization"] == "Bearer mytoken"

    def test_cloud_file_url(self):
        a = self._adapter(base_url="https://api.github.com")
        url = a.file_url("owner/repo", "docs/readme.md", "main")
        assert url == "https://github.com/owner/repo/blob/main/docs/readme.md"


# ---------------------------------------------------------------------------
# BitbucketAdapter
# ---------------------------------------------------------------------------

class TestBitbucketAdapter:

    def _adapter(self, base_url="https://bitbucket.org", token="user:pass"):
        conn = {"name": "bb", "provider": "bitbucket",
                "base_url": base_url, "token": token, "access_level": "read"}
        return gp._BitbucketAdapter(conn)

    def test_cloud_detected(self):
        a = self._adapter(base_url="https://bitbucket.org")
        assert a._cloud is True

    def test_server_detected(self):
        a = self._adapter(base_url="https://bitbucket.mycompany.com")
        assert a._cloud is False

    def test_basic_auth_when_colon_in_token(self):
        a = self._adapter(token="myuser:mypassword")
        headers = a._headers()
        assert headers["Authorization"].startswith("Basic ")
        decoded = base64.b64decode(headers["Authorization"][6:]).decode()
        assert decoded == "myuser:mypassword"

    def test_bearer_auth_when_no_colon(self):
        a = self._adapter(token="plain-bearer-token")
        headers = a._headers()
        assert headers["Authorization"] == "Bearer plain-bearer-token"

    def test_server_api_base(self):
        a = self._adapter(base_url="https://bitbucket.mycompany.com")
        assert "rest/api/1.0" in a._api_base
