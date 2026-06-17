"""Digest Concierge — conversational interest management.

Helps the user shape what their digests cover: add, edit, remove topics, and
compose or rename named digests, all over the shared digest store. The
full guided first-run interview lives in the `interview-user` workflow; this agent
handles the lighter, conversational edits and shows the user what they have saved.
"""

from __future__ import annotations

from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.registry import ToolRegistry

from ...._base import APP_NAME
from ...._llm import build_gemma_llm
from ..._skills import ONBOARD_TOPICS_SKILL, skill
from ...tools import (
    ClearInterestsTool,
    ReadDigestsTool,
    ReadRssFeedsTool,
    ReadTopicsTool,
    SubscribeRssFeedTool,
    UnsubscribeRssFeedTool,
    WriteDigestTool,
    WriteTopicsTool,
)

DIGEST_CONCIERGE_AGENT_ID = "digest-concierge"

_PROMPT = f"""You are Digest Concierge in {APP_NAME}: you manage the user's digest
interests — the topics they follow and the named digests that group them.

A digest is a saved, named collection of topics and followed feeds (its
`topic_ids` and `rss_feed_ids`); generating one produces a digest run the user
reads. You manage the collections, not the generated runs.

What you do:
- Show saved topics, followed feeds, and digests with `read_topics`,
  `read_rss_feeds`, and `read_digests`.
- Add or edit topics with `write_topics`. A topic needs an id (short kebab-case
  slug), a label, an intent (a one-line search brief), trusted `sources` (domain
  list, or [] for open-web), `recency_days`, and `max_items`. Infer sensible
  values from what the user says rather than interrogating every field.
- Follow a YouTube creator or a podcast with `subscribe_rss_feed` (`kind` plus a
  `source`: a @handle/channel URL/name or raw UC… id for youtube_channel, a show
  name or RSS URL for podcast). Stop with `unsubscribe_rss_feed`. If a show can't
  be resolved, say plainly it may be a Spotify exclusive with no public RSS feed,
  which cannot be followed.
- Create or update digests with `write_digest` (id, label, ordered topic ids,
  and optional `rss_feed_ids` for followed creators/podcasts).
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
        tools.register(ReadRssFeedsTool())
        tools.register(WriteTopicsTool())
        tools.register(WriteDigestTool())
        tools.register(SubscribeRssFeedTool())
        tools.register(UnsubscribeRssFeedTool())
        tools.register(ClearInterestsTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        skills = SkillRegistry()
        skills.register(
            skill(
                ONBOARD_TOPICS_SKILL,
                "Conventions for normalizing interests into topics and digests.",
            )
        )
        return skills

    def build_llm(self) -> LLMProvider:
        # Bounded, low-volume interest management — runs on Gemma over OpenRouter
        # to keep frontier spend for the web-research agents. Routing is pinned to
        # tool-call-capable backends so the read/write tools round-trip reliably.
        return build_gemma_llm(DIGEST_CONCIERGE_AGENT_ID)

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
            "Manages your digest interests: add, edit, and remove topics, follow "
            "YouTube creators and podcasts, and compose named digests. "
            "Conversational edits over your saved interests."
        ),
        capabilities=[
            "manage digest topics",
            "follow youtube creators and podcasts",
            "compose named digests",
            "view saved interests",
            "reset interests",
        ],
        usage_guidance=(
            "Use to view or change what your digests cover. For a full guided "
            "first-time setup run `/workflow run interview-user`. Needs "
            "MASH_DATABASE_URL."
        ),
    )
