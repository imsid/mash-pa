"""Tools over named digests (saved collections), plus the interest reset."""

from __future__ import annotations

from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _store
from ._base import _BaseTool, _ok, _optional_digest_id


class ReadDigestsTool(_BaseTool):
    """List digests, or resolve one digest to its topics and feeds."""

    name = "read_digests"
    description = (
        "List the user's digests, or resolve one when `digest_id` is provided to "
        "its ordered `topics` (topic rows) and `rss_feeds` (followed "
        "creators/podcasts)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "integer",
                "description": "Digest id to resolve. Omit to list digests.",
            }
        },
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        try:
            digest_id = _optional_digest_id((args or {}).get("digest_id"))
        except ValueError as exc:
            return ToolResult.error(str(exc))
        if digest_id is not None:
            return _ok(
                {
                    "topics": await _store.resolve_digest_topics(digest_id),
                    "rss_feeds": await _store.resolve_digest_rss_feeds(digest_id),
                }
            )
        return _ok(await _store.list_digests())


class WriteDigestTool(_BaseTool):
    """Create or update a user-configured digest."""

    name = "write_digest"
    description = (
        "Create or update a digest: a human label, an ordered list of topic ids, "
        "and optionally `rss_feed_ids` for followed creators/podcasts it "
        "includes. Omit `digest_id` to create a new digest (its id is generated "
        "and returned); pass `digest_id` to update an existing one."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_id": {
                "type": "integer",
                "description": "Existing digest id to update; omit to create.",
            },
            "label": {"type": "string"},
            "topic_ids": {"type": "array", "items": {"type": "string"}},
            "rss_feed_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Followed feed ids; omit or [] if none.",
            },
        },
        "required": ["label", "topic_ids"],
        "additionalProperties": False,
    }

    # User-configured digests (set up in conversation / onboarding) carry this
    # source; freeform snapshot digests carry their generating workflow's id.
    _SOURCE = "user"

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        label = str(args.get("label") or "").strip()
        topic_ids = args.get("topic_ids")
        rss_feed_ids = args.get("rss_feed_ids") or []
        if not label:
            return ToolResult.error("`label` is required.")
        if not isinstance(topic_ids, list):
            return ToolResult.error("`topic_ids` must be an array.")
        if not isinstance(rss_feed_ids, list):
            return ToolResult.error("`rss_feed_ids` must be an array.")
        topic_ids = [str(t) for t in topic_ids]
        rss_feed_ids = [str(f) for f in rss_feed_ids]

        try:
            digest_id = _optional_digest_id(args.get("digest_id"))
        except ValueError as exc:
            return ToolResult.error(str(exc))
        if digest_id is not None:
            if not await _store.update_digest(
                digest_id, label, topic_ids, rss_feed_ids
            ):
                return ToolResult.error(f"No digest with id {digest_id}.")
        else:
            digest_id = await _store.create_digest(
                label, self._SOURCE, topic_ids, rss_feed_ids
            )
        return _ok(
            {
                "digest_id": digest_id,
                "topics": len(topic_ids),
                "rss_feeds": len(rss_feed_ids),
            }
        )


class ClearInterestsTool(_BaseTool):
    """Reset saved topics and feeds, and drop never-run digest definitions."""

    name = "clear_interests"
    description = (
        "Reset the user's interests before re-onboarding: delete all saved topics "
        "and followed feeds, and drop digest definitions that were never run. "
        "Digests with past runs are kept so their history stays viewable."
    )

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        del args  # no inputs
        await _store.clear_all()
        return _ok({"cleared": True})
