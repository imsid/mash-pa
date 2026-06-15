"""Digest Concierge — conversational interest management.

Helps the user shape what their digests cover: add, edit, remove topics, and
compose or rename named digest bundles, all over the shared digest store. The
full guided first-run interview lives in the `interview-user` workflow; this agent
handles the lighter, conversational edits and shows the user what they have saved.
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
from ..._skills import ONBOARD_TOPICS_SKILL, skill
from ..._tools import (
    ClearInterestsTool,
    ReadDigestsTool,
    ReadTopicsTool,
    WriteDigestTool,
    WriteTopicsTool,
)

DIGEST_CONCIERGE_AGENT_ID = "digest-concierge"

_PROMPT = f"""You are Digest Concierge in {APP_NAME}: you manage the user's digest
interests — the topics they follow and the named bundles that group them.

What you do:
- Show saved topics and bundles with `read_topics` / `read_digests`.
- Add or edit topics with `write_topics`. A topic needs an id (short kebab-case
  slug), a label, an intent (a one-line search brief), trusted `sources` (domain
  list, or [] for open-web), `recency_days`, and `max_items`. Infer sensible
  values from what the user says rather than interrogating every field.
- Create or update bundles with `write_digest` (id, label, ordered topic ids).
- Use `clear_interests` only when the user explicitly asks to wipe everything.

The normalization rules you follow are in the `{ONBOARD_TOPICS_SKILL}` skill; load
it when you need the conventions. For a full guided first-time setup, tell the
user to run `/workflow run interview-user`. Confirm changes back in a short list.
"""


class DigestConciergeSpec(AgentSpec):
    """Conversational interest manager over the digest store."""

    def get_agent_id(self) -> str:
        return DIGEST_CONCIERGE_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(ReadTopicsTool())
        tools.register(ReadDigestsTool())
        tools.register(WriteTopicsTool())
        tools.register(WriteDigestTool())
        tools.register(ClearInterestsTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        skills = SkillRegistry()
        skills.register(
            skill(
                ONBOARD_TOPICS_SKILL,
                "Conventions for normalizing interests into topics and bundles.",
            )
        )
        return skills

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=DIGEST_CONCIERGE_AGENT_ID,
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
            app_id=DIGEST_CONCIERGE_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=True,
            max_steps=12,
            temperature=0.2,
        )


def create_spec(*, workspace_root: str) -> DigestConciergeSpec:
    del workspace_root  # personal agents do not operate on a code workspace
    return DigestConciergeSpec()


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="Digest Concierge",
        description=(
            "Manages your digest interests: add, edit, and remove topics, and "
            "compose named digest bundles. Conversational edits over your saved "
            "interests."
        ),
        capabilities=[
            "manage digest topics",
            "compose named digest bundles",
            "view saved interests",
            "reset interests",
        ],
        usage_guidance=(
            "Use to view or change what your digests cover. For a full guided "
            "first-time setup run `/workflow run interview-user`. Needs "
            "MASH_DATABASE_URL."
        ),
    )
