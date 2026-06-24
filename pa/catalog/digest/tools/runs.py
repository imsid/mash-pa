"""Tools over digest runs and their sections (output + skip-seen)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _store
from ._base import _BaseTool, _ok, _optional_digest_id


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
        "Open a new digest run and get back its `digest_id` and `run_id`. Call "
        "this once before writing sections. Pass a `title` and an optional `lead` "
        "(the '1 big thing'). Provide exactly one of: `digest_id` to attach the "
        "run to an existing digest (a configured digest, or one named in the "
        "workflow input), or `workflow` (this workflow/agent's id) to create a "
        "freeform digest on the fly for a one-off snapshot."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "integer",
                "description": "Existing digest id to attach this run to.",
            },
            "workflow": {
                "type": "string",
                "description": (
                    "This workflow/agent's id; creates a freeform digest. Use "
                    "instead of `digest_id` for a one-off snapshot."
                ),
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
        # A missing/zero/empty `digest_id` (a model's 0 placeholder) means "not
        # provided" and routes to the freeform `workflow` path.
        try:
            digest_id = _optional_digest_id(args.get("digest_id"))
        except ValueError as exc:
            return ToolResult.error(str(exc))
        workflow = str(args.get("workflow") or "").strip()
        # An explicit existing digest wins; otherwise open a freeform digest for
        # the named workflow.
        if digest_id is not None:
            workflow = ""
        elif not workflow:
            return ToolResult.error(
                "Provide a `digest_id` (an existing digest) or a `workflow` "
                "(to open a freeform digest)."
            )
        try:
            result = await _store.start_digest_run(
                title,
                digest_id=digest_id,
                workflow=workflow or None,
                lead=str(args.get("lead") or ""),
            )
        except ValueError as exc:
            return ToolResult.error(str(exc))
        return _ok(result)


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
