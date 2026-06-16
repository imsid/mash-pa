"""Agent tools over the digest store, grouped by domain.

Each submodule mirrors a section of `_store`: `topics`, `digests` (the saved
named digests + reset), `runs` (digest runs/sections and skip-seen), and
`rss_feeds` (followed creators/podcasts). Tools are re-exported here so callers
import any of them from
`pa.catalog.digest.tools` without knowing which submodule defines it.
"""

from __future__ import annotations

from .digests import ClearInterestsTool, ReadDigestsTool, WriteDigestTool
from .rss_feeds import (
    RSS_SECTION_PREFIX,
    FetchRssItemsTool,
    ReadNewRssItemsTool,
    ReadRssFeedsTool,
    SubscribeRssFeedTool,
    UnsubscribeRssFeedTool,
)
from .runs import AppendDigestSectionTool, ReadDigestHistoryTool, StartDigestRunTool
from .topics import ReadTopicsTool, WriteTopicsTool

__all__ = [
    "RSS_SECTION_PREFIX",
    "ReadTopicsTool",
    "WriteTopicsTool",
    "ReadDigestsTool",
    "WriteDigestTool",
    "ClearInterestsTool",
    "ReadDigestHistoryTool",
    "StartDigestRunTool",
    "AppendDigestSectionTool",
    "ReadRssFeedsTool",
    "SubscribeRssFeedTool",
    "UnsubscribeRssFeedTool",
    "ReadNewRssItemsTool",
    "FetchRssItemsTool",
]
