# git_plane.py
"""
Git Plane: provider-agnostic repository connections and read/write tools.

Supports GitLab, GitHub, and Bitbucket via their REST APIs.
Connections are stored in Postgres (git_connections table) and managed
entirely through MCP tools — no hardcoded credentials anywhere.

Connection management:
  repo_add        — register a named connection
  repo_list       — list all connections
  repo_remove     — delete a connection
  repo_test       — verify a connection works

Read tools (any access level):
  git_list_repos      — list repos accessible via a connection
  git_ingest_repo     — bulk-ingest a repo as reference memory
  git_ingest_file     — ingest a single file

Write tools (read-write access level only):
  git_write_file      — create or update a file in a repo

Provider differences handled internally:
  gitlab    — PRIVATE-TOKEN header, /api/v4/projects/.../repository/...
  github    — Authorization: Bearer, /repos/{owner}/{repo}/contents/...
  bitbucket — Authorization: Bearer (app password), /2.0/repositories/.../src/...
"""

import base64
import logging
import re
import time
from typing import Optional

import psycopg
import requests
from fastmcp import FastMCP

from memory_steward_mcp.config import POSTGRES_DSN

log = logging.getLogger("memory-steward-mcp.git")

VALID_PROVIDERS = ("gitlab", "github", "bitbucket")

# ---------------------------------------------------------------------------
# Connection registry
# ---------------------------------------------------------------------------

