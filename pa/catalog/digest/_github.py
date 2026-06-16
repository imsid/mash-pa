"""GitHub MCP connection for the github-digest workflow.

The user's GitHub world is read through the GitHub MCP server with a read-only
tool allowlist. Configuration is per-deployment: one `GITHUB_MCP_PAT`, one GitHub
identity — there is nothing user-managed here (unlike topics or RSS feeds), so
this module only builds the connection. Keys are read at call time via
`os.getenv`, mirroring `_rss.py`; an unconfigured deployment yields `None` and the
workflow explains how to light itself up.
"""

from __future__ import annotations

import os

from mash.mcp.types import MCPServerConfig

GITHUB_MCP_CONNECTION_NAME = "github"
DEFAULT_GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"

# Verified against the live GitHub MCP server; all read-only.
GITHUB_TOOL_ALLOWLIST = [
    "get_me",
    "list_commits",
    "list_issues",
    "list_pull_requests",
    "issue_read",
    "pull_request_read",
    "search_issues",
    "search_pull_requests",
]


def github_mcp_config() -> MCPServerConfig | None:
    """The read-only GitHub MCP connection, or None when unconfigured."""
    url = os.getenv("GITHUB_MCP_URL") or DEFAULT_GITHUB_MCP_URL
    pat = os.getenv("GITHUB_MCP_PAT")
    if not url or not pat:
        return None
    return MCPServerConfig(
        name=GITHUB_MCP_CONNECTION_NAME,
        url=url,
        description="GitHub MCP server (read-only allowlist) for the GitHub digest",
        headers={"Authorization": f"Bearer {pat}"},
        allowed_tools=list(GITHUB_TOOL_ALLOWLIST),
    )
