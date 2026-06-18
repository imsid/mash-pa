---
name: curate-digest
description: Curate fresh web content for topics and produce an Axios-style digest, skipping already-seen items.
---

# Curate Digest

Turn the user's topics into one Axios-style ("Smart Brevity") digest. This skill
backs both the `run-digest` workflow (over saved topics) and freeform digest
requests (an ad-hoc topic the user describes).

## Resolve the sources

A digest has two kinds of source: **topics** (curated by web search) and
**followed feeds** (`rss_feed_ids` — YouTube creators and podcasts, fetched by
RSS). Process both.

- **Workflow / saved digest:** read `digest_id` from `workflow_input` (default
  `default`). Call `read_digests` with that `digest_id`; it returns `topics`
  (topic rows) and `rss_feeds` (followed creators/podcasts). If both are empty,
  stop and reply: "Nothing set up yet — run `/workflow run interview-user` to set
  up your interests." Do not call `AskUser`.
- **Freeform:** build a single ad-hoc topic from the user's request (pick a label,
  intent, sensible `recency_days` and `max_items`, and any sources they named).
  Omit `digest_id` when recording it. **Exception:** if the request names a
  specific YouTube creator or podcast (e.g. "latest episodes of the Training Data
  podcast"), treat it as an ad-hoc feed, not a web topic — see "Ad-hoc feeds"
  below — and do not web-search it.

## Open the run

Call `start_digest_run` once with a `title` (the digest's label, or the freeform
topic label) and, if you can frame it up front, a `lead` — the "1 big thing", the
single most important item across all topics, in 2–3 sentences. Include `digest_id`
for a saved digest; omit it for a freeform digest. Keep the returned `run_id`.

Then process each topic **one at a time**, finishing each as its own section
before moving on, so no single response has to emit the whole digest.

## 1. Curate

- If the topic has `sources`, search those trusted domains first (scope
  `web_search` queries to them). If they return too little, fall back to an open
  `web_search` and mark those items as `unverified-source`.
- If the topic has no sources, use open `web_search`.
- Respect `recency_days`: prefer items published within that window.

## 2. Extract

`web_fetch` the most promising candidates (no more than `max_items`) to get real
content. Never summarize from search snippets alone for headline items.

## 3. Dedup (skip-seen)

Call `read_digest_history` with the topic id and its `recency_days`. Drop any
candidate whose URL or title is already in the returned `seen` set. Keep only
net-new items. If everything was already seen, say the topic was quiet.

## 4. Write the section (Axios "Smart Brevity")

Write this topic's card in markdown, then immediately record it — do not wait
until all topics are done:

- Use the topic label as the heading. For each item:
  - a **bold one-line headline** that is itself a markdown link to the source,
    `**[Headline text](https://source-url)**`,
  - *Why it matters:* one sentence,
  - 1–3 tight bullets ("The big picture", "Between the lines", numbers),
  - **Go deeper:** `[publisher/title](https://source-url)` — a real, clickable
    markdown link to the exact page you fetched, never a bare label or "(link)".
- Tag any open-web fallback items as `(unverified source)`.
- If the topic had nothing net-new, make the card one line saying it was quiet.

Every item must carry its source URL as a markdown link — both in the headline
and the **Go deeper:** line. Cite every claim with its link, and never emit an
item, table row, or bullet without the underlying URL. Never invent sources,
links, or facts: only ever link to URLs you actually retrieved with `web_fetch`
(or that `read_new_rss_items` / `fetch_rss_items` returned).

## 5. Record the section

Call `append_digest_section` with:

- `run_id`: the id from `start_digest_run`,
- `topic_id`: this topic's id (empty for a freeform digest),
- `heading`: the topic label,
- `content`: this card's rendered markdown,
- `seen`: `{ "urls": [...], "titles": [...] }` for the items in this card (this
  powers skip-seen next time).

Then move to the next topic and repeat steps 1–5.

## Followed feeds (creators / podcasts)

For each id in the digest's `rss_feed_ids`, **do not web-search** — the feed is
the source of truth:

1. Call `read_new_rss_items` with the `rss_feed_id`. It returns the net-new,
   already-deduped items (respecting the feed's recency window and `max_items`),
   each with best-effort `content` (a YouTube transcript or podcast show-notes),
   plus the `section_topic_id` to record under.
2. Write one Axios card for the feed, heading = the feed `label`. For each item:
   a **bold headline** that is a markdown link to the item `url`
   (`**[Episode title](url)**`), *Why it matters:* one sentence grounded in its
   `content`, 1–3 tight bullets, and **Go deeper:** `[label](url)` as a clickable
   markdown link to the item `url`. If `items` is empty, make the card one line
   saying the feed was quiet.
3. Record it with `append_digest_section`: `run_id`, `topic_id` = the returned
   `section_topic_id` (e.g. `rss:lex-fridman`), `heading` = the feed label,
   `content` = the card markdown, and `seen` = `{ "urls": [...], "titles": [...] }`
   for the items shown (this powers skip-seen next run).

## Ad-hoc feeds (an unsaved creator / podcast named in a freeform request)

When the user names a YouTube creator or podcast that is **not** saved, do **not**
web-search it — resolve and fetch it directly:

1. Call `fetch_rss_items` with the `kind` (`youtube_channel` or `podcast`), the
   `source` (the name/handle/URL the user gave), and an optional `max_items`. It
   resolves the feed (Apple Podcasts / YouTube Data API) and returns the latest
   items with best-effort `content`. Only if it errors (e.g. resolution keys not
   configured) fall back to an open `web_search`.
2. Write one Axios card exactly as for a followed feed (heading = the returned
   `label`).
3. Record it with `append_digest_section` using `topic_id` `""` (it is not saved,
   so it does not participate in skip-seen) and the `seen` items shown. You may
   offer to save it as a followed feed afterward, but do not require it.

After the last topic and feed, briefly confirm the digest is ready (the user has
seen each card as you wrote it).
