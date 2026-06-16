"""Tools for following YouTube creators and podcasts via RSS.

Subscribe resolves a human reference to a canonical feed once (`_rss.resolve_*`);
`read_new_rss_items` is the steady-state fetcher for saved feeds — pure RSS,
deduped in the tool. `fetch_rss_items` is the freeform analog: it resolves a
creator/podcast on the fly and returns its latest items without saving anything,
so a one-off "latest episodes of X" never needs a subscription or web search.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from mash.tools.base import ToolResult

from .. import _rss, _store
from ._base import _BaseTool, _ok

# Followed-feed sections are recorded under this namespace so their skip-seen
# history (via `recent_item_keys`) never collides with a topic of the same id.
RSS_SECTION_PREFIX = "rss:"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "feed"


class ReadRssFeedsTool(_BaseTool):
    """List the user's followed YouTube creators and podcasts."""

    name = "read_rss_feeds"
    description = (
        "List the user's followed RSS feeds (id, kind, label, feed_url, "
        "recency_days, max_items). Covers YouTube creators and podcasts."
    )

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        del args  # no inputs
        return _ok(await _store.list_rss_feeds())


class SubscribeRssFeedTool(_BaseTool):
    """Resolve a creator/podcast to its RSS feed and follow it."""

    name = "subscribe_rss_feed"
    description = (
        "Follow a YouTube creator or a podcast. Give the `kind` and a `source` "
        "— for youtube_channel a @handle, channel name, channel URL, or raw UC… "
        "id; for podcast a show name or RSS feed URL. The source is resolved "
        "once to a canonical feed (YouTube Data API / Podcast Index) and cached; "
        "later polling is pure RSS. Optionally set `label`, `recency_days` "
        "(default 7), and `max_items` (default 5). Spotify-exclusive shows have "
        "no public RSS and cannot be followed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [_rss.YOUTUBE_KIND, _rss.PODCAST_KIND],
            },
            "source": {
                "type": "string",
                "description": "Handle/URL/name (youtube) or show name/RSS URL (podcast).",
            },
            "label": {
                "type": "string",
                "description": "Display name; inferred from the source if omitted.",
            },
            "recency_days": {"type": "integer"},
            "max_items": {"type": "integer"},
        },
        "required": ["kind", "source"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        kind = str(args.get("kind") or "").strip()
        source = str(args.get("source") or "").strip()
        if kind not in (_rss.YOUTUBE_KIND, _rss.PODCAST_KIND):
            return ToolResult.error(
                f"`kind` must be '{_rss.YOUTUBE_KIND}' or '{_rss.PODCAST_KIND}'."
            )
        if not source:
            return ToolResult.error("`source` is required.")

        resolver = (
            _rss.resolve_youtube
            if kind == _rss.YOUTUBE_KIND
            else _rss.resolve_podcast
        )
        try:
            resolved = await asyncio.to_thread(resolver, source)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))
        except Exception as exc:  # network/API failure — report, don't crash
            return ToolResult.error(f"Could not resolve '{source}': {exc}")

        if not resolved.get("feed_url"):
            return ToolResult.error(
                f"Resolved '{source}' but found no usable RSS feed."
            )

        label = (
            str(args.get("label") or "").strip()
            or resolved.get("label")
            or source
        )
        feed = {
            "id": _slugify(label),
            "kind": kind,
            "label": label,
            "source_url": source,
            "canonical_ref": resolved.get("canonical_ref") or "",
            "feed_url": resolved["feed_url"],
            "recency_days": int(args.get("recency_days") or 7),
            "max_items": int(args.get("max_items") or 5),
        }
        await _store.upsert_rss_feed(feed)
        return _ok({"subscribed": feed})


