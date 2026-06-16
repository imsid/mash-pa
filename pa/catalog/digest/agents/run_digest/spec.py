"""Run Digest — the deterministic digest workflow agent.

A workflow-only agent: the `run-digest` workflow runs it to generate a digest run
from a saved digest (default `default`, or `digest_id` from the workflow input). It
runs the same shared `curate-digest` pipeline the interactive curator uses. No
interactive tools — if the digest has no topics it reports that and stops.
"""

from __future__ import annotations

from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.registry import ToolRegistry
from mash.workflows import TaskSpec, WorkflowSpec, WorkflowTaskMessageSpec

from ...._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME
from ..._skills import CURATE_DIGEST_SKILL, skill
from ...tools import (
    AppendDigestSectionTool,
    ReadDigestHistoryTool,
    ReadDigestsTool,
    ReadNewRssItemsTool,
    ReadRssFeedsTool,
    ReadTopicsTool,
    StartDigestRunTool,
)

RUN_DIGEST_AGENT_ID = "run-digest"
RUN_DIGEST_WORKFLOW_ID = "run-digest"
RUN_DIGEST_TASK_ID = "curate"

_PROMPT = f"""You are the digest runner in {APP_NAME}. Generate one Axios-style
digest over the user's saved topics.

Run the `{CURATE_DIGEST_SKILL}` skill. Read `digest_id` from `workflow_input`
(default `default`), resolve it with `read_digests` (returns `topics` and `rss_feeds`),
and process each: for topics, curate (trusted
sources first, open-web fallback), extract with `web_fetch`, skip already-seen via
`read_digest_history`; for followed feeds, call `read_new_rss_items` instead of
web-searching. Write the Axios digest one section at a time — `start_digest_run`
once, then one `append_digest_section` per topic or feed so no single response has
to emit the whole digest. If the digest resolves to nothing, reply that there is
nothing yet and that the user should run `/workflow run interview-user`. Do not ask
the user questions.
"""


class RunDigestSpec(AgentSpec):
    """Workflow agent that generates a digest run from a saved digest."""

    def get_agent_id(self) -> str:
        return RUN_DIGEST_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(ReadTopicsTool())
        tools.register(ReadDigestsTool())
        tools.register(ReadRssFeedsTool())
        tools.register(ReadDigestHistoryTool())
        tools.register(ReadNewRssItemsTool())
        tools.register(StartDigestRunTool())
        tools.register(AppendDigestSectionTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        skills = SkillRegistry()
        skills.register(
            skill(
                CURATE_DIGEST_SKILL,
                "Curate fresh web content and produce an Axios-style digest.",
            )
        )
        return skills

    def enable_web_search_tools(self) -> bool:
        return True

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=RUN_DIGEST_AGENT_ID,
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
            app_id=RUN_DIGEST_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=True,
            max_steps=30,
            # Digests span multiple topics; the default 4096 truncates a long
            # digest, and the runtime then continues the turn via an assistant
            # prefill the API rejects. Give it room to finish in one turn.
            max_tokens=16000,
            temperature=0.3,
        )


def create_spec() -> RunDigestSpec:
    return RunDigestSpec()


def build_workflow_spec() -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=RUN_DIGEST_WORKFLOW_ID,
        tasks=[TaskSpec(task_id=RUN_DIGEST_TASK_ID, agent_spec=create_spec())],
        task_message=WorkflowTaskMessageSpec(skill_name=CURATE_DIGEST_SKILL),
    )


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="Run Digest",
        description="Generates an Axios-style digest over your saved topics.",
        capabilities=["scheduled digest generation"],
        usage_guidance="Run via `/workflow run run-digest`.",
    )
