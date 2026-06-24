"""Postgres store for the digest agents.

Topics, named digests, and generated digest runs live in `pa_*` tables in
the same database the Mash runtime uses (`MASH_DATABASE_URL`). That URL is
**required** — there is no file fallback; the store raises if it is unset.

The access pattern mirrors `mash.memory.store.backends.postgres.store`: psycopg v3
async, autocommit, lazy `CREATE TABLE IF NOT EXISTS`. Each call opens a
short-lived connection rather than sharing one across the pooled agent runtimes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import psycopg
from psycopg.rows import DictRow, dict_row

from mash.core.database import resolve_database_url

# Flipped once a connection has ensured the schema, so we do not re-run the DDL
# on every call within a process. A mutable holder avoids a module `global`.
_SCHEMA_READY = {"value": False}


def _database_url() -> str:
    url = resolve_database_url()
    if not url:
        raise RuntimeError(
            "MASH_DATABASE_URL is required for the digest agents. Set it on the "
            "deployment (the embedded Postgres URL or your own) and restart."
        )
    return url


async def _connect() -> "psycopg.AsyncConnection[DictRow]":
    # Parametrize the class so `row_factory=dict_row` type-checks: calling
    # `connect` on the bare AsyncConnection binds Row to the default TupleRow.
    conn = await psycopg.AsyncConnection[DictRow].connect(
        _database_url(), row_factory=dict_row
    )
    await conn.set_autocommit(True)
    await _ensure_schema(conn)
    return conn


async def _ensure_schema(conn: "psycopg.AsyncConnection[Any]") -> None:
    if _SCHEMA_READY["value"]:
        return
    async with conn.cursor() as cursor:
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_topics (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                intent TEXT NOT NULL,
                sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                recency_days INT NOT NULL,
                max_items INT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        # A digest is a named collection (configured topics/feeds) or a freeform
        # snapshot; either way it is a real row, and `source` records what created
        # it (a workflow/agent id, e.g. `interview-user`, `github-digest`,
        # `digest-curator`). `id` is DB-generated.
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digests (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                label TEXT NOT NULL,
                source TEXT NOT NULL,
                topic_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                rss_feed_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        # Followed YouTube channels / podcasts. Resolved once at subscribe time
        # (canonical_ref + feed_url cached) so steady-state polling is pure RSS.
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_rss_feeds (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                canonical_ref TEXT NOT NULL DEFAULT '',
                feed_url TEXT NOT NULL,
                recency_days INT NOT NULL,
                max_items INT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        # A digest run is one execution of a digest; its sections (cards) are
        # written one at a time so no single LLM generation has to emit the whole
        # digest. Every run belongs to a `pa_digests` row. The run title + lead
        # are full-text searchable too, not just sections.
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digest_runs (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                digest_id BIGINT NOT NULL
                    REFERENCES pa_digests (id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                lead TEXT NOT NULL DEFAULT '',
                generated_at TIMESTAMPTZ NOT NULL,
                search_tsv TSVECTOR GENERATED ALWAYS AS (
                    to_tsvector('english', title || ' ' || lead)
                ) STORED
            )
            """
        )
        # Sections carry `digest_id` (denormalized from the run) alongside
        # `run_id` so a digest's cards are directly queryable without the join.
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digest_sections (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                digest_id BIGINT NOT NULL
                    REFERENCES pa_digests (id) ON DELETE CASCADE,
                run_id BIGINT NOT NULL
                    REFERENCES pa_digest_runs (id) ON DELETE CASCADE,
                position INT NOT NULL,
                topic_id TEXT NOT NULL,
                heading TEXT NOT NULL,
                content TEXT NOT NULL,
                seen JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                search_tsv TSVECTOR GENERATED ALWAYS AS (
                    to_tsvector('english', heading || ' ' || content)
                ) STORED
            )
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_runs_digest
            ON pa_digest_runs (digest_id, generated_at DESC)
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_runs_generated_at
            ON pa_digest_runs (generated_at DESC)
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_runs_search
            ON pa_digest_runs USING GIN (search_tsv)
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_sections_run
            ON pa_digest_sections (run_id, position)
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_sections_topic
            ON pa_digest_sections (topic_id, created_at)
            """
        )
        await cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pa_digest_sections_search
            ON pa_digest_sections USING GIN (search_tsv)
            """
        )
    _SCHEMA_READY["value"] = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Topics -----------------------------------------------------------------


