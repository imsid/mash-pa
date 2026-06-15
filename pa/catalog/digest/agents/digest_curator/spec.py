"""Digest Curator — the primary digest agent.

Curates fresh web content for the user's topics and produces Axios-style digests.
Runs freeform ("digest me X") in conversation, and is the agent the `run-digest`
workflow's pipeline mirrors. Web search/fetch are on; topic and history reads come
from the shared digest store. When the user has no topics yet it points them at
the `interview-user` workflow and can delegate edits to `digest-concierge`.
"""

from __future__ import annotations

from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.registry import ToolRegistry

from ...._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME
from ..._skills import CURATE_DIGEST_SKILL, skill
from ..._tools import (
    AppendDigestSectionTool,
    ReadDigestHistoryTool,
    ReadDigestsTool,
    ReadTopicsTool,
    StartDigestRunTool,
)

DIGEST_CURATOR_AGENT_ID = "digest-curator"
DIGEST_CONCIERGE_AGENT_ID = "digest-concierge"

_PROMPT = f"""You are Digest Curator in {APP_NAME}: you turn fresh web content
into an Axios-style ("Smart Brevity") digest.

The curation pipeline is the `{CURATE_DIGEST_SKILL}` skill — load it and follow it
for every digest, whether the user asks for a freeform topic or their saved ones.

Working rules:
- Curate trusted `sources` first and fall back to open web search, tagging
  fallback items. Extract real content with `web_fetch`, never headline from
  snippets alone. Skip already-seen items via `read_digest_history`. Cite every
  claim with a link; never invent sources or facts.
- Build the digest one section at a time: `start_digest_run` once, then write and
  record each card with `append_digest_section` (one card per turn) so no single
  response has to emit the whole digest. This also lets the user view/search it
  later and lets the next run skip what was seen.
- Your access is the public web only: no paywalled or login-gated pages, no
  personal accounts, and you publish nothing. You are a curated sample, not a
  breaking-news wire.

If the user has no saved topics (use `read_topics` / `read_digests` to check),
tell them to run `/workflow run interview-user` to set up interests. When they
want to add, edit, or remove topics or bundles, delegate to the
`{DIGEST_CONCIERGE_AGENT_ID}` subagent if it is available, then confirm back.
"""


class DigestCuratorSpec(AgentSpec):
    """Primary digest agent with web search and the curate-digest skill."""

    def get_agent_id(self) -> str:
        return DIGEST_CURATOR_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(ReadTopicsTool())
        tools.register(ReadDigestsTool())
        tools.register(ReadDigestHistoryTool())
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
            app_id=DIGEST_CURATOR_AGENT_ID,
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
            app_id=DIGEST_CURATOR_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=True,
            max_steps=30,
            # Digests span multiple topics; the default 4096 truncates a long
            # digest, and the runtime then continues the turn via an assistant
            # prefill the API rejects. Give it room to finish in one turn.
            max_tokens=16000,
            temperature=0.3,
        )


def create_spec(*, workspace_root: str) -> DigestCuratorSpec:
    del workspace_root  # personal agents do not operate on a code workspace
    return DigestCuratorSpec()


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="Digest Curator",
        description=(
            "Curates fresh web content for your topics into Axios-style digests "
            "with highlights and key takeaways. Public web only, every claim "
            "linked; runs freeform or over your saved topics."
        ),
        capabilities=[
            "web research digests",
            "axios-style smart brevity summaries",
            "trusted-source curation with open-web fallback",
            "skip already-seen items",
        ],
        usage_guidance=(
            "Use to build a digest on any topic, or generate your saved digest. "
            "Delegates interest edits to digest-concierge; needs MASH_DATABASE_URL "
            "and a web search provider (PARALLEL_API_KEY)."
        ),
    )
