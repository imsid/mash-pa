# PA

A self-hosted app store for **personal agents**, built with the
[Mash](https://github.com/imsid/mashpy) SDK. 

It is a catalog of personal assistant agents you compose into hosts that help run *your* day.

Run the store on your laptop or your own server.

## Quick Start

```bash
# 1. Start your store — one container, embedded Postgres included
docker run -d --name pa -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e YOUTUBE_API_KEY=AIza... \
  -e GITHUB_MCP_PAT=ghp_... \
  -v pa-data:/var/lib/pa \
  ghcr.io/imsid/mash-pa:latest

# 2. Install the CLI
curl -fsSL https://raw.githubusercontent.com/imsid/mash-pa/main/install.sh | sh

# 3. See available agents in the store
pa browse

# 4. Compose a host called assistant
```bash
pa compose assistant --primary digest-curator \
  --subagents digest-concierge,finance-watch \
  --workflows interview-user,run-digest,github-digest
```

# 5. Interact via commands or free form text
pa repl --host assistant
```

`GITHUB_MCP_PAT` lights up the `github-digest` workflow (read-only GitHub
access); omit it and running the workflow just explains how to configure
itself. The `pa-data` volume keeps the database and your ledger durable
across container restarts and upgrades.

The CLI defaults to `http://127.0.0.1:8002`; point it at a store running
elsewhere with `--api-base-url` or `PA_API_BASE_URL`. To bring your own
Postgres instead of the embedded one, set `MASH_DATABASE_URL` on the
container — that's all the [docker compose setup](CONTRIBUTING.md) does.

## The Catalog

Three pooled agents ship with the listing metadata that powers both the
storefront and delegation routing:

| Agent | Listing |
|-------|---------|
| `digest-curator` | Curates the public web into Axios-style digests on your topics — every claim linked — and pulls new uploads from followed YouTube creators and podcast episode drops via RSS. Runs freeform or over your saved topics |
| `digest-concierge` | Manages your digest interests — add/edit/remove topics, follow YouTube creators and podcasts, and compose named digests |
| `finance-watch` | A local transactions ledger — odd charges, duplicates, subscription drift. No credentials, no network; data never leaves the deployment |

Three workflows ship alongside them: `interview-user` (the onboarding interview),
`run-digest` (generate a run from a saved digest), and `github-digest` (snapshot
your GitHub world — PRs awaiting review, your open PRs, assigned issues, recent repo
activity — as a digest, via the read-only GitHub MCP allowlist).

## Composing Teams

The pool is flat — which agents work together is your configuration, not
the deployment's. `pa browse` shows the pool and your configured hosts;
`pa compose` creates or replaces one; `pa repl --host` enters it.

The host config file (`~/.pa/hosts.json`) ships with one default entry, the
**`assistant`** host: `digest-curator` as the primary, with `digest-concierge`
and `finance-watch` as subagents, and the `interview-user`, `run-digest`, and
`github-digest` workflows attached. In its REPL, digest requests are handled
directly, interest edits and spending questions are delegated, and the GitHub
snapshot runs as a workflow:

```text
> build me a digest on AI agents from OpenAI, Anthropic, and Google
> add a topic that follows NPR headlines
> any duplicate charges this month?
> /workflow run github-digest
```

If you already have a `~/.pa/hosts.json` from an earlier version, re-create the
default layout with:

```bash
pa compose assistant --primary digest-curator \
  --subagents digest-concierge,finance-watch \
  --workflows interview-user,run-digest,github-digest
```

```bash
pa repl --host assistant
```

Inside `pa repl --host <id>` everything is scoped to that host: plain
messages route to its primary, delegation is limited to its subagents, and
`/agents` lists exactly the team you composed.

## Digests

The digest agents learn your interests once, then turn fresh web content into an
Axios-style ("Smart Brevity") digest — a "1 big thing" lead, then per item a
headline, *why it matters*, a few bullets, and a source link.

```text
> /workflow run interview-user                 # short interview, saves your topics
> /workflow run run-digest                      # generate your default digest
> /workflow run run-digest --input {"digest_id":"work"}   # a specific saved digest you composed
> /workflow run github-digest                   # snapshot your GitHub world (read-only)
> build me a digest on RISC-V servers           # freeform, any topic, any time
> /interests                                    # view saved topics and digests
> /interests reset                              # clear and re-run the interview
> /digest                                       # the latest generated digest
> /digest list 5                                # recent digests
> /digest search agents                         # full-text search past digests
```

Topics carry trusted `sources` (a domain allowlist) and a recency window; the
curator searches those first and falls back to the open web when they're thin,
skipping items already surfaced. Topics, named digests, and every generated
digest run are stored in the deployment's Postgres database (`MASH_DATABASE_URL`,
required); web search/fetch use Parallel AI (`PARALLEL_API_KEY`, optional — the
free anonymous tier works without it). `/digest` reads the database directly, so
run it where `MASH_DATABASE_URL` is reachable.

