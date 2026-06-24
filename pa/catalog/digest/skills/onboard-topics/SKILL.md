---
name: onboard-topics
description: Interview the user about their interests and save them as digest topics and a starter digest.
---

# Onboard Topics

Use this skill to learn what the user wants digests about and persist it. It runs
both on first use and when the user resets their interests. Keep it short and
targeted — interests are meant to evolve, not be exhaustive.

## Reset

If the request (or `workflow_input`) carries `reset: true`, call `clear_interests`
**first**, then run the interview from scratch.

## Interview

Ask **no more than 4–5** questions with `AskUser`, one at a time. Use the
`options` argument for choices; omit it for free-form answers. Cover:

1. The 2–4 subjects they want to follow (free-form). Example answers: "AI agents
   from the big labs", "US national news", "what's trending".
2. For subjects where it matters, which **sources** they trust (free-form, e.g.
   "openai.com, anthropic.com, deepmind.google", "npr.org"). It is fine to leave a
   subject open to the whole web — that becomes an empty source list.
3. Any specific **YouTube creators or podcasts** they want to follow (free-form,
   e.g. "Lex Fridman on YouTube", "the Acquired podcast"). Optional — fine to skip.
4. How fresh items must be (offer options like "last 1 day", "last 3 days",
   "last 7 days").
5. How many items per subject (offer options like "3", "5", "8").

Do not over-ask. Infer sensible specifics from their answers rather than
interrogating every field.

## Normalize and save

Turn the answers into one topic per subject and call `write_topics` with:

- `id`: short kebab-case slug (e.g. `ai-agents`, `us-news`, `trending`).
- `label`: a human title (e.g. "AI agents from the big labs").
- `intent`: a one-line search brief describing exactly what to look for, written
  so the curator can act on it (e.g. "Blog, engineering, and launch posts about AI
  agents from OpenAI, Anthropic, and Google").
- `sources`: the trusted domains for the topic, or `[]` for open-web topics.
- `recency_days`: integer from their freshness answer.
- `max_items`: integer from their count answer.

For each creator or podcast they named, call `subscribe_rss_feed` with:

- `kind`: `youtube_channel` or `podcast`.
- `source`: what they gave — a @handle/channel URL/name for YouTube, a show name
  or RSS URL for a podcast.
- `recency_days` / `max_items`: reuse their freshness and count answers.

It resolves and returns the feed (note its `id`). If a podcast cannot be resolved,
mention it may be a Spotify exclusive with no public RSS and move on.

Then call `write_digest` to create the starter digest (omit `digest_id` — it is
generated and returned):

- `label`: e.g. "Daily digest"
- `topic_ids`: every topic id you just wrote, in the order they should appear.
- `rss_feed_ids`: the ids of the creators/podcasts you followed (omit or `[]` if
  none).

## Confirm

Summarize back the topics and the starter digest in a short list, and tell the
user they can generate it any time with `/workflow run run-digest`, edit interests
conversationally, or view them with `/interests`.
