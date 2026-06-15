---
name: curate-digest
description: Curate fresh web content for topics and produce an Axios-style digest, skipping already-seen items.
---

# Curate Digest

Turn the user's topics into one Axios-style ("Smart Brevity") digest. This skill
backs both the `run-digest` workflow (over saved topics) and freeform digest
requests (an ad-hoc topic the user describes).

## Resolve the topics

- **Workflow / saved digest:** read `digest_id` from `workflow_input` (default
  `default`). Call `read_digests` with that `digest_id` to get its ordered topics.
  If it resolves to no topics, stop and reply: "No topics yet — run
  `/workflow run interview-user` to set up your interests." Do not call `AskUser`.
- **Freeform:** build a single ad-hoc topic from the user's request (pick a label,
  intent, sensible `recency_days` and `max_items`, and any sources they named).
  Omit `digest_id` when recording it.

## Open the run

Call `start_digest_run` once with a `title` (the bundle label, or the freeform
topic label) and, if you can frame it up front, a `lead` — the "1 big thing", the
single most important item across all topics, in 2–3 sentences. Include `digest_id`
for a saved bundle; omit it for a freeform digest. Keep the returned `run_id`.

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
  - a **bold one-line headline**,
  - *Why it matters:* one sentence,
  - 1–3 tight bullets ("The big picture", "Between the lines", numbers),
  - **Go deeper:** the source link.
- Tag any open-web fallback items as `(unverified source)`.
- If the topic had nothing net-new, make the card one line saying it was quiet.

Cite every claim with its link. Never invent sources or facts.

## 5. Record the section

Call `append_digest_section` with:

- `run_id`: the id from `start_digest_run`,
- `topic_id`: this topic's id (empty for a freeform digest),
- `heading`: the topic label,
- `content`: this card's rendered markdown,
- `seen`: `{ "urls": [...], "titles": [...] }` for the items in this card (this
  powers skip-seen next time).

Then move to the next topic and repeat steps 1–5. After the last topic, briefly
confirm the digest is ready (the user has seen each card as you wrote it).