async def list_topics() -> list[dict[str, Any]]:
    """Return every topic, ordered by label."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, label, intent, sources, recency_days, max_items "
                "FROM pa_topics ORDER BY label"
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def upsert_topics(topics: list[dict[str, Any]]) -> None:
    """Insert or update topic rows by id."""
    if not topics:
        return
    now = _now()
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            for topic in topics:
                await cursor.execute(
                    """
                    INSERT INTO pa_topics
                        (id, label, intent, sources, recency_days, max_items,
                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        label = EXCLUDED.label,
                        intent = EXCLUDED.intent,
                        sources = EXCLUDED.sources,
                        recency_days = EXCLUDED.recency_days,
                        max_items = EXCLUDED.max_items,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        str(topic["id"]),
                        str(topic["label"]),
                        str(topic["intent"]),
                        json.dumps(list(topic.get("sources") or [])),
                        int(topic["recency_days"]),
                        int(topic["max_items"]),
                        now,
                        now,
                    ),
                )
    finally:
        await conn.close()


# --- Digests (saved collections of topics + feeds) --------------------------


async def list_digests() -> list[dict[str, Any]]:
    """Return every digest, ordered by id."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, label, source, topic_ids, rss_feed_ids "
                "FROM pa_digests ORDER BY id"
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def list_digest_configs() -> list[dict[str, Any]]:
    """Return every digest's configuration with run stats: its label, source,
    the resolved topic and feed labels it contains, run count, and last run time.
    Powers `/digest config`. Ids that no longer resolve fall back to the raw id."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT d.id, d.label, d.source, d.topic_ids, d.rss_feed_ids,
                       count(r.id) AS runs,
                       max(r.generated_at) AS last_run
                FROM pa_digests d
                LEFT JOIN pa_digest_runs r ON r.digest_id = d.id
                GROUP BY d.id
                ORDER BY d.id
                """
            )
            rows = list(await cursor.fetchall())
    finally:
        await conn.close()
    topic_labels = {row["id"]: row["label"] for row in await list_topics()}
    feed_labels = {row["id"]: row["label"] for row in await list_rss_feeds()}
    for row in rows:
        row["topics"] = [
            topic_labels.get(str(tid), str(tid))
            for tid in (row.pop("topic_ids") or [])
        ]
        row["feeds"] = [
            feed_labels.get(str(fid), str(fid))
            for fid in (row.pop("rss_feed_ids") or [])
        ]
    return rows


async def get_digest(digest_id: int) -> Optional[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, label, source, topic_ids, rss_feed_ids "
                "FROM pa_digests WHERE id = %s",
                (int(digest_id),),
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def create_digest(
    label: str,
    source: str,
    topic_ids: Optional[list[str]] = None,
    rss_feed_ids: Optional[list[str]] = None,
) -> int:
    """Insert a new digest and return its DB-generated id. `source` records what
    created it (a workflow/agent id)."""
    now = _now()
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digests
                    (label, source, topic_ids, rss_feed_ids, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    str(label),
                    str(source),
                    json.dumps([str(t) for t in (topic_ids or [])]),
                    json.dumps([str(f) for f in (rss_feed_ids or [])]),
                    now,
                    now,
                ),
            )
            row = await cursor.fetchone()
            return int(row["id"])
    finally:
        await conn.close()


async def update_digest(
    digest_id: int,
    label: str,
    topic_ids: list[str],
    rss_feed_ids: Optional[list[str]] = None,
) -> bool:
    """Update an existing digest's label and contents. Returns False if no such
    digest exists."""
    now = _now()
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE pa_digests SET
                    label = %s,
                    topic_ids = %s,
                    rss_feed_ids = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    str(label),
                    json.dumps([str(t) for t in topic_ids]),
                    json.dumps([str(f) for f in (rss_feed_ids or [])]),
                    now,
                    int(digest_id),
                ),
            )
            return cursor.rowcount > 0
    finally:
        await conn.close()


async def resolve_digest_topics(digest_id: int) -> list[dict[str, Any]]:
    """Resolve a digest id to its topic rows, preserving the digest's order."""
    digest = await get_digest(digest_id)
    if digest is None:
        return []
    ordered_ids = [str(t) for t in (digest.get("topic_ids") or [])]
    if not ordered_ids:
        return []
    by_id = {row["id"]: row for row in await list_topics()}
    return [by_id[tid] for tid in ordered_ids if tid in by_id]


