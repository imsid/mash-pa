"""GH Brief — a personal agent over a cloud service via MCP.

Prepares a brief of your GitHub world: review-requested PRs, assigned
issues, and recent activity, through the GitHub MCP server with a read-only
tool allowlist. Registers even without credentials; unconfigured, it
explains how to light itself up. As the primary of the `assistant` host it
delegates personal-spending questions to the `finance-watch` subagent.
"""

from __future__ import annotations

import os
from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.mcp.types import MCPServerConfig
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.registry import ToolRegistry

from ..._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME

GH_BRIEF_AGENT_ID = "gh-brief"
FINANCE_WATCH_AGENT_ID = "finance-watch"
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


def _github_mcp_config() -> MCPServerConfig | None:
    url = os.getenv("GITHUB_MCP_URL") or DEFAULT_GITHUB_MCP_URL
    pat = os.getenv("GITHUB_MCP_PAT")
    if not url or not pat:
        return None
    return MCPServerConfig(
        name=GITHUB_MCP_CONNECTION_NAME,
        url=url,
        description="GitHub MCP server (read-only allowlist) for the GitHub brief",
        headers={"Authorization": f"Bearer {pat}"},
        allowed_tools=list(GITHUB_TOOL_ALLOWLIST),
    )


_PROMPT = f"""You are GH Brief in {APP_NAME}: a personal assistant whose
specialty is preparing a compact brief of the user's GitHub world.

How to work:
- Start with `get_me` to learn who the user is, then gather in parallel
  where possible: pull requests awaiting their review
  (`search_pull_requests` with `review-requested:@me state:open`), their own
  open pull requests (`author:@me state:open`), and issues assigned to them
  (`search_issues` with `assignee:@me state:open`).
- If the user names repositories, add recent activity for those:
  `list_commits`, `list_issues`, `list_pull_requests` since yesterday (or
  the window they ask for).
- Produce one compact markdown brief grouped by section (Needs your review /
  Your open PRs / Assigned issues / Repo activity), most actionable first.
  Include titles, repo names, and URLs. Say plainly when a section is empty.
- Your GitHub access is read-only; you cannot comment, merge, or write.

When the user asks about personal spending, transactions, charges, or
subscriptions, delegate to the `{FINANCE_WATCH_AGENT_ID}` subagent if it is
available, then return one synthesized answer.

If GitHub tools are unavailable, this deployment has no GitHub connection:
explain that `GITHUB_MCP_PAT` (a GitHub personal access token) must be set
in the deployment's `.env` and the host restarted.
"""


class GhBriefSpec(AgentSpec):
    """GitHub brief assistant over the MCP connection."""

    def get_agent_id(self) -> str:
        return GH_BRIEF_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        return ToolRegistry()

    def build_skills(self) -> SkillRegistry:
        return SkillRegistry()

    def build_mcp_servers(self) -> list[MCPServerConfig]:
        config = _github_mcp_config()
        return [config] if config else []

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=GH_BRIEF_AGENT_ID,
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
        )

    def build_system_prompt(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": _PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def build_agent_config(self) -> AgentConfig:
        return AgentConfig(
            app_id=GH_BRIEF_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=False,
            max_steps=20,
            temperature=0.2,
        )


def create_spec(*, workspace_root: str) -> GhBriefSpec:
    del workspace_root  # personal agents do not operate on a code workspace
    return GhBriefSpec()


def build_metadata() -> AgentMetadata:
    configured = _github_mcp_config() is not None
    return AgentMetadata(
        display_name="GH Brief",
        description=(
            "Prepares a compact brief of your GitHub world: PRs awaiting "
            "your review, your open PRs, assigned issues, and recent repo "
            "activity. Read-only GitHub access via MCP."
            + ("" if configured else " (Not configured: set GITHUB_MCP_PAT.)")
        ),
        capabilities=[
            "github brief",
            "review-requested pull requests",
            "assigned issues",
            "recent repo activity",
        ],
        usage_guidance=(
            "Use to catch up on GitHub: what needs review, what's assigned, "
            "what changed recently. Requires GITHUB_MCP_PAT on the "
            "deployment; read-only."
        ),
    )
