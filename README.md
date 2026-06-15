# PA

Your self-hosted app store for **personal agents**, built with the
[Mash](https://github.com/imsid/mashpy) SDK.

PA is a sibling of [Pilot](https://github.com/imsid/mash-pilot): same
architecture — a catalog of agents you compose into hosts and talk to over
plain HTTP + SSE — but where Pilot is "all things Mash," PA is the agents
that help run *your* day. It plays the app store:

| App store concept | Mash concept | In PA |
|---|---|---|
| The catalog | The agent pool | `pa/catalog/`, registered by `build_pool()` |
| An app listing | `AgentMetadata` | `pa browse` |
| Installing an app | `PUT /v1/hosts/{id}` | `pa compose` |
| An installed app | A `Host` composition | An entry in `~/.pa/hosts.json`, published on connect |
| Launching an app | `POST /v1/hosts/{id}/request` | `pa repl --host <id>` |

The deployment is yours: run the store on your laptop or your own server.

## Quick Start

```bash
# 1. Start your store — one container, embedded Postgres included
docker run -d --name pa -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e GITHUB_MCP_PAT=ghp_... \
  -v pa-data:/var/lib/pa \
  ghcr.io/imsid/mash-pa:latest

# 2. Install the CLI and walk in
curl -fsSL https://raw.githubusercontent.com/imsid/mash-pa/main/install.sh | sh
pa browse                   # see what the store ships
pa repl --host assistant    # enter the default composition
```

`GITHUB_MCP_PAT` lights up the `gh-brief` agent (read-only GitHub access);
omit it and the agent stays in the catalog and explains how to configure
itself. The `pa-data` volume keeps the database and your ledger durable
across container restarts and upgrades.

The CLI defaults to `http://127.0.0.1:8002`; point it at a store running
elsewhere with `--api-base-url` or `PA_API_BASE_URL`. To bring your own
Postgres instead of the embedded one, set `MASH_DATABASE_URL` on the
container — that's all the [docker compose setup](CONTRIBUTING.md) does.

## The Catalog

Two personal agents ship in `pa/catalog/agents/`, each with the listing
metadata that powers both the storefront and delegation routing:

| Agent | Listing |
|-------|---------|
| `digest-curator` | Curates the public web into Axios-style digests on your topics — every claim linked. Runs freeform or over your saved topics |
| `digest-concierge` | Manages your digest interests — add/edit/remove topics and compose named digest bundles |
| `gh-brief` | Your GitHub world — reviews requested, open PRs, assigned issues — via the GitHub MCP server with a read-only tool allowlist |
| `finance-watch` | A local transactions ledger — odd charges, duplicates, subscription drift. No credentials, no network; data never leaves the deployment |

Two workflows ship alongside them: `interview-user` (the onboarding interview)
and `run-digest` (generate a digest over a saved bundle).

## Composing Teams

The pool is flat — which agents work together is your configuration, not
the deployment's. `pa browse` shows the pool and your configured hosts;
`pa compose` creates or replaces one; `pa repl --host` enters it.

The host config file (`~/.pa/hosts.json`) ships with one default entry, the
**`assistant`** host: `digest-curator` as the primary, with `digest-concierge`,
`finance-watch`, and `gh-brief` as subagents, and the `interview-user` and
`run-digest` workflows attached. In its REPL, digest requests are handled
directly and interest edits, spending, and GitHub questions are delegated:

```text
> build me a digest on AI agents from OpenAI, Anthropic, and Google
> add a topic that follows NPR headlines
> any duplicate charges this month?
```

If you already have a `~/.pa/hosts.json` from an earlier version, re-create the
default layout with:

```bash
pa compose assistant --primary digest-curator \
  --subagents digest-concierge \
  --workflows interview-user,run-digest
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
> /workflow run run-digest --input {"digest_id":"work"}   # a named bundle
> build me a digest on RISC-V servers           # freeform, any topic, any time
> /interests                                    # view saved topics and bundles
> /interests reset                              # clear and re-run the interview
> /digest                                       # the latest generated digest
> /digest list 5                                # recent digests
> /digest search agents                         # full-text search past digests
```

Topics carry trusted `sources` (a domain allowlist) and a recency window; the
curator searches those first and falls back to the open web when they're thin,
skipping items already surfaced. Topics, named bundles, and every generated
digest are stored in the deployment's Postgres database (`MASH_DATABASE_URL`,
required); web search/fetch use Parallel AI (`PARALLEL_API_KEY`, optional — the
free anonymous tier works without it). `/digest` reads the database directly, so
run it where `MASH_DATABASE_URL` is reachable.

## The Agents

**Digest Curator** is the `assistant` primary: it curates the public web into
Axios-style digests on your topics (or any freeform topic), citing every claim,
and records each digest for `/digest` to view and search. It delegates interest
edits to Digest Concierge.

**Digest Concierge** manages what your digests cover — add, edit, or remove
topics and compose named bundles — over the shared digest store.

**GH Brief** prepares a compact brief of your GitHub world — PRs awaiting
your review, your open PRs, assigned issues, recent repo activity — through
the GitHub MCP server with a read-only tool allowlist (set `GITHUB_MCP_PAT`
in `.env`; without it the agent stays in the catalog and explains how to
configure itself). As the `assistant` primary it delegates spending
questions to Finance Watch.

**Finance Watch** watches a transactions ledger at
`$PA_DATA_DIR/transactions.csv` — flagging duplicate charges, new merchants,
subscription price changes, and outliers — with no credentials and no
network. A synthetic sample ledger is seeded on first start so it works out
of the box.

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
