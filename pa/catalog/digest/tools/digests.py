"""Tools over named digests (saved collections), plus the interest reset."""

from __future__ import annotations

from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _store
from ._base import _BaseTool, _ok


class ReadDigestsTool(_BaseTool):
    """List digests, or resolve one digest to its topics and feeds."""

    name = "read_digests"
    description = (
        "List the user's named digests, or resolve one when `digest_id` is "
        "provided to its ordered `topics` (topic rows) and `rss_feeds` "
        "(followed creators/podcasts)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "string",
                "description": "Digest id to resolve. Omit to list digests.",
            }
        },
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        digest_id = str((args or {}).get("digest_id") or "").strip()
        if digest_id:
            return _ok(
                {
                    "topics": await _store.resolve_digest_topics(digest_id),
                    "rss_feeds": await _store.resolve_digest_rss_feeds(digest_id),
                }
            )
        return _ok(await _store.list_digests())


class WriteDigestTool(_BaseTool):
    """Create or update a named digest."""

    name = "write_digest"
    description = (
        "Create or update a named digest: an id, a human label, an ordered "
        "list of topic ids, and optionally `rss_feed_ids` for followed "
        "creators/podcasts it includes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {"type": "string"},
            "label": {"type": "string"},
            "topic_ids": {"type": "array", "items": {"type": "string"}},
            "rss_feed_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Followed feed ids; omit or [] if none.",
            },
        },
        "required": ["digest_id", "label", "topic_ids"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        digest_id = str(args.get("digest_id") or "").strip()
        label = str(args.get("label") or "").strip()
        topic_ids = args.get("topic_ids")
        rss_feed_ids = args.get("rss_feed_ids") or []
        if not digest_id or not label:
            return ToolResult.error("`digest_id` and `label` are required.")
        if not isinstance(topic_ids, list):
            return ToolResult.error("`topic_ids` must be an array.")
        if not isinstance(rss_feed_ids, list):
            return ToolResult.error("`rss_feed_ids` must be an array.")
        await _store.upsert_digest(
            digest_id,
            label,
            [str(t) for t in topic_ids],
            [str(f) for f in rss_feed_ids],
        )
        return _ok(
            {
                "digest_id": digest_id,
                "topics": len(topic_ids),
                "rss_feeds": len(rss_feed_ids),
            }
        )


class ClearInterestsTool(_BaseTool):
    """Delete all saved topics, followed feeds, and digests (reset)."""

    name = "clear_interests"
    description = (
        "Delete all saved topics, followed feeds, and digests. Use this when the "
        "user resets their interests before re-onboarding. Past digest runs are "
        "kept."
    )

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        del args  # no inputs
        await _store.clear_all()
        return _ok({"cleared": True})
