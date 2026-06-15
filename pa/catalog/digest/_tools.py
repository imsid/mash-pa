"""Agent tools over the digest store.

Thin wrappers around `_store`: each returns a `ToolResult` and follows the same
shape as `finance_watch`'s `ReadLedgerTool` (`name`, `description`, `parameters`,
async `execute`, `to_llm_format`). Read tools are shared by every digest agent;
write/clear tools are registered only where they belong (the concierge and the
interview workflow).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from mash.tools.base import ToolResult

from . import _store


def _ok(payload: Any) -> ToolResult:
    return ToolResult.success(json.dumps(payload, ensure_ascii=False, default=str))


class _BaseTool:
    """Shared tool surface: name, description, schema, and LLM formatting."""

    requires_approval = False
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    def to_llm_format(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ReadTopicsTool(_BaseTool):
    """List the user's saved digest topics."""

    name = "read_topics"
    description = (
        "List the user's saved digest topics (id, label, intent, trusted "
        "sources, recency_days, max_items)."
    )

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        del args  # no inputs
        return _ok(await _store.list_topics())


class ReadDigestsTool(_BaseTool):
    """List digest bundles, or resolve one bundle to its topics."""

    name = "read_digests"
    description = (
        "List the user's named digest bundles, or resolve one bundle to its "
        "ordered topic rows when `digest_id` is provided."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "string",
                "description": "Bundle id to resolve to its topics. Omit to list bundles.",
            }
        },
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        digest_id = str((args or {}).get("digest_id") or "").strip()
        if digest_id:
            return _ok(await _store.resolve_digest_topics(digest_id))
        return _ok(await _store.list_digests())


class WriteTopicsTool(_BaseTool):
    """Insert or update digest topics by id."""

    name = "write_topics"
    description = (
        "Insert or update digest topics by id. Each topic needs id, label, "
        "intent (the search brief), sources (trusted-domain allowlist; [] for "
        "open-web topics), recency_days, and max_items."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "label": {"type": "string"},
                        "intent": {"type": "string"},
                        "sources": {"type": "array", "items": {"type": "string"}},
                        "recency_days": {"type": "integer"},
                        "max_items": {"type": "integer"},
                    },
                    "required": [
                        "id",
                        "label",
                        "intent",
                        "sources",
                        "recency_days",
                        "max_items",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["topics"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        topics = (args or {}).get("topics")
        if not isinstance(topics, list) or not topics:
            return ToolResult.error("`topics` must be a non-empty array.")
        try:
            await _store.upsert_topics(topics)
        except (KeyError, ValueError, TypeError) as exc:
            return ToolResult.error(f"Invalid topic payload: {exc}")
        return _ok({"written": len(topics)})


class WriteDigestTool(_BaseTool):
    """Create or update a named digest bundle."""

    name = "write_digest"
    description = (
        "Create or update a named digest bundle: an id, a human label, and an "
        "ordered list of topic ids it includes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {"type": "string"},
            "label": {"type": "string"},
            "topic_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["digest_id", "label", "topic_ids"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        digest_id = str(args.get("digest_id") or "").strip()
        label = str(args.get("label") or "").strip()
        topic_ids = args.get("topic_ids")
        if not digest_id or not label:
            return ToolResult.error("`digest_id` and `label` are required.")
        if not isinstance(topic_ids, list):
            return ToolResult.error("`topic_ids` must be an array.")
        await _store.upsert_digest(digest_id, label, [str(t) for t in topic_ids])
        return _ok({"digest_id": digest_id, "topics": len(topic_ids)})


class ClearInterestsTool(_BaseTool):
    """Delete all saved topics and bundles (reset)."""

    name = "clear_interests"
    description = (
        "Delete all saved topics and digest bundles. Use this when the user "
        "resets their interests before re-onboarding. Past digest runs are kept."
    )

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        del args  # no inputs
        await _store.clear_all()
        return _ok({"cleared": True})


class ReadDigestHistoryTool(_BaseTool):
    """Return already-seen item keys for a topic within a recency window."""

    name = "read_digest_history"
    description = (
        "Return URLs and titles already surfaced for a topic within the last "
        "`recency_days` days, so already-seen items can be skipped."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic_id": {"type": "string"},
            "recency_days": {"type": "integer"},
        },
        "required": ["topic_id", "recency_days"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        topic_id = str(args.get("topic_id") or "").strip()
        if not topic_id:
            return ToolResult.error("`topic_id` is required.")
        raw_recency = args.get("recency_days")
        if raw_recency is None:
            return ToolResult.error("`recency_days` must be an integer.")
        try:
            recency_days = int(raw_recency)
        except (TypeError, ValueError):
            return ToolResult.error("`recency_days` must be an integer.")
        since = datetime.now(timezone.utc) - timedelta(days=recency_days)
        keys = await _store.recent_item_keys(topic_id, since)
        return _ok({"seen": sorted(keys)})


class StartDigestRunTool(_BaseTool):
    """Open a digest run before appending its sections."""

    name = "start_digest_run"
    description = (
        "Open a new digest run and get back its `run_id`. Call this once before "
        "writing sections. Pass a `title` and an optional `lead` (the '1 big "
        "thing'). For a saved bundle include its `digest_id`; omit it for a "
        "freeform digest."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "string",
                "description": "Bundle id; omit for a freeform digest.",
            },
            "title": {"type": "string"},
            "lead": {
                "type": "string",
                "description": "The '1 big thing' lead; optional.",
            },
        },
        "required": ["title"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        title = str(args.get("title") or "").strip()
        if not title:
            return ToolResult.error("`title` is required.")
        run_id = await _store.start_digest_run(
            str(args.get("digest_id") or ""),
            title,
            str(args.get("lead") or ""),
        )
        return _ok({"run_id": run_id})


class AppendDigestSectionTool(_BaseTool):
    """Append one digest section (card) to an open run."""

    name = "append_digest_section"
    description = (
        "Append one section (card) to a digest run, written one at a time so no "
        "single response has to emit the whole digest. Pass the `run_id` from "
        "start_digest_run, the section's `topic_id` (empty for a freeform "
        "digest), a `heading`, the section's rendered markdown as `content`, and "
        "`seen` (the urls/titles surfaced in this section, for skip-seen)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "run_id": {"type": "integer"},
            "topic_id": {"type": "string"},
            "heading": {"type": "string"},
            "content": {"type": "string"},
            "seen": {
                "type": "object",
                "description": 'The items shown: {"urls": [...], "titles": [...]}.',
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "titles": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": False,
            },
        },
        "required": ["run_id", "heading", "content", "seen"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        raw_run_id = args.get("run_id")
        if raw_run_id is None:
            return ToolResult.error("`run_id` is required.")
        try:
            run_id = int(raw_run_id)
        except (TypeError, ValueError):
            return ToolResult.error("`run_id` must be an integer.")
        heading = str(args.get("heading") or "").strip()
        content = str(args.get("content") or "").strip()
        seen = args.get("seen")
        if not heading or not content:
            return ToolResult.error("`heading` and `content` are required.")
        if not isinstance(seen, dict):
            return ToolResult.error("`seen` must be an object.")
        section_id = await _store.append_digest_section(
            run_id,
            str(args.get("topic_id") or ""),
            heading,
            content,
            seen,
        )
        return _ok({"section_id": section_id})