`github-digest` is a digest too, just from a different source: it snapshots your
GitHub world via the read-only GitHub MCP allowlist (`GITHUB_MCP_PAT`) and records
it alongside the rest, so it shows up in `/digest` like any other — but as a
current-state snapshot it does not skip already-seen items.

## The Agents

PA ships two kinds of agent: **pooled agents** you talk to directly — a primary
and its subagents — and **workflow agents** you trigger with `/workflow run`.

### Pooled agents

**Digest Curator** is the `assistant` primary: it curates the public web into
Axios-style digests on your topics (or any freeform topic), citing every claim,
and records each digest for `/digest` to view and search. It delegates interest
edits to Digest Concierge.

**Digest Concierge** manages what your digests cover — add, edit, or remove
topics and compose named digests — over the shared digest store.

**Finance Watch** is a subagent over a local transactions ledger at
`$PA_DATA_DIR/transactions.csv` — flagging duplicate charges, new merchants,
subscription price changes, and outliers — with no credentials and no network, so
the data never leaves the deployment. A synthetic sample ledger is seeded on first
start so it works out of the box, and Digest Curator delegates spending questions
to it.

### Workflow agents

**Interview User** (`/workflow run interview-user`) is a short onboarding
interview that saves your interests — topics, followed YouTube creators and
podcasts, and a starter digest.

**Run Digest** (`/workflow run run-digest`) generates an Axios-style digest over a
saved digest (your `default`, or a named `digest_id`), recorded for `/digest`.

**GitHub Digest** (`/workflow run github-digest`) snapshots your GitHub world — PRs
awaiting your review, your open PRs, assigned issues, recent repo activity —
through the GitHub MCP server with a read-only tool allowlist, and writes it as a
digest you can view and search like any other (set `GITHUB_MCP_PAT` in `.env`;
without it the run just explains how to configure itself). Because it is a
current-state snapshot it does not skip already-seen items the way topic and feed
digests do.

## CLI Commands

| Command | Description |
|---------|-------------|
| `pa browse` | Browse the agent pool, the attachable workflows, and your configured hosts |
| `pa compose <host-id> --primary <agent> [--subagents a,b]` | Compose agents into a host (define-or-replace) |
| `pa hosts` | List the hosts in your config file |
| `pa repl --host <id>` | Enter a host's REPL, scoped to its team (`--agent <id>` for one bare agent) |
| `pa serve` | Run your own PA host from a source install |

Inside a host REPL, alongside the stock mash commands (`/workflow`, `/agents`,
`/feedback`, …), PA adds `/interests` (view or reset your digest interests) and
`/digest` (view, list, or search past digests).

The stock mash CLI drives the same deployment: `mash connect` /
`mash compose` / `mash repl`.

## Telemetry

The host serves a telemetry UI for real-time visibility into agent execution
at [http://127.0.0.1:8000/telemetry](http://127.0.0.1:8000/telemetry) (or
`/telemetry` on whatever host you deployed).

## Development & Deployment

See [CONTRIBUTING.md](CONTRIBUTING.md) for local development, Docker Compose
deployment, adding an agent to the catalog, and releasing CLI binaries.
