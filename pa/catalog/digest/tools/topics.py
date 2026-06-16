"""Tools over the user's saved digest topics."""

from __future__ import annotations

from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _store
from ._base import _BaseTool, _ok


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
