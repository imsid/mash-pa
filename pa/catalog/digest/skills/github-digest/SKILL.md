---
name: github-digest
description: Gather the user's GitHub world via the GitHub MCP server and write it as a snapshot digest run.
---

# GitHub Digest

Produce a snapshot of the user's GitHub world — what needs their attention right
now — and write it in the digest format (a run plus sections), so it lands in the
same digest history as every other digest. Your GitHub access is **read-only**: you
cannot comment, merge, or write.

This is a **snapshot, not a feed.** Unlike topic/RSS digests, do **not** skip
already-seen items — a pull request still awaiting review must show up every run.
Record every section with an empty `seen` (`{}`).

## If GitHub is not configured

If the GitHub tools (`get_me`, `search_pull_requests`, …) are not available, this
deployment has no GitHub connection. Open a run titled "Your GitHub world" and write
one section explaining that `GITHUB_MCP_PAT` (a GitHub personal access token) must
be set in the deployment's `.env` and the host restarted, then stop. Do not ask the
user questions.

## Gather

Start with `get_me` to learn who the user is. Then gather, in parallel where you
can:

- **Needs your review:** `search_pull_requests` with `review-requested:@me
  state:open`.
- **Your open PRs:** `search_pull_requests` with `author:@me state:open`.
- **Assigned issues:** `search_issues` with `assignee:@me state:open`.
- **Repo activity** (only if the user named repositories in `workflow_input`):
  `list_commits`, `list_issues`, `list_pull_requests` since yesterday, or the
  window they asked for.

## Open the run

Call `start_digest_run` once with `title` "Your GitHub world" and, if one item
clearly dominates, a `lead` (the single most pressing thing, 2–3 sentences). Omit
`digest_id` — this is not a saved digest. Keep the returned `run_id`.

## Write one section per group

For each group above, in order (most actionable first), write a markdown card and
record it immediately with `append_digest_section`:

- `run_id`: from `start_digest_run`.
- `topic_id`: `""` (this snapshot does not participate in skip-seen).
- `heading`: the group name ("Needs your review", "Your open PRs", "Assigned
  issues", "Repo activity").
- `content`: each item as a tight line — title, repo name, and URL. Say plainly
  when a group is empty (one line, e.g. "Nothing awaiting your review.").
- `seen`: `{}` — always empty for a snapshot.

After the last group, briefly confirm the snapshot is ready.
