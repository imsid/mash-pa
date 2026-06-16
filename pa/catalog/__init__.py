"""The PA catalog: every pooled agent the store ships, with its listing.

Each entry pairs an agent factory with the `AgentMetadata` that becomes its
store listing (and, when the agent serves as a subagent, the delegation
directory the primary reads). Adding an agent to the store is adding a
package under `agents/` and one entry to `CATALOG`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

# Load the repo .env before any agent module is imported: agent modules read
# model/provider configuration from the environment at import time.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from mash.runtime import AgentMetadata, AgentSpec  # noqa: E402

from . import digest  # noqa: E402
from .agents import finance_watch  # noqa: E402
from .digest import build_digest_workflow_specs  # noqa: E402


@dataclass(frozen=True)
class CatalogEntry:
    """One store listing: an agent id, its spec factory, and its metadata."""

    agent_id: str
    create_spec: Callable[..., AgentSpec]  # accepts workspace_root=...
    build_metadata: Callable[[], AgentMetadata]


CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        digest.DIGEST_CURATOR_AGENT_ID,
        digest.digest_curator.create_spec,
        digest.digest_curator.build_metadata,
    ),
    CatalogEntry(
        digest.DIGEST_CONCIERGE_AGENT_ID,
        digest.digest_concierge.create_spec,
        digest.digest_concierge.build_metadata,
    ),
    CatalogEntry(
        finance_watch.FINANCE_WATCH_AGENT_ID,
        finance_watch.create_spec,
        finance_watch.build_metadata,
    ),
)

__all__ = ["CATALOG", "CatalogEntry", "build_digest_workflow_specs"]