async def resolve_digest_rss_feeds(digest_id: int) -> list[dict[str, Any]]:
    """Resolve a digest id to its followed feed rows, preserving digest order."""
    digest = await get_digest(digest_id)
    if digest is None:
        return []
    ordered_ids = [str(f) for f in (digest.get("rss_feed_ids") or [])]
    if not ordered_ids:
        return []
    by_id = {row["id"]: row for row in await list_rss_feeds()}
    return [by_id[fid] for fid in ordered_ids if fid in by_id]


async def clear_all() -> None:
    """Reset saved interests: remove all topics and followed feeds, and drop
    digest definitions that were never run. Digests with run history are kept (a
    delete would cascade their runs), so past digests stay viewable."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                DELETE FROM pa_digests d
                WHERE NOT EXISTS (
                    SELECT 1 FROM pa_digest_runs r WHERE r.digest_id = d.id
                )
                """
            )
            await cursor.execute("DELETE FROM pa_topics")
            await cursor.execute("DELETE FROM pa_rss_feeds")
    finally:
        await conn.close()


# --- RSS feeds (followed creators / podcasts) -------------------------------


async def list_rss_feeds() -> list[dict[str, Any]]:
    """Return every followed feed, ordered by label."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, kind, label, source_url, canonical_ref, feed_url, "
                "recency_days, max_items FROM pa_rss_feeds ORDER BY label"
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def get_rss_feed(feed_id: str) -> Optional[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, kind, label, source_url, canonical_ref, feed_url, "
                "recency_days, max_items FROM pa_rss_feeds WHERE id = %s",
                (str(feed_id),),
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def upsert_rss_feed(feed: dict[str, Any]) -> None:
    """Insert or update a followed feed by id."""
    now = _now()
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_rss_feeds
                    (id, kind, label, source_url, canonical_ref, feed_url,
                     recency_days, max_items, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    label = EXCLUDED.label,
                    source_url = EXCLUDED.source_url,
                    canonical_ref = EXCLUDED.canonical_ref,
                    feed_url = EXCLUDED.feed_url,
                    recency_days = EXCLUDED.recency_days,
                    max_items = EXCLUDED.max_items,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    str(feed["id"]),
                    str(feed["kind"]),
                    str(feed["label"]),
                    str(feed.get("source_url") or ""),
                    str(feed.get("canonical_ref") or ""),
                    str(feed["feed_url"]),
                    int(feed["recency_days"]),
                    int(feed["max_items"]),
                    now,
                    now,
                ),
            )
    finally:
        await conn.close()


async def delete_rss_feed(feed_id: str) -> bool:
    """Delete a followed feed by id. Returns whether a row was removed."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "DELETE FROM pa_rss_feeds WHERE id = %s", (str(feed_id),)
            )
            return cursor.rowcount > 0
    finally:
        await conn.close()


# --- Digest runs + sections (output + skip-seen) ----------------------------


async def start_digest_run(
    title: str,
    *,
    digest_id: Optional[int] = None,
    workflow: Optional[str] = None,
    lead: str = "",
) -> dict[str, int]:
    """Open a digest run and return its digest id and run id. Provide exactly
    one of:

    - `digest_id`: attach the run to an existing digest (a configured digest, or
      one named in the workflow input).
    - `workflow`: create a freeform digest on the fly (label = `title`, `source`
      = `workflow`, no topics) and run under it.

    Sections are appended one at a time so no single generation has to emit the
    whole digest.
    """
    has_digest = digest_id is not None
    has_workflow = bool(workflow and str(workflow).strip())
    if has_digest == has_workflow:
        raise ValueError("provide exactly one of `digest_id` or `workflow`")

    if has_workflow:
        digest_id = await create_digest(
            label=str(title), source=str(workflow).strip()
        )

    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digest_runs (digest_id, title, lead, generated_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (int(digest_id), str(title), str(lead), _now()),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to insert digest run")
            return {"digest_id": int(digest_id), "run_id": int(row["id"])}
    finally:
        await conn.close()


async def append_digest_section(
    run_id: int,
    topic_id: str,
    heading: str,
    content: str,
    seen: dict[str, Any],
) -> int:
    """Append one section (card) to a run. The section's `digest_id` is derived
    from the run. Position is assigned in append order. Returns the section id."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digest_sections
                    (digest_id, run_id, position, topic_id, heading, content,
                     seen, created_at)
                VALUES (
                    (SELECT digest_id FROM pa_digest_runs WHERE id = %s),
                    %s,
                    (SELECT COALESCE(MAX(position) + 1, 0)
                       FROM pa_digest_sections WHERE run_id = %s),
                    %s, %s, %s, %s, %s
                )
                RETURNING id
                """,
                (
                    int(run_id),
                    int(run_id),
                    int(run_id),
                    str(topic_id),
                    str(heading),
                    str(content),
                    json.dumps(seen or {}),
                    _now(),
                ),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to insert digest section")
            return int(row["id"])
    finally:
        await conn.close()


async def recent_item_keys(topic_id: str, since: datetime) -> set[str]:
    """URLs and titles already surfaced for a topic since `since` — the
    skip-seen source. Reads the `seen` payload of that topic's sections."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT seen FROM pa_digest_sections
                WHERE topic_id = %s AND created_at >= %s
                """,
                (str(topic_id), since),
            )
            rows = await cursor.fetchall()
    finally:
        await conn.close()
    keys: set[str] = set()
    for row in rows:
        seen = row.get("seen") or {}
        for key in ("urls", "titles"):
            for value in seen.get(key) or []:
                text = str(value).strip()
                if text:
                    keys.add(text)
    return keys


