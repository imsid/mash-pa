# Contributing to PA

This guide covers local development, running the host with Docker Compose,
adding an agent to the catalog, and releasing standalone CLI binaries.

## Local Development

This is the loop for working on the catalog, the CLI, or the specs: run the
host from source so code changes don't need an image rebuild.

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages Python and the venv)
- Docker (for Postgres)
- An Anthropic API key

### Setup

```bash
cd mash-pa
uv sync                              # create the venv
docker compose up -d db              # Postgres only, published on 127.0.0.1:5434
cp .env.example .env
```

In `.env`, set `ANTHROPIC_API_KEY` and uncomment the local-development line:

```
MASH_DATABASE_URL=postgresql://mash:mash@127.0.0.1:5434/mash_pa
```

The database is `mash_pa` with an underscore — everything else in this
project is `mash-pa` with a hyphen, so this is an easy one to typo (Postgres
will report `database "mash-pa" does not exist`).

`GITHUB_MCP_PAT` is optional: a GitHub personal access token (generate one
at **Settings → Developer settings → Personal access tokens**, `repo` scope)
that powers the `github-digest` workflow (read-only). Without it the workflow
still runs; it reports itself unconfigured.

Do not quote values in `.env` — `python-dotenv` treats quotes as literal
characters.

### Run

```bash
mash host serve --host-app pa.spec:build_pool --port 8002
```
Then, in another terminal:

```bash
pa browse                  # the pool + configured hosts
pa repl --host assistant   # enter the default composition
```

The CLI defaults to `http://127.0.0.1:8002`.

## The Docker Image

The published image (`ghcr.io/imsid/mash-pa`) is dual-mode, selected by
`MASH_DATABASE_URL` in `docker-entrypoint.sh`:

- **unset** — single-container mode: the entrypoint initializes and starts
  an embedded Postgres on the data volume (`$PA_DATA_DIR/pg`), then runs the
  host. This is the README quick start.
- **set** — external-database mode: the embedded Postgres is skipped
  entirely and the host connects to yours.

`docker compose up -d` runs the external-database mode locally: one Postgres
container plus the PA host built from source (`cp .env.example .env` first).

`GET /api/v1/health` reports readiness, useful as a probe if you put the
container behind a reverse proxy or orchestrator.

## Adding an Agent to the Catalog

Adding an agent to the store is adding a package under `pa/catalog/agents/`
and one entry to the `CATALOG` tuple.

1. **Create the package.** A directory under `pa/catalog/agents/<name>/`
   with a `spec.py` implementation and an `__init__.py` that re-exports the
   agent id plus two callables:

   ```python
   def create_spec(*, workspace_root: str) -> AgentSpec: ...
   def build_metadata() -> AgentMetadata: ...
   ```

   The spec is a standard Mash `AgentSpec` (tools, LLM, system prompt,
   config). `finance_watch` is the smallest complete example; the
   `github-digest` workflow agent (`pa/catalog/digest/agents/github_digest/`)
   shows the MCP pattern.

2. **Write the listing carefully.** The `AgentMetadata` is both the store
   listing `pa browse` renders and the delegation directory a primary reads
   when your agent serves as a subagent. Vague `usage_guidance` produces
   vague routing.

3. **Register it.** Add one `CatalogEntry` to `CATALOG` in
   `pa/catalog/__init__.py`.

4. **Degrade gracefully.** If the agent needs credentials, register it
   unconditionally and gate the capability: return `[]` from
   `build_mcp_servers()` when unconfigured and let the system prompt explain
   what to set (see the `github-digest` workflow agent). The catalog should
   always be fully browsable.

5. **Ship data files as package data.** Add globs to
   `[tool.setuptools.package-data]` in `pyproject.toml` (see the
   `finance_watch` sample ledger) so the Docker `pip install .` includes
   them.

Rebuild the deployment (`docker compose build pa && docker compose up -d`)
and the new listing appears in `pa browse`, ready to be composed into hosts.

## Releasing CLI Binaries

Tag a version to build and publish standalone CLI binaries:

```bash
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions builds `pa` binaries for macOS (arm64) and Linux (x86_64) via
PyInstaller and uploads them to a GitHub Release. The same tag also triggers
the Docker workflow, which publishes the multi-arch (amd64 + arm64) image to
`ghcr.io/imsid/mash-pa` tagged `latest` and the version. One-time setup:
after the first push, set the GHCR package to public in the repo's package
settings so `docker run` works without authentication.

The install script (`install.sh`) always fetches the latest release:

```bash
curl -fsSL https://raw.githubusercontent.com/imsid/mash-pa/main/install.sh | sh
```

## Architecture

PA is a standard Mash application:

- `pa/catalog/` — The agent catalog: each package under `agents/` is one
  store listing, registered through the explicit `CATALOG` tuple in
  `catalog/__init__.py`
- `pa/spec.py` — `build_pool()`: registers the catalog as a flat pool (no
  built-in hosts)
- `pa/cli.py` — Standalone CLI, defaulting to `http://127.0.0.1:8000`
- `pa/store.py` — The host config file (`~/.pa/hosts.json`): the source of
  truth for compositions, seeded with `assistant`, published to the
  deployment on REPL entry

The deployment is a flat pool of two personal agents with no built-in host
compositions. Hosts are configuration: the CLI's config file holds them
(seeded with the `assistant` composition), and entering a REPL publishes
them over the host control API (`PUT /v1/hosts/{id}`, idempotent). Requests
routed through a host (`POST /v1/hosts/{id}/request`) give the primary an
`InvokeSubagent` tool and a directory of that host's subagents; bare
requests to any agent run it alone. Subagent delegation, tool approval, and
durable interactions are handled by the Mash runtime. See the
[mashpy docs](https://github.com/imsid/mashpy) for framework details.
