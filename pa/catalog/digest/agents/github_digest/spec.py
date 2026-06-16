"""GitHub Digest — the GitHub-world snapshot workflow agent.

A workflow-only agent and a sibling of `run-digest`: the `github-digest` workflow
runs it to gather the user's GitHub world (review-requested PRs, their open PRs,
assigned issues, recent repo activity) through the GitHub MCP server with a
read-only allowlist, and write it in the digest format — a run plus sections — so
it lands in the same digest history as every other digest.

Unlike topic/RSS digests it is a snapshot, not a feed: it does not skip already-seen
items (a still-open PR must reappear every run). When `GITHUB_MCP_PAT` is unset the
GitHub tools are absent and it writes a one-card run explaining how to configure it.
"""

from __future__ import annotations

from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.mcp.types import MCPServerConfig
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.registry import ToolRegistry
from mash.workflows import TaskSpec, WorkflowSpec, WorkflowTaskMessageSpec

from ...._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME
from ..._github import github_mcp_config
from ..._skills import GITHUB_DIGEST_SKILL, skill
from ...tools import AppendDigestSectionTool, StartDigestRunTool

GITHUB_DIGEST_AGENT_ID = "github-digest"
GITHUB_DIGEST_WORKFLOW_ID = "github-digest"
GITHUB_DIGEST_TASK_ID = "github"

_PROMPT = f"""You are the GitHub digest runner in {APP_NAME}. Produce one snapshot of
the user's GitHub world and write it in the digest format.

Run the `{GITHUB_DIGEST_SKILL}` skill. Start with `get_me`, then gather (in parallel
where you can): pull requests awaiting their review
(`search_pull_requests review-requested:@me state:open`), their own open PRs
(`author:@me state:open`), assigned issues (`search_issues assignee:@me state:open`),
and, only if the user named repositories in `workflow_input`, recent activity for
those repos. Open one run titled "Your GitHub world" with `start_digest_run`, then
write one section per group with `append_digest_section` (most actionable first),
each with `topic_id` "" and `seen` {{}} — this is a snapshot, never skip already-seen
items. Your GitHub access is read-only.

If the GitHub tools are unavailable, this deployment has no GitHub connection: write
a one-card run explaining that `GITHUB_MCP_PAT` (a GitHub personal access token) must
be set in the deployment's `.env` and the host restarted. Do not ask the user
questions.
"""


class GithubDigestSpec(AgentSpec):
    """Workflow agent that snapshots the GitHub world as a digest run."""

    def get_agent_id(self) -> str:
        return GITHUB_DIGEST_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(StartDigestRunTool())
        tools.register(AppendDigestSectionTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        skills = SkillRegistry()
        skills.register(
            skill(
                GITHUB_DIGEST_SKILL,
                "Gather the GitHub world via MCP and write it as a snapshot digest.",
            )
        )
        return skills

    def build_mcp_servers(self) -> list[MCPServerConfig]:
        config = github_mcp_config()
        return [config] if config else []

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=GITHUB_DIGEST_AGENT_ID,
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
            app_id=GITHUB_DIGEST_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=True,
            max_steps=20,
            temperature=0.2,
        )


def create_spec() -> GithubDigestSpec:
    return GithubDigestSpec()


def build_workflow_spec() -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=GITHUB_DIGEST_WORKFLOW_ID,
        tasks=[TaskSpec(task_id=GITHUB_DIGEST_TASK_ID, agent_spec=create_spec())],
        task_message=WorkflowTaskMessageSpec(skill_name=GITHUB_DIGEST_SKILL),
    )


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="GitHub Digest",
        description=(
            "Snapshots your GitHub world — PRs awaiting your review, your open PRs, "
            "assigned issues, and recent repo activity — as a digest. Read-only "
            "GitHub access via MCP."
        ),
        capabilities=["github snapshot digest"],
        usage_guidance=(
            "Run via `/workflow run github-digest`. Requires GITHUB_MCP_PAT on the "
            "deployment; read-only."
        ),
    )
