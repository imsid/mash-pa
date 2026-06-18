"""Tools over digest runs and their sections (output + skip-seen)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _store
from ._base import _BaseTool, _ok


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
    parallel_safe = False
    description = (
        "Open a new digest run and get back its `run_id`. Call this once before "
        "writing sections. Pass a `title` and an optional `lead` (the '1 big "
        "thing'). For a saved digest include its `digest_id`; omit it for a "
        "freeform digest."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "string",
                "description": "Digest id; omit for a freeform digest.",
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
    parallel_safe = False
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
