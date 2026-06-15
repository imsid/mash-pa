"""Postgres store for the digest agents.

Topics, named digest bundles, and generated digest runs live in `pa_*` tables in
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
from psycopg.rows import dict_row

from mash.core.database import resolve_database_url

DEFAULT_DIGEST_ID = "default"

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


async def _connect() -> "psycopg.AsyncConnection[Any]":
    conn = await psycopg.AsyncConnection.connect(
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
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digests (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                topic_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        # A digest run is one execution; its sections (cards) are written one at
        # a time so no single LLM generation has to emit the whole digest.
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digest_runs (
                id BIGSERIAL PRIMARY KEY,
                digest_id TEXT NOT NULL,
                title TEXT NOT NULL,
                lead TEXT NOT NULL DEFAULT '',
                generated_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        # Make the run title + lead full-text searchable too, not just sections
        # (a user searching "open source" expects to match the digest's title).
        # ADD COLUMN IF NOT EXISTS upgrades an existing table in place.
        await cursor.execute(
            """
            ALTER TABLE pa_digest_runs
            ADD COLUMN IF NOT EXISTS search_tsv TSVECTOR GENERATED ALWAYS AS (
                to_tsvector('english', title || ' ' || lead)
            ) STORED
            """
        )
        await cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pa_digest_sections (
                id BIGSERIAL PRIMARY KEY,
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


# --- Digest bundles ---------------------------------------------------------


async def list_digests() -> list[dict[str, Any]]:
    """Return every named digest bundle, ordered by id."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, label, topic_ids FROM pa_digests ORDER BY id"
            )
            return list(await cursor.fetchall())
    finally:
        await conn.close()


async def get_digest(digest_id: str) -> Optional[dict[str, Any]]:
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id, label, topic_ids FROM pa_digests WHERE id = %s",
                (str(digest_id),),
            )
            return await cursor.fetchone()
    finally:
        await conn.close()


async def upsert_digest(
    digest_id: str, label: str, topic_ids: list[str]
) -> None:
    now = _now()
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digests (id, label, topic_ids, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    label = EXCLUDED.label,
                    topic_ids = EXCLUDED.topic_ids,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    str(digest_id),
                    str(label),
                    json.dumps([str(t) for t in topic_ids]),
                    now,
                    now,
                ),
            )
    finally:
        await conn.close()


async def resolve_digest_topics(digest_id: str) -> list[dict[str, Any]]:
    """Resolve a bundle id to its topic rows, preserving the bundle's order."""
    bundle = await get_digest(digest_id)
    if bundle is None:
        return []
    ordered_ids = [str(t) for t in (bundle.get("topic_ids") or [])]
    if not ordered_ids:
        return []
    by_id = {row["id"]: row for row in await list_topics()}
    return [by_id[tid] for tid in ordered_ids if tid in by_id]


async def clear_all() -> None:
    """Remove all topics and bundles (used by reset). Digest runs are kept as
    history."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM pa_digests")
            await cursor.execute("DELETE FROM pa_topics")
    finally:
        await conn.close()


# --- Digest runs + sections (output + skip-seen) ----------------------------


async def start_digest_run(digest_id: str, title: str, lead: str = "") -> int:
    """Open a digest run and return its id. Sections are appended one at a
    time so no single generation has to emit the whole digest."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digest_runs (digest_id, title, lead, generated_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (str(digest_id), str(title), str(lead), _now()),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to insert digest run")
            return int(row["id"])
    finally:
        await conn.close()


async def append_digest_section(
    run_id: int,
    topic_id: str,
    heading: str,
    content: str,
    seen: dict[str, Any],
) -> int:
    """Append one section (card) to a run. Position is assigned in append
    order. Returns the section id."""
    conn = await _connect()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO pa_digest_sections
                    (run_id, position, topic_id, heading, content, seen, created_at)
                VALUES (
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