# --- Digest reads (CLI) -----------------------------------------------------


async def latest_run() -> Optional[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, digest_id, title, lead, generated_at "
                "FROM pa_digest_runs ORDER BY generated_at DESC, id DESC LIMIT 1"
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def get_run(run_id: int) -> Optional[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, digest_id, title, lead, generated_at "
                "FROM pa_digest_runs WHERE id = %s",
                (int(run_id),),
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def get_run_for_digest(
    digest_id: int, run_id: int
) -> Optional[dict[str, Any]]:
    """Fetch a run only if it belongs to the given digest (the addressing the
    `/digest <digest_id> <run_id>` command uses)."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, digest_id, title, lead, generated_at "
                "FROM pa_digest_runs WHERE id = %s AND digest_id = %s",
                (int(run_id), int(digest_id)),
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def digest_run_payload(run: dict[str, Any]) -> dict[str, Any]:
    """Build the structured render payload for a run — its ids, title, lead, and
    ordered sections. Shared by the CLI renderer and the workflow's structured
    output so both render the same shape."""
    sections = await get_run_sections(int(run["id"]))
    return {
        "digest_id": int(run["digest_id"]),
        "run_id": int(run["id"]),
        "title": str(run["title"]),
        "lead": str(run.get("lead") or ""),
        "sections": [
            {
                "position": int(s["position"]),
                "heading": str(s["heading"]),
                "content": str(s["content"]),
            }
            for s in sections
        ],
    }


async def get_run_sections(run_id: int) -> list[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT position, topic_id, heading, content "
                "FROM pa_digest_sections WHERE run_id = %s ORDER BY position",
                (int(run_id),),
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def list_recent_runs(n: int) -> list[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT r.id, r.digest_id, r.title, r.generated_at,
                       count(s.id) AS sections
                FROM pa_digest_runs r
                LEFT JOIN pa_digest_sections s ON s.run_id = r.id
                GROUP BY r.id
                ORDER BY r.generated_at DESC, r.id DESC
                LIMIT %s
                """,
                (int(n),),
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def search_runs(query: str, n: int) -> list[dict[str, Any]]:
    """Full-text search over a run's title/lead and its section headings +
    content; returns the matching runs, best rank first."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                SELECT r.id, r.digest_id, r.title, r.generated_at,
                       greatest(
                           ts_rank(r.search_tsv,
                                   websearch_to_tsquery('english', %(q)s)),
                           coalesce(max(ts_rank(s.search_tsv,
                                   websearch_to_tsquery('english', %(q)s))), 0)
                       ) AS rank
                FROM pa_digest_runs r
                LEFT JOIN pa_digest_sections s
                       ON s.run_id = r.id
                      AND s.search_tsv @@ websearch_to_tsquery('english', %(q)s)
                WHERE r.search_tsv @@ websearch_to_tsquery('english', %(q)s)
                   OR s.id IS NOT NULL
                GROUP BY r.id
                ORDER BY rank DESC, r.generated_at DESC, r.id DESC
                LIMIT %(n)s
                """,
                {"q": str(query), "n": int(n)},
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()