class UnsubscribeRssFeedTool(_BaseTool):
    """Stop following a creator or podcast by feed id."""

    name = "unsubscribe_rss_feed"
    description = "Stop following an RSS feed by its `rss_feed_id`."
    parameters = {
        "type": "object",
        "properties": {"rss_feed_id": {"type": "string"}},
        "required": ["rss_feed_id"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        feed_id = str((args or {}).get("rss_feed_id") or "").strip()
        if not feed_id:
            return ToolResult.error("`rss_feed_id` is required.")
        removed = await _store.delete_rss_feed(feed_id)
        return _ok({"removed": removed, "rss_feed_id": feed_id})


class ReadNewRssItemsTool(_BaseTool):
    """Fetch net-new items from a followed feed (deterministic, deduped)."""

    name = "read_new_rss_items"
    description = (
        "Fetch the followed feed's items published within its recency window, "
        "drop already-seen items, cap at its max_items, and attach best-effort "
        "content (YouTube transcript or podcast show-notes). Returns the items "
        "and the `section_topic_id` to pass to append_digest_section so dedup "
        "persists. This replaces web search for a feed — do not web-search it."
    )
    parameters = {
        "type": "object",
        "properties": {"rss_feed_id": {"type": "string"}},
        "required": ["rss_feed_id"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        feed_id = str((args or {}).get("rss_feed_id") or "").strip()
        if not feed_id:
            return ToolResult.error("`rss_feed_id` is required.")
        feed = await _store.get_rss_feed(feed_id)
        if feed is None:
            return ToolResult.error(f"No followed feed with id '{feed_id}'.")

        kind = str(feed["kind"])
        recency_days = int(feed["recency_days"])
        max_items = int(feed["max_items"])
        section_topic_id = f"{RSS_SECTION_PREFIX}{feed_id}"

        entries = await asyncio.to_thread(
            _rss.fetch_entries, str(feed["feed_url"]), kind
        )

        since = datetime.now(timezone.utc) - timedelta(days=recency_days)
        seen = await _store.recent_item_keys(section_topic_id, since)

        fresh: list[Dict[str, Any]] = []
        for entry in entries:
            published = entry.get("published")
            if published is not None and published < since:
                continue
            if entry.get("url") in seen or entry.get("title") in seen:
                continue
            fresh.append(entry)
            if len(fresh) >= max_items:
                break

        enriched = [
            await asyncio.to_thread(_rss.enrich, entry, kind) for entry in fresh
        ]
        items = [
            {
                "title": e.get("title"),
                "url": e.get("url"),
                "published": e.get("published"),
                "author": e.get("author"),
                "content": e.get("content") or e.get("summary"),
            }
            for e in enriched
        ]
        return _ok(
            {
                "rss_feed_id": feed_id,
                "label": feed["label"],
                "kind": kind,
                "section_topic_id": section_topic_id,
                "items": items,
            }
        )


class FetchRssItemsTool(_BaseTool):
    """Resolve a creator/podcast on the fly and fetch its latest items."""

    name = "fetch_rss_items"
    description = (
        "Fetch the latest items from a YouTube creator or podcast the user has "
        "NOT saved — for freeform requests like 'latest episodes of <podcast>' or "
        "'newest videos from <creator>'. Give the `kind` and a `source` (a "
        "@handle/channel URL/name or UC… id for youtube_channel; a show name or "
        "RSS URL for podcast). Resolves the feed via the YouTube Data API / "
        "Podcast Index and returns up to `max_items` newest items with "
        "best-effort content. No subscription is created and no skip-seen is "
        "applied. Prefer this over web search for a named creator/podcast; if it "
        "errors (e.g. resolution keys not configured), fall back to web search. "
        "Record the section with an empty `topic_id`."
    )
    parameters = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [_rss.YOUTUBE_KIND, _rss.PODCAST_KIND],
            },
            "source": {
                "type": "string",
                "description": "Handle/URL/name (youtube) or show name/RSS URL (podcast).",
            },
            "max_items": {
                "type": "integer",
                "description": "Newest items to return (default 5).",
            },
        },
        "required": ["kind", "source"],
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        args = args or {}
        kind = str(args.get("kind") or "").strip()
        source = str(args.get("source") or "").strip()
        if kind not in (_rss.YOUTUBE_KIND, _rss.PODCAST_KIND):
            return ToolResult.error(
                f"`kind` must be '{_rss.YOUTUBE_KIND}' or '{_rss.PODCAST_KIND}'."
            )
        if not source:
            return ToolResult.error("`source` is required.")
        max_items = int(args.get("max_items") or 5)

        resolver = (
            _rss.resolve_youtube
            if kind == _rss.YOUTUBE_KIND
            else _rss.resolve_podcast
        )
        try:
            resolved = await asyncio.to_thread(resolver, source)
        except (RuntimeError, ValueError) as exc:
            return ToolResult.error(str(exc))
        except Exception as exc:  # network/API failure — report, don't crash
            return ToolResult.error(f"Could not resolve '{source}': {exc}")

        feed_url = resolved.get("feed_url")
        if not feed_url:
            return ToolResult.error(
                f"Resolved '{source}' but found no usable RSS feed."
            )

        entries = await asyncio.to_thread(_rss.fetch_entries, feed_url, kind)
        # Newest first, then take the most recent few — "latest episodes".
        entries.sort(
            key=lambda e: e.get("published")
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        latest = entries[:max_items]
        enriched = [
            await asyncio.to_thread(_rss.enrich, entry, kind) for entry in latest
        ]
        items = [
            {
                "title": e.get("title"),
                "url": e.get("url"),
                "published": e.get("published"),
                "author": e.get("author"),
                "content": e.get("content") or e.get("summary"),
            }
            for e in enriched
        ]
        return _ok(
            {
                "kind": kind,
                "label": resolved.get("label") or source,
                "feed_url": feed_url,
                "items": items,
            }
        )