def _get_connection(name: str) -> dict:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT name, provider, base_url, token, access_level "
            "FROM git_connections WHERE name = %s",
            (name,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(
            f"No git connection named '{name}'. "
            f"Use repo_list to see available connections, or repo_add to register one."
        )
    return {
        "name": row[0],
        "provider": row[1],
        "base_url": row[2].rstrip("/"),
        "token": row[3],
        "access_level": row[4],
    }


def _require_write(conn: dict) -> None:
    if conn["access_level"] != "read-write":
        raise PermissionError(
            f"Connection '{conn['name']}' has access_level='{conn['access_level']}'. "
            f"Write operations require access_level='read-write'."
        )


# ---------------------------------------------------------------------------
# Provider adapters
# ---------------------------------------------------------------------------

class _GitLabAdapter:
    def __init__(self, conn: dict):
        self.conn = conn

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": self.conn["token"], "Content-Type": "application/json"}

    def _api(self, path: str) -> str:
        return f"{self.conn['base_url']}/api/v4{path}"

    def _enc(self, project: str) -> str:
        return requests.utils.quote(project, safe="")

    def test(self) -> dict:
        r = requests.get(self._api("/user"), headers=self._headers(), timeout=10)
        r.raise_for_status()
        u = r.json()
        return {"username": u.get("username"), "name": u.get("name")}

    def list_repos(self, search: str, owned: bool) -> list[dict]:
        params = {"per_page": 50, "order_by": "last_activity_at"}
        if owned:
            params["owned"] = "true"
        if search:
            params["search"] = search
        r = requests.get(self._api("/projects"), headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return [
            {"path": p["path_with_namespace"], "description": p.get("description", ""),
             "default_branch": p.get("default_branch", "main")}
            for p in r.json()
        ]

    def list_files(self, project: str, path: str, ref: str) -> list[dict]:
        enc = self._enc(project)
        files, page = [], 1
        while True:
            r = requests.get(
                self._api(f"/projects/{enc}/repository/tree"),
                headers=self._headers(),
                params={"path": path, "ref": ref, "recursive": True, "per_page": 100, "page": page},
                timeout=30,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return [f for f in files if f.get("type") == "blob"]

    def fetch_file(self, project: str, file_path: str, ref: str) -> str:
        enc = self._enc(project)
        enc_path = requests.utils.quote(file_path, safe="")
        r = requests.get(
            self._api(f"/projects/{enc}/repository/files/{enc_path}"),
            headers=self._headers(),
            params={"ref": ref},
            timeout=30,
        )
        r.raise_for_status()
        return base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")

    def write_file(self, project: str, file_path: str, content: str,
                   commit_message: str, ref: str, overwrite: bool) -> str:
        enc = self._enc(project)
        enc_path = requests.utils.quote(file_path, safe="")
        check = requests.get(
            self._api(f"/projects/{enc}/repository/files/{enc_path}"),
            headers=self._headers(), params={"ref": ref}, timeout=10,
        )
        file_exists = check.status_code == 200
        if file_exists and not overwrite:
            return None  # caller handles
        r = requests.request(
            "PUT" if file_exists else "POST",
            self._api(f"/projects/{enc}/repository/files/{enc_path}"),
            headers=self._headers(),
            json={"branch": ref, "content": content,
                  "commit_message": commit_message, "encoding": "text"},
            timeout=30,
        )
        r.raise_for_status()
        return "updated" if file_exists else "created"

    def file_url(self, project: str, file_path: str, ref: str) -> str:
        return f"{self.conn['base_url']}/{project}/-/blob/{ref}/{file_path}"


class _GitHubAdapter:
    def __init__(self, conn: dict):
        self.conn = conn
        # GitHub base URL: https://api.github.com for cloud,
        # or https://github.yourdomain.com/api/v3 for GitHub Enterprise
        base = self.conn["base_url"]
        if "api.github.com" in base or base.endswith("/api/v3"):
            self._api_base = base
        else:
            self._api_base = f"{base}/api/v3"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.conn['token']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _api(self, path: str) -> str:
        return f"{self._api_base}{path}"

    def test(self) -> dict:
        r = requests.get(self._api("/user"), headers=self._headers(), timeout=10)
        r.raise_for_status()
        u = r.json()
        return {"username": u.get("login"), "name": u.get("name")}

    def list_repos(self, search: str, owned: bool) -> list[dict]:
        params = {"per_page": 50, "sort": "updated"}
        if owned:
            params["affiliation"] = "owner"
        r = requests.get(self._api("/user/repos"), headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        repos = r.json()
        if search:
            repos = [p for p in repos if search.lower() in p["full_name"].lower()]
        return [
            {"path": p["full_name"], "description": p.get("description", ""),
             "default_branch": p.get("default_branch", "main")}
            for p in repos
        ]

    def list_files(self, project: str, path: str, ref: str) -> list[dict]:
        # GitHub Trees API — recursive, single call
        owner, repo = project.split("/", 1)
        r = requests.get(
            self._api(f"/repos/{owner}/{repo}/git/trees/{ref}"),
            headers=self._headers(),
            params={"recursive": "1"},
            timeout=30,
        )
        r.raise_for_status()
        tree = r.json().get("tree", [])
        return [
            {"name": t["path"].split("/")[-1], "path": t["path"], "type": "blob"}
            for t in tree
            if t["type"] == "blob" and (not path or t["path"].startswith(path))
        ]

    def fetch_file(self, project: str, file_path: str, ref: str) -> str:
        owner, repo = project.split("/", 1)
        r = requests.get(
            self._api(f"/repos/{owner}/{repo}/contents/{file_path}"),
            headers=self._headers(),
            params={"ref": ref},
            timeout=30,
        )
        r.raise_for_status()
        return base64.b64decode(r.json()["content"]).decode("utf-8", errors="replace")

    def write_file(self, project: str, file_path: str, content: str,
                   commit_message: str, ref: str, overwrite: bool) -> str:
        owner, repo = project.split("/", 1)
        # Check if file exists (need SHA for updates)
        check = requests.get(
            self._api(f"/repos/{owner}/{repo}/contents/{file_path}"),
            headers=self._headers(), params={"ref": ref}, timeout=10,
        )
        file_exists = check.status_code == 200
        if file_exists and not overwrite:
            return None
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": ref,
        }
        if file_exists:
            payload["sha"] = check.json()["sha"]
        r = requests.put(
            self._api(f"/repos/{owner}/{repo}/contents/{file_path}"),
            headers=self._headers(), json=payload, timeout=30,
        )
        r.raise_for_status()
        return "updated" if file_exists else "created"

    def file_url(self, project: str, file_path: str, ref: str) -> str:
        base = self.conn["base_url"].rstrip("/")
        if "api.github.com" in base:
            base = "https://github.com"
        elif base.endswith("/api/v3"):
            base = base[:-len("/api/v3")]
        return f"{base}/{project}/blob/{ref}/{file_path}"


class _BitbucketAdapter:
    """
    Bitbucket Cloud (api.bitbucket.org/2.0) and Bitbucket Server/Data Center.
    Token should be an App Password (Cloud) or Personal Access Token (Server).
    For Cloud: token format is 'username:app_password' or just the app_password
    if username is embedded in base_url.
    Simplest: store as 'username:apppassword' in token field.
    """
    def __init__(self, conn: dict):
        self.conn = conn
        base = self.conn["base_url"]
        # Cloud
        if "bitbucket.org" in base:
            self._api_base = "https://api.bitbucket.org/2.0"
            self._cloud = True
        else:
            # Server/Data Center
            self._api_base = f"{base}/rest/api/1.0"
            self._cloud = False

    def _headers(self) -> dict:
        token = self.conn["token"]
        if ":" in token:
            # username:password or username:app_password
            encoded = base64.b64encode(token.encode()).decode()
            return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _api(self, path: str) -> str:
        return f"{self._api_base}{path}"

    def test(self) -> dict:
        if self._cloud:
            r = requests.get(self._api("/user"), headers=self._headers(), timeout=10)
            r.raise_for_status()
            u = r.json()
            return {"username": u.get("account_id"), "name": u.get("display_name")}
        else:
            r = requests.get(self._api("/users/~"), headers=self._headers(), timeout=10)
            r.raise_for_status()
            u = r.json()
            return {"username": u.get("slug"), "name": u.get("displayName")}

    def list_repos(self, search: str, owned: bool) -> list[dict]:
        if self._cloud:
            r = requests.get(
                self._api("/repositories"),
                headers=self._headers(),
                params={"role": "owner" if owned else "member", "pagelen": 50},
                timeout=30,
            )
            r.raise_for_status()
            repos = r.json().get("values", [])
            if search:
                repos = [p for p in repos if search.lower() in p["full_name"].lower()]
            return [
                {"path": p["full_name"], "description": p.get("description", ""),
                 "default_branch": p.get("mainbranch", {}).get("name", "main")}
                for p in repos
            ]
        else:
            r = requests.get(
                self._api("/repos"),
                headers=self._headers(),
                params={"limit": 50},
                timeout=30,
            )
            r.raise_for_status()
            repos = r.json().get("values", [])
            return [
                {"path": f"{p['project']['key']}/{p['slug']}",
                 "description": p.get("description", ""),
                 "default_branch": "main"}
                for p in repos
            ]

    def list_files(self, project: str, path: str, ref: str) -> list[dict]:
        if self._cloud:
            workspace, repo = project.split("/", 1)
            url = self._api(f"/repositories/{workspace}/{repo}/src/{ref}/{path}")
            files = []
            while url:
                r = requests.get(url, headers=self._headers(),
                                  params={"pagelen": 100}, timeout=30)
                r.raise_for_status()
                data = r.json()
                files.extend([
                    {"name": v["path"].split("/")[-1], "path": v["path"], "type": "blob"}
                    for v in data.get("values", [])
                    if v["type"] == "commit_file"
                ])
                url = data.get("next")
            return files
        else:
            proj, repo = project.split("/", 1)
            r = requests.get(
                self._api(f"/projects/{proj}/repos/{repo}/files/{path}"),
                headers=self._headers(),
                params={"at": ref, "limit": 1000},
                timeout=30,
            )
            r.raise_for_status()
            return [
                {"name": v.split("/")[-1], "path": v, "type": "blob"}
                for v in r.json().get("values", [])
            ]

    def fetch_file(self, project: str, file_path: str, ref: str) -> str:
        if self._cloud:
            workspace, repo = project.split("/", 1)
            r = requests.get(
                self._api(f"/repositories/{workspace}/{repo}/src/{ref}/{file_path}"),
                headers=self._headers(), timeout=30,
            )
        else:
            proj, repo = project.split("/", 1)
            r = requests.get(
                self._api(f"/projects/{proj}/repos/{repo}/raw/{file_path}"),
                headers=self._headers(),
                params={"at": ref},
                timeout=30,
            )
        r.raise_for_status()
        return r.text

    def write_file(self, project: str, file_path: str, content: str,
                   commit_message: str, ref: str, overwrite: bool) -> str:
        if self._cloud:
            workspace, repo = project.split("/", 1)
            # Bitbucket Cloud uses multipart form for file writes
            check = requests.get(
                self._api(f"/repositories/{workspace}/{repo}/src/{ref}/{file_path}"),
                headers={"PRIVATE-TOKEN": self.conn["token"]}, timeout=10,
            )
            # Cloud src endpoint returns 200 for existing files
            file_exists = check.status_code == 200
            if file_exists and not overwrite:
                return None
            h = self._headers()
            h.pop("Content-Type", None)  # let requests set multipart
            r = requests.post(
                self._api(f"/repositories/{workspace}/{repo}/src"),
                headers=h,
                data={"branch": ref, "message": commit_message},
                files={file_path: content.encode()},
                timeout=30,
            )
            r.raise_for_status()
            return "updated" if file_exists else "created"
        else:
            proj, repo = project.split("/", 1)
            r = requests.put(
                self._api(f"/projects/{proj}/repos/{repo}/browse/{file_path}"),
                headers=self._headers(),
                json={
                    "content": content,
                    "message": commit_message,
                    "branch": ref,
                },
                timeout=30,
            )
            r.raise_for_status()
            return "created/updated"

    def file_url(self, project: str, file_path: str, ref: str) -> str:
        base = self.conn["base_url"].rstrip("/")
        if self._cloud:
            return f"https://bitbucket.org/{project}/src/{ref}/{file_path}"
        return f"{base}/projects/{project}/browse/{file_path}?at={ref}"


def _adapter(conn: dict):
    provider = conn["provider"]
    if provider == "gitlab":
        return _GitLabAdapter(conn)
    if provider == "github":
        return _GitHubAdapter(conn)
    if provider == "bitbucket":
        return _BitbucketAdapter(conn)
    raise ValueError(f"Unknown provider '{provider}'. Must be one of: {VALID_PROVIDERS}")


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_git_tools(mcp: FastMCP, ingest_text_fn):

    # -----------------------------------------------------------------------
    # CONNECTION MANAGEMENT
    # -----------------------------------------------------------------------

    @mcp.tool()
    def repo_add(
        name: str,
        provider: str,
        base_url: str,
        token: str,
        access_level: str = "read",
    ) -> str:
        """[Connections] Register a named repository connection.

        Args:
          name:         Unique name, e.g. 'ms-docs', 'github-internal'
          provider:     'gitlab', 'github', or 'bitbucket'
          base_url:     Instance URL, e.g. 'https://gitlab.yourdomain.com'
                        For GitHub Cloud use 'https://api.github.com'
                        For Bitbucket Cloud use 'https://bitbucket.org'
          token:        Auth token. GitLab: Personal Access Token.
                        GitHub: Personal Access Token or fine-grained token.
                        Bitbucket: 'username:app_password' or Bearer token.
          access_level: 'read' or 'read-write'

        Examples:
          name=ms-gitlab provider=gitlab base_url=https://gitlab.internal token=glpat-xxx access_level=read
          name=gh-output provider=github base_url=https://api.github.com token=ghp_yyy access_level=read-write
          name=bb-docs provider=bitbucket base_url=https://bitbucket.org token=user:apppass access_level=read
        """
        if provider not in VALID_PROVIDERS:
            return f"Invalid provider '{provider}'. Must be one of: {VALID_PROVIDERS}"
        if access_level not in ("read", "read-write"):
            return f"Invalid access_level '{access_level}'. Must be 'read' or 'read-write'."

        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO git_connections (name, provider, base_url, token, access_level)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                      SET provider = EXCLUDED.provider,
                          base_url = EXCLUDED.base_url,
                          token = EXCLUDED.token,
                          access_level = EXCLUDED.access_level,
                          updated_at = now()
                """, (name, provider, base_url.rstrip("/"), token, access_level))
        except Exception as e:
            return f"DB error: {e}"

        log.info(f"Operator action: REPO_ADD name={name} provider={provider} access_level={access_level}")
        return f"✅ Connection '{name}' registered (provider={provider}, access_level={access_level})."

    @mcp.tool()
    def repo_list() -> str:
        """[Connections] List all registered repository connections. Tokens are masked."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT name, provider, base_url, access_level, updated_at
                    FROM git_connections ORDER BY name
                """)
                rows = cur.fetchall()
        except Exception as e:
            return f"DB error: {e}"

        if not rows:
            return "No git connections registered. Use repo_add to register one."

        lines = ["## Git Connections"]
        for name, provider, base_url, access_level, updated_at in rows:
            icon = "✍️" if access_level == "read-write" else "👁️"
            lines.append(
                f"{icon} **{name}** [{provider}] — {base_url}  "
                f"access={access_level}  "
                f"updated={updated_at.strftime('%Y-%m-%d %H:%M')}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def repo_remove(name: str) -> str:
        """[Connections] Remove a registered repository connection by name."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM git_connections WHERE name = %s RETURNING name", (name,)
                )
                if not cur.fetchone():
                    return f"No connection named '{name}' found."
        except Exception as e:
            return f"DB error: {e}"

        log.warning(f"Operator action: REPO_REMOVE name={name}")
        return f"✅ Connection '{name}' removed."

    @mcp.tool()
    def repo_test(name: str) -> str:
        """[Connections] Verify a registered connection works by calling the provider API."""
        try:
            conn = _get_connection(name)
        except ValueError as e:
            return str(e)

        try:
            adapter = _adapter(conn)
            user = adapter.test()
            return (
                f"✅ Connection '{name}' is working.\n"
                f"- Provider: {conn['provider']}\n"
                f"- Instance: {conn['base_url']}\n"
                f"- Authenticated as: {user.get('username')} ({user.get('name')})\n"
                f"- Access level: {conn['access_level']}"
            )
        except Exception as e:
            return f"❌ Connection '{name}' failed: {e}"

    # -----------------------------------------------------------------------
    # READ TOOLS
    # -----------------------------------------------------------------------

    @mcp.tool()
    def git_list_repos(
        connection: str,
        search: str = "",
        owned: bool = True,
    ) -> str:
        """[Git] List repositories accessible via a named connection.

        Args:
          connection: Name of a registered connection (see repo_list)
          search:     Optional name filter
          owned:      If true, only show repos owned by the token's user
        """
        try:
            conn = _get_connection(connection)
        except ValueError as e:
            return str(e)

        try:
            repos = _adapter(conn).list_repos(search=search, owned=owned)
        except Exception as e:
            return f"API error: {e}"

        if not repos:
            return f"No repositories found via connection '{connection}'."

        lines = [f"## Repositories via '{connection}' [{conn['provider']}]"]
        for r in repos:
            lines.append(
                f"- `{r['path']}` — {r['description'] or 'no description'}  "
                f"(branch={r['default_branch']})"
            )
        return "\n".join(lines)

    @mcp.tool()
    def git_ingest_repo(
        connection: str,
        project: str,
        product: str,
        version: str,
        scope: str = "general",
        path: str = "",
        ref: str = "main",
        file_extension: str = ".md",
    ) -> str:
        """[Git] Walk a repository and ingest all matching files as reference memory.
        Idempotent — safe to re-run after doc updates.

        Args:
          connection:     Name of a registered connection (see repo_list)
          project:        Repo path. GitLab/GitHub: 'group/repo'. Bitbucket: 'workspace/repo'
          product:        Reference memory product name, e.g. 'memory-steward'
          version:        Version label, e.g. '1.0'
          scope:          Memory scope, e.g. 'architecture', 'operations'
          path:           Sub-directory to restrict to, e.g. 'docs'
          ref:            Branch or tag, default 'main'
          file_extension: Only ingest files with this extension, default '.md'
        """
        try:
            conn = _get_connection(connection)
            adapter = _adapter(conn)
        except ValueError as e:
            return str(e)

        try:
            all_files = adapter.list_files(project, path=path, ref=ref)
        except Exception as e:
            return f"Repo tree fetch failed: {e}"

        target_files = [
            f for f in all_files
            if f.get("name", "").endswith(file_extension)
        ]

        if not target_files:
            return f"No {file_extension} files found in {project}/{path} @ {ref}."

        results, errors, total_chunks = [], [], 0

        for f in target_files:
            file_path = f["path"]
            source_url = adapter.file_url(project, file_path, ref)
            try:
                content = adapter.fetch_file(project, file_path, ref=ref)
                result = ingest_text_fn(
                    text=content,
                    product=product,
                    version=version,
                    scope=scope,
                    source_url=source_url,
                )
                match = re.search(r'\*\*(\d+) chunks\*\*', result)
                n = int(match.group(1)) if match else 0
                total_chunks += n
                results.append(f"  ✅ `{file_path}` → {n} chunks")
            except Exception as e:
                errors.append(f"  ❌ `{file_path}`: {e}")
            time.sleep(0.1)

        lines = [
            f"## Git Ingest: `{project}` @ {ref} via '{connection}' [{conn['provider']}]",
            f"- Files: {len(results) + len(errors)}  chunks: {total_chunks}  errors: {len(errors)}",
            "",
            "### Files",
        ] + results + (["", "### Errors"] + errors if errors else [])

        return "\n".join(lines)

    @mcp.tool()
    def git_ingest_file(
        connection: str,
        project: str,
        file_path: str,
        product: str,
        version: str,
        scope: str = "general",
        ref: str = "main",
    ) -> str:
        """[Git] Fetch and ingest a single file from a repository.

        Args:
          connection: Name of a registered connection (see repo_list)
          project:    Repo path, e.g. 'mygroup/memory-steward'
          file_path:  Path within repo, e.g. 'docs/01_overview.md'
          product:    Reference memory product name
          version:    Version label
          scope:      Memory scope
          ref:        Branch or tag
        """
        try:
            conn = _get_connection(connection)
            adapter = _adapter(conn)
        except ValueError as e:
            return str(e)

        source_url = adapter.file_url(project, file_path, ref)
        try:
            content = adapter.fetch_file(project, file_path, ref=ref)
        except Exception as e:
            return f"Failed to fetch `{file_path}` from `{project}`: {e}"

        return ingest_text_fn(
            text=content,
            product=product,
            version=version,
            scope=scope,
            source_url=source_url,
        )

    # -----------------------------------------------------------------------
    # WRITE TOOLS
    # -----------------------------------------------------------------------

    @mcp.tool()
    def git_write_file(
        connection: str,
        project: str,
        file_path: str,
        content: str,
        commit_message: str,
        ref: str = "main",
        overwrite: bool = False,
    ) -> str:
        """[Git] Write a file to a repository (create or update).
        Requires access_level='read-write' on the connection.

        Args:
          connection:     Name of a registered read-write connection
          project:        Repo path, e.g. 'mygroup/docs'
          file_path:      Target path, e.g. 'runbooks/my-runbook.md'
          content:        File content (plain text or markdown)
          commit_message: Git commit message
          ref:            Branch to commit to, default 'main'
          overwrite:      If false and file exists, returns error instead of updating
        """
        try:
            conn = _get_connection(connection)
            _require_write(conn)
            adapter = _adapter(conn)
        except (ValueError, PermissionError) as e:
            return str(e)

        try:
            action = adapter.write_file(
                project, file_path, content, commit_message, ref, overwrite
            )
        except Exception as e:
            return f"Write failed: {e}"

        if action is None:
            return (
                f"File `{file_path}` already exists in `{project}`. "
                f"Set overwrite=true to update it."
            )

        file_url = adapter.file_url(project, file_path, ref)
        log.info(
            f"Operator action: GIT_WRITE connection={connection} "
            f"provider={conn['provider']} project={project} path={file_path}"
        )
        return f"✅ File {action}: {file_url}"
        log.warning(f"Operator action: REPO_REMOVE name={name}")
        return f"✅ Connection '{name}' removed."

    @mcp.tool()
    def repo_test(name: str) -> str:
        """[Git] Verify a registered connection works by calling the provider API."""
        try:
            conn = _get_connection(name)
        except ValueError as e:
            return str(e)

        try:
            adapter = _adapter(conn)
            user = adapter.test()
            return (
                f"✅ Connection '{name}' is working.\n"
                f"- Provider: {conn['provider']}\n"
                f"- Instance: {conn['base_url']}\n"
                f"- Authenticated as: {user.get('username')} ({user.get('name')})\n"
                f"- Access level: {conn['access_level']}"
            )
        except Exception as e:
            return f"❌ Connection '{name}' failed: {e}"

    # -----------------------------------------------------------------------
    # READ TOOLS
    # -----------------------------------------------------------------------

    @mcp.tool()
    def git_list_repos(
        connection: str,
        search: str = "",
        owned: bool = True,
    ) -> str:
        """[Git] List repositories accessible via a named connection.

        Args:
          connection: Name of a registered connection (see repo_list)
          search:     Optional name filter
          owned:      If true, only show repos owned by the token's user
        """
        try:
            conn = _get_connection(connection)
        except ValueError as e:
            return str(e)

        try:
            repos = _adapter(conn).list_repos(search=search, owned=owned)
        except Exception as e:
            return f"API error: {e}"

        if not repos:
            return f"No repositories found via connection '{connection}'."

        lines = [f"## Repositories via '{connection}' [{conn['provider']}]"]
        for r in repos:
            lines.append(
                f"- `{r['path']}` — {r['description'] or 'no description'}  "
                f"(branch={r['default_branch']})"
            )
        return "\n".join(lines)

    @mcp.tool()
    def git_ingest_repo(
        connection: str,
        project: str,
        product: str,
        version: str,
        scope: str = "general",
        path: str = "",
        ref: str = "main",
        file_extension: str = ".md",
    ) -> str:
        """[Git] Walk a repository and ingest all matching files as reference memory.
        Idempotent — safe to re-run after doc updates.

        Args:
          connection:     Name of a registered connection (see repo_list)
          project:        Repo path. GitLab/GitHub: 'group/repo'. Bitbucket: 'workspace/repo'
          product:        Reference memory product name, e.g. 'memory-steward'
          version:        Version label, e.g. '1.0'
          scope:          Memory scope, e.g. 'architecture', 'operations'
          path:           Sub-directory to restrict to, e.g. 'docs'
          ref:            Branch or tag, default 'main'
          file_extension: Only ingest files with this extension, default '.md'
        """
        try:
            conn = _get_connection(connection)
            adapter = _adapter(conn)
        except ValueError as e:
            return str(e)

        try:
            all_files = adapter.list_files(project, path=path, ref=ref)
        except Exception as e:
            return f"Repo tree fetch failed: {e}"

        target_files = [
            f for f in all_files
            if f.get("name", "").endswith(file_extension)
        ]

        if not target_files:
            return f"No {file_extension} files found in {project}/{path} @ {ref}."

        results, errors, total_chunks = [], [], 0

        for f in target_files:
            file_path = f["path"]
            source_url = adapter.file_url(project, file_path, ref)
            try:
                content = adapter.fetch_file(project, file_path, ref=ref)
                result = ingest_text_fn(
                    text=content,
                    product=product,
                    version=version,
                    scope=scope,
                    source_url=source_url,
                )
                match = re.search(r'\*\*(\d+) chunks\*\*', result)
                n = int(match.group(1)) if match else 0
                total_chunks += n
                results.append(f"  ✅ `{file_path}` → {n} chunks")
            except Exception as e:
                errors.append(f"  ❌ `{file_path}`: {e}")
            time.sleep(0.1)

        lines = [
            f"## Git Ingest: `{project}` @ {ref} via '{connection}' [{conn['provider']}]",
            f"- Files: {len(results) + len(errors)}  chunks: {total_chunks}  errors: {len(errors)}",
            "",
            "### Files",
        ] + results + (["", "### Errors"] + errors if errors else [])

        return "\n".join(lines)

    @mcp.tool()
    def git_ingest_file(
        connection: str,
        project: str,
        file_path: str,
        product: str,
        version: str,
        scope: str = "general",
        ref: str = "main",
    ) -> str:
        """[Git] Fetch and ingest a single file from a repository.

        Args:
          connection: Name of a registered connection (see repo_list)
          project:    Repo path, e.g. 'mygroup/memory-steward'
          file_path:  Path within repo, e.g. 'docs/01_overview.md'
          product:    Reference memory product name
          version:    Version label
          scope:      Memory scope
          ref:        Branch or tag
        """
        try:
            conn = _get_connection(connection)
            adapter = _adapter(conn)
        except ValueError as e:
            return str(e)

        source_url = adapter.file_url(project, file_path, ref)
        try:
            content = adapter.fetch_file(project, file_path, ref=ref)
        except Exception as e:
            return f"Failed to fetch `{file_path}` from `{project}`: {e}"

        return ingest_text_fn(
            text=content,
            product=product,
            version=version,
            scope=scope,
            source_url=source_url,
        )

    # -----------------------------------------------------------------------
    # WRITE TOOLS
    # -----------------------------------------------------------------------

    @mcp.tool()
    def git_write_file(
        connection: str,
        project: str,
        file_path: str,
        content: str,
        commit_message: str,
        ref: str = "main",
        overwrite: bool = False,
    ) -> str:
        """[Git] Write a file to a repository (create or update).
        Requires access_level='read-write' on the connection.

        Args:
          connection:     Name of a registered read-write connection
          project:        Repo path, e.g. 'mygroup/docs'
          file_path:      Target path, e.g. 'runbooks/my-runbook.md'
          content:        File content (plain text or markdown)
          commit_message: Git commit message
          ref:            Branch to commit to, default 'main'
          overwrite:      If false and file exists, returns error instead of updating
        """
        try:
            conn = _get_connection(connection)
            _require_write(conn)
            adapter = _adapter(conn)
        except (ValueError, PermissionError) as e:
            return str(e)

        try:
            action = adapter.write_file(
                project, file_path, content, commit_message, ref, overwrite
            )
        except Exception as e:
            return f"Write failed: {e}"

        if action is None:
            return (
                f"File `{file_path}` already exists in `{project}`. "
                f"Set overwrite=true to update it."
            )

        file_url = adapter.file_url(project, file_path, ref)
        log.info(
            f"Operator action: GIT_WRITE connection={connection} "
            f"provider={conn['provider']} project={project} path={file_path}"
        )
        return f"✅ File {action}: {file_url}"
