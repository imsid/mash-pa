"""RSS connectors for the digest agents — YouTube creators and podcasts.

Everything here is RSS-first: in steady state we only fetch and parse public RSS
feeds (no auth, no quota). The official APIs are touched **once**, at subscribe
time, to resolve a human reference (a YouTube `@handle`, a podcast name or RSS
URL) into a canonical id and the feed URL we then poll forever:

- YouTube: the Data API resolves a handle/name to a `UC…` channel id; the feed is
  the first-party `feeds/videos.xml?channel_id=…`. A raw `UC…` id (or a
  `/channel/UC…` URL) resolves with no API key at all.
- Podcasts: the Podcast Index API resolves a show name or RSS URL to its feed
  URL. Spotify-exclusive shows have no public RSS and are out of scope.

Resolution raises a clear, actionable error when its key is missing, mirroring
how `_github` explains an unconfigured connection. Fetch and enrich never raise
for missing content — enrichment is best-effort and degrades to the feed's own
summary so a flaky transcript never breaks a digest.

These functions are synchronous (feedparser + httpx sync); tool code calls them
through `asyncio.to_thread` so the agent event loop is not blocked.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
import httpx

YOUTUBE_KIND = "youtube_channel"
PODCAST_KIND = "podcast"

YOUTUBE_FEED_TMPL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
PODCAST_INDEX_API = "https://api.podcastindex.org/api/1.0"

# A YouTube channel id is the literal "UC" followed by 22 url-safe base64 chars.
_CHANNEL_ID_RE = re.compile(r"(UC[0-9A-Za-z_-]{22})")
_HANDLE_RE = re.compile(r"@([0-9A-Za-z._-]+)")
_HTTP_TIMEOUT = httpx.Timeout(20.0)
_USER_AGENT = "mash-pa-digest/0.1 (+https://github.com/imsid/mash-pa)"
# Transcript link types we will actually fetch and inline (plain-ish text).
_TRANSCRIPT_TYPES = ("text/plain", "text/vtt", "application/srt", "text/html")
_MAX_CONTENT_CHARS = 4000


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_HTTP_TIMEOUT,
        headers={"User-Agent": _USER_AGENT},
        follow_redirects=True,
    )


# --- YouTube resolution -----------------------------------------------------


def resolve_youtube(source: str) -> dict[str, Any]:
    """Resolve a YouTube reference to {kind, canonical_ref, feed_url, label}.

    Accepts a raw `UC…` channel id, a `/channel/UC…` URL (no API key needed), or
    a `@handle` / name / handle URL (needs `YOUTUBE_API_KEY`).
    """
    source = (source or "").strip()
    if not source:
        raise ValueError("A YouTube channel id, handle, or URL is required.")

    direct = _CHANNEL_ID_RE.search(source)
    if direct:
        cid = direct.group(1)
        return {
            "kind": YOUTUBE_KIND,
            "canonical_ref": cid,
            "feed_url": YOUTUBE_FEED_TMPL.format(cid=cid),
            "label": "",
        }

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Resolving a YouTube handle or name needs YOUTUBE_API_KEY on the "
            "deployment. Either set it and restart, or subscribe with the raw "
            "channel id (UC…) or a youtube.com/channel/UC… URL, which needs no key."
        )

    handle_match = _HANDLE_RE.search(source)
    cid, label = _youtube_lookup(api_key, source, handle_match)
    return {
        "kind": YOUTUBE_KIND,
        "canonical_ref": cid,
        "feed_url": YOUTUBE_FEED_TMPL.format(cid=cid),
        "label": label,
    }


def _youtube_lookup(
    api_key: str, source: str, handle_match: Optional[re.Match[str]]
) -> tuple[str, str]:
    """Return (channel_id, title) via the Data API: handle first, then search."""
    with _client() as client:
        if handle_match:
            resp = client.get(
                f"{YOUTUBE_API}/channels",
                params={
                    "part": "snippet",
                    "forHandle": handle_match.group(1),
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            items = resp.json().get("items") or []
            if items:
                return items[0]["id"], items[0]["snippet"]["title"]

        # Fall back to a channel search on the free-text name.
        resp = client.get(
            f"{YOUTUBE_API}/search",
            params={
                "part": "snippet",
                "type": "channel",
                "q": source,
                "maxResults": 1,
                "key": api_key,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items") or []
        if not items:
            raise RuntimeError(f"No YouTube channel found for '{source}'.")
        snippet = items[0]["snippet"]
        return snippet["channelId"], snippet.get("title", "")


# --- Podcast resolution -----------------------------------------------------


def resolve_podcast(source: str) -> dict[str, Any]:
    """Resolve a podcast reference to {kind, canonical_ref, feed_url, label}.

    Accepts a show name (Podcast Index search) or an RSS feed URL
    (validated/looked up by feed URL). Needs PODCAST_INDEX_API_KEY/_SECRET.
    A Spotify-exclusive show with no public RSS cannot be resolved.
    """
    source = (source or "").strip()
    if not source:
        raise ValueError("A podcast name or RSS feed URL is required.")

    key = os.getenv("PODCAST_INDEX_API_KEY")
    secret = os.getenv("PODCAST_INDEX_API_SECRET")
    if not key or not secret:
        raise RuntimeError(
            "Resolving a podcast needs PODCAST_INDEX_API_KEY and "
            "PODCAST_INDEX_API_SECRET on the deployment. Set them (free at "
            "podcastindex.org) and restart, or subscribe with the show's RSS "
            "feed URL directly."
        )

    is_feed_url = source.startswith("http") and "spotify.com" not in source
    with _client() as client:
        client.headers.update(_podcast_index_auth(key, secret))
        if is_feed_url:
            resp = client.get(
                f"{PODCAST_INDEX_API}/podcasts/byfeedurl", params={"url": source}
            )
            resp.raise_for_status()
            feed = resp.json().get("feed") or {}
            if not feed:
                raise RuntimeError(f"No podcast found at feed URL '{source}'.")
        else:
            resp = client.get(
                f"{PODCAST_INDEX_API}/search/byterm",
                params={"q": source, "max": 1},
            )
            resp.raise_for_status()
            feeds = resp.json().get("feeds") or []
            if not feeds:
                raise RuntimeError(
                    f"No podcast found for '{source}'. If it is a Spotify "
                    "exclusive it has no public RSS feed and cannot be followed."
                )
            feed = feeds[0]

    return {
        "kind": PODCAST_KIND,
        "canonical_ref": str(feed.get("id") or feed.get("url") or ""),
        "feed_url": feed.get("url") or "",
        "label": feed.get("title") or "",
    }


def _podcast_index_auth(key: str, secret: str) -> dict[str, str]:
    """Podcast Index auth headers: sha1(key + secret + unix_time)."""
    now = str(int(time.time()))
    digest = hashlib.sha1((key + secret + now).encode("utf-8")).hexdigest()
    return {"X-Auth-Key": key, "X-Auth-Date": now, "Authorization": digest}


# --- Fetch + enrich (steady state, pure RSS) --------------------------------


def fetch_entries(feed_url: str, kind: str) -> list[dict[str, Any]]:
    """Fetch and normalize a feed's items, newest first.

    Each item: {title, url, published(datetime|None), author, summary,
    video_id, transcript_url}. Never raises on a malformed feed — returns what
    parsed.
    """
    if not feed_url:
        return []
    try:
        with _client() as client:
            resp = client.get(feed_url)
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPError:
        return []

    parsed = feedparser.parse(raw)
    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        items.append(
            {
                "title": (entry.get("title") or "").strip(),
                "url": entry.get("link") or "",
                "published": _entry_published(entry),
                "author": entry.get("author") or "",
                "summary": _entry_summary(entry),
                "video_id": entry.get("yt_videoid") or "",
                "transcript_url": _podcast_transcript_url(entry)
                if kind == PODCAST_KIND
                else "",
            }
        )
    return items


def _entry_published(entry: Any) -> Optional[datetime]:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def _entry_summary(entry: Any) -> str:
    """Best text the feed itself carries: content:encoded > summary > media."""
    content = entry.get("content")
    if content and isinstance(content, list) and content[0].get("value"):
        return str(content[0]["value"])
    return str(entry.get("summary") or entry.get("media_description") or "")


def _podcast_transcript_url(entry: Any) -> str:
    """Best-effort Podcasting-2.0 <podcast:transcript> URL, if the feed has one."""
    candidate = entry.get("podcast_transcript") or entry.get("transcript")
    if isinstance(candidate, dict) and candidate.get("url"):
        return str(candidate["url"])
    for link in entry.get("links") or []:
        if str(link.get("type", "")).lower() in _TRANSCRIPT_TYPES and link.get(
            "rel"
        ) in ("transcript", "alternate"):
            # Heuristic; most feeds expose the transcript via the namespaced tag.
            if "transcript" in str(link.get("href", "")).lower():
                return str(link["href"])
    return ""


def enrich(item: dict[str, Any], kind: str) -> dict[str, Any]:
    """Attach best-effort `content` to an item; always falls back to `summary`.

    Mutates and returns the item. A failed transcript fetch is swallowed — the
    feed's own summary/show-notes is the floor, never an error.
    """
    summary = _truncate(item.get("summary") or "")
    content = summary
    if kind == YOUTUBE_KIND and item.get("video_id"):
        transcript = _youtube_transcript(item["video_id"])
        if transcript:
            content = _truncate(transcript)
    elif kind == PODCAST_KIND and item.get("transcript_url"):
        transcript = _fetch_text(item["transcript_url"])
        if transcript:
            content = _truncate(transcript)
    item["content"] = content
    return item


def _youtube_transcript(video_id: str) -> str:
    """Best-effort caption fetch via the public timedtext endpoint. Often empty
    (captions are not always public); the caller falls back to the description."""
    try:
        with _client() as client:
            resp = client.get(
                "https://www.youtube.com/api/timedtext",
                params={"lang": "en", "v": video_id, "fmt": "json3"},
            )
        if resp.status_code != 200 or not resp.content:
            return ""
        events = resp.json().get("events") or []
        parts: list[str] = []
        for event in events:
            for seg in event.get("segs") or []:
                text = seg.get("utf8")
                if text:
                    parts.append(text)
        return " ".join("".join(parts).split())
    except (httpx.HTTPError, ValueError):
        return ""


def _fetch_text(url: str) -> str:
    """Fetch a transcript URL and strip it to plain text. Best-effort."""
    try:
        with _client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.text
    except httpx.HTTPError:
        return ""
    # Strip tags/cues crudely; transcripts are plain text, vtt, or light html.
    stripped = re.sub(r"<[^>]+>", " ", body)
    stripped = re.sub(r"\d{2}:\d{2}:\d{2}[.,]\d{3} --> [^\n]+", " ", stripped)
    return " ".join(stripped.split())


def _truncate(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= _MAX_CONTENT_CHARS:
        return text
    return text[:_MAX_CONTENT_CHARS].rsplit(" ", 1)[0] + " …"
