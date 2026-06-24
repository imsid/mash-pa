"""PA CLI — the storefront for a PA deployment.

The deployment is a flat pool of agents; which agents work together is your
configuration. Browse the pool with `pa browse`, compose hosts with
`pa compose` (saved to the host config file, see `pa.store`), and enter one
with `pa repl --host <id>` — the REPL is scoped to that host.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
from typing import Any, Sequence

from mash.cli.client import MashHostClient
from mash.cli.commands import Command
from mash.cli.render import RichRenderer
from mash.cli.shell import MashRemoteShell, ShellTarget

from . import store

# Workflows whose final task returns a digest structured output (see
# `pa.catalog.digest._output.DIGEST_OUTPUT_SCHEMA`). For these, the CLI renders
# the digest from that structured output once the run completes.
_DIGEST_WORKFLOW_IDS = frozenset({"run-digest", "github-digest"})

PA_DEFAULT_API_BASE_URL = os.environ.get(
    "PA_API_BASE_URL",
    "http://127.0.0.1:8002",
)


def _resolve_connection(args: argparse.Namespace) -> tuple[str, str | None]:
    base_url = (
        args.api_base_url
        or os.environ.get("MASH_API_BASE_URL")
        or PA_DEFAULT_API_BASE_URL
    ).strip()
    api_key = args.api_key or os.environ.get("MASH_API_KEY") or None
    if not base_url:
        raise ValueError(
            "API base URL is required. Use --api-base-url or PA_API_BASE_URL."
        )
    return base_url, api_key


def _describe_host(client: MashHostClient, host_id: str) -> dict[str, Any]:
    """Fetch the merged view of a published host."""
    try:
        described = client.get_host(host_id)
    except Exception as exc:
        raise ValueError(
            f"host '{host_id}' is not available on this deployment. "
            f"Check `pa hosts` or create it with `pa compose`: {exc}"
        ) from exc
    primary = described.get("primary") or {}
    agent_id = primary.get("agent_id") if isinstance(primary, dict) else None
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError(f"host '{host_id}' did not report a primary agent id")
    return described


def _split_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pa",
        description="PA CLI — your self-hosted app store for personal agents.",
    )
    parser.add_argument("--api-base-url", default=None, help="Mash host base URL")
    parser.add_argument("--api-key", default=None, help="Bearer API key")
    parser.add_argument(
        "--agent",
        default=None,
        help="Target a single agent directly (bare-agent mode, no delegation)",
    )
    subparsers = parser.add_subparsers(dest="command")

    repl = subparsers.add_parser("repl", help="Enter the REPL of a composed host")
    repl.add_argument("--session-id", default=None, help="Remote session id")
    repl.add_argument(
        "--host",
        dest="target_host",
        default=None,
        help="Host to enter (see `pa hosts`)",
    )

    subparsers.add_parser(
        "browse", help="Browse the agent pool and your configured hosts"
    )

    compose = subparsers.add_parser(
        "compose", help="Compose agents into a host (define-or-replace)"
    )
    compose.add_argument("host_id", help="Id for the composition")
    compose.add_argument("--primary", required=True, help="Primary agent id")
    compose.add_argument(
        "--subagents", default=None, help="Comma-separated subagent ids"
    )
    compose.add_argument(
        "--workflows", default=None, help="Comma-separated workflow ids"
    )

    subparsers.add_parser("hosts", help="List the hosts in your config file")

    serve = subparsers.add_parser(
        "serve", help="Run your own PA host (server install required)"
    )
    serve.add_argument(
        "--workspace-root",
        default=os.environ.get("PA_WORKSPACE_ROOT", "."),
        help="Accepted for compatibility; PA agents do not use a workspace",
    )
    serve.add_argument("--host", default="127.0.0.1", help="API bind host")
    serve.add_argument("--port", type=int, default=8000, help="API bind port")
    serve.add_argument(
        "--api-key", dest="api_key", default=None, help="Optional API key to require"
    )
    return parser


def _run_serve(args: argparse.Namespace) -> int:
    # Import by name so the PyInstaller CLI binary does not bundle the
    # server stack; `serve` needs a source or pip install of mash-pa.
    try:
        spec = importlib.import_module("pa.spec")
    except ImportError as exc:
        raise ValueError(
            "`pa serve` requires the full server install, which this "
            "binary does not include. Run it from a source checkout "
            "(`uv pip install -e .`) or start the store with `docker run` "
            f"or `docker compose up`. ({exc})"
        ) from exc
    return spec.serve(
        workspace_root=args.workspace_root,
        bind_host=args.host,
        bind_port=args.port,
        api_key=args.api_key,
    )


def _agent_listing_rows(agents: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for agent in sorted(agents, key=lambda a: str(a.get("agent_id") or "")):
        metadata = agent.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        rows.append(
            [
                str(agent.get("agent_id") or ""),
                str(metadata.get("display_name") or ""),
                str(metadata.get("description") or ""),
            ]
        )
    return rows


def _configured_host_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for host_id, entry in sorted(store.load_hosts().items()):
        rows.append(
            [
                host_id,
                entry["primary"],
                ", ".join(entry["subagents"]),
                ", ".join(entry["workflows"]),
            ]
        )
    return rows


def _render_configured_hosts(renderer: RichRenderer) -> None:
    rows = _configured_host_rows()
    if rows:
        renderer.table(["Host", "Primary", "Subagents", "Workflows"], rows)
    else:
        renderer.info("(no hosts configured)")


def _workflow_rows(workflows: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for workflow in sorted(workflows, key=lambda w: str(w.get("workflow_id") or "")):
        rendered_tasks = []
        for task in workflow.get("tasks") or []:
            if isinstance(task, dict):
                rendered_tasks.append(
                    f"{task.get('task_id') or ''} -> {task.get('agent_id') or ''}"
                )
        rows.append([str(workflow.get("workflow_id") or ""), ", ".join(rendered_tasks)])
    return rows


def _run_browse(client: MashHostClient, renderer: RichRenderer) -> int:
    renderer.info("Agent pool")
    renderer.table(
        ["Agent", "Listing", "Description"], _agent_listing_rows(client.list_agents())
    )
    renderer.info("Workflows (attach with `pa compose ... --workflows <id>`)")
    workflow_rows = _workflow_rows(client.list_workflows())
    if workflow_rows:
        renderer.table(["Workflow", "Tasks"], workflow_rows)
    else:
        renderer.info("(none registered)")
    renderer.info(f"Configured hosts ({store.hosts_file_path()})")
    _render_configured_hosts(renderer)
    renderer.info(
        "Compose a host with `pa compose <host-id> --primary <agent> "
        "--subagents a,b`, then enter it with `pa repl --host <host-id>`."
    )
    return 0


def _run_compose(
    client: MashHostClient, renderer: RichRenderer, args: argparse.Namespace
) -> int:
    subagents = _split_ids(args.subagents)
    workflows = _split_ids(args.workflows)
    client.define_host(
        args.host_id,
        primary=args.primary,
        subagents=subagents,
        workflows=workflows,
    )
    store.record_host(
        args.host_id, primary=args.primary, subagents=subagents, workflows=workflows
    )
    renderer.info(
        f"Composed host '{args.host_id}' (primary {args.primary}, "
        f"{len(subagents)} subagent(s)). Saved to {store.hosts_file_path()}."
    )
    renderer.info(f"Enter it with `pa repl --host {args.host_id}`.")
    return 0


def _run_hosts(renderer: RichRenderer) -> int:
    _render_configured_hosts(renderer)
    renderer.info(
        "Enter one with `pa repl --host <id>`; compose or replace one "
        "with `pa compose`."
    )
    return 0


def _interests_command(shell: MashRemoteShell, ctx: Any, args: list[str]) -> None:
    """View digest interests, or reset and re-run the onboarding interview.

    Deployment-agnostic: routes through the agent/workflow rather than touching
    Postgres directly. Viewing asks the primary to list interests; reset runs the
    `interview-user` workflow with `reset` so it clears and re-interviews.
    """
    if not ctx.host_id:
        ctx.renderer.error("/interests needs a host. Enter one with `pa repl --host <id>`.")
        return
    subcommand = args[0].strip().lower() if args else "show"
    if subcommand in ("", "show", "view", "list"):
        shell.handle_repl_message(
            ctx,
            "List my saved digest topics, the YouTube creators and podcasts I "
            "follow, and my digests.",
        )
        return
    if subcommand == "reset":
        workflow_cmd = shell.command_registry.get("workflow")
        if workflow_cmd is None:
            ctx.renderer.error("Workflow command unavailable.")
            return
        ctx.renderer.info("Resetting interests and re-running onboarding…")
        workflow_cmd.handler(
            ctx, ["run", "interview-user", "--input", '{"reset": true}']
        )
        return
    ctx.renderer.error("Usage: /interests [show|reset]")


def _render_digest_payload(
    renderer: Any, payload: dict, *, show_command: bool = False
) -> None:
    """Dumb-render a digest payload — `{title, lead, sections:[{position,
    heading, content}], digest_id, run_id}` — as markdown. Shared by `/digest`
    and the workflow render (which sets `show_command` to print the re-view
    command). The same shape comes from the store and from a workflow's
    structured output."""
    parts = [f"# {payload.get('title') or ''}"]
    lead = str(payload.get("lead") or "").strip()
    if lead:
        parts.append(f"**1 big thing:** {lead}")
    sections = sorted(
        payload.get("sections") or [], key=lambda s: int(s.get("position") or 0)
    )
    parts.extend(str(s.get("content") or "").strip() for s in sections)
    renderer.markdown("\n\n".join(parts))
    if show_command:
        digest_id = payload.get("digest_id")
        run_id = payload.get("run_id")
        if digest_id is not None and run_id is not None:
            renderer.info(f"View this digest later: /digest {digest_id} {run_id}")


def _digest_command(ctx: Any, args: list[str]) -> None:
    """View past digests directly from the Postgres store (no agent).

    `/digest` latest · `/digest list [N]` · `/digest config` ·
    `/digest <digest_id> <run_id>` · `/digest <run_id>` · `/digest search <query>`.
    """
    # Imported lazily so the CLI (and its PyInstaller binary) does not pull in
    # psycopg and the catalog unless a digest command is actually used.
    from .catalog.digest import _store as digest_store  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    renderer = ctx.renderer

    def _run_table(rows: list[dict]) -> None:
        renderer.table(
            ["ID", "Digest", "Title", "Generated"],
            [
                [
                    str(r["id"]),
                    str(r["digest_id"] or "(freeform)"),
                    str(r["title"]),
                    str(r["generated_at"]),
                ]
                for r in rows
            ],
        )

    def _render_run(run: dict) -> None:
        payload = asyncio.run(digest_store.digest_run_payload(run))
        _render_digest_payload(renderer, payload)

    try:
        sub = args[0].strip().lower() if args else ""
        if sub == "list":
            limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
            rows = asyncio.run(digest_store.list_recent_runs(limit))
            if not rows:
                renderer.info("No digests yet. Generate one with `/workflow run run-digest`.")
                return
            _run_table(rows)
            return
        if sub == "config":
            rows = asyncio.run(digest_store.list_digest_configs())
            if not rows:
                renderer.info(
                    "No digests configured. Set up interests with "
                    "`/workflow run interview-user`."
                )
                return
            renderer.table(
                ["ID", "Label", "Source", "Topics", "Feeds", "Runs", "Last run"],
                [
                    [
                        str(r["id"]),
                        str(r["label"]),
                        str(r["source"]),
                        ", ".join(r["topics"])
                        if r["topics"]
                        else ("(freeform)" if not r["feeds"] else "—"),
                        ", ".join(r["feeds"]) if r["feeds"] else "—",
                        str(r["runs"]),
                        str(r["last_run"] or "—"),
                    ]
                    for r in rows
                ],
            )
            return
        if sub == "search":
            query = " ".join(args[1:]).strip()
            if not query:
                renderer.error("Usage: /digest search <query>")
                return
            rows = asyncio.run(digest_store.search_runs(query, 10))
            if not rows:
                renderer.info(f"No digests match '{query}'.")
                return
            _run_table(rows)
            return
        # `/digest <digest_id> <run_id>` — a run addressed within its digest.
        if len(args) >= 2 and args[0].isdigit() and args[1].isdigit():
            digest_id, run_id = int(args[0]), int(args[1])
            run = asyncio.run(digest_store.get_run_for_digest(digest_id, run_id))
            if run is None:
                renderer.error(f"No run {run_id} in digest {digest_id}.")
                return
            _render_run(run)
            return
        # `/digest <run_id>` — a run by its id alone.
        if sub.isdigit():
            run = asyncio.run(digest_store.get_run(int(sub)))
            if run is None:
                renderer.error(f"No digest run with id {sub}.")
                return
            _render_run(run)
            return
        if sub:
            renderer.error(
                "Usage: /digest [list N | config | search <query> | "
                "<digest_id> <run_id> | <run_id>]"
            )
            return
        latest = asyncio.run(digest_store.latest_run())
        if latest is None:
            renderer.info("No digests yet. Generate one with `/workflow run run-digest`.")
            return
        _render_run(latest)
    except Exception as exc:
        renderer.error(f"/digest failed: {exc}")


def _register_pa_commands(shell: MashRemoteShell) -> None:
    """Register PA-specific slash commands on the REPL shell."""
    shell.register_command(
        Command(
            name="interests",
            help="View your digest interests, or reset them (/interests [show|reset])",
            handler=lambda ctx, args: _interests_command(shell, ctx, args),
        )
    )
    shell.register_command(
        Command(
            name="digest",
            help=(
                "View past digests (/digest [list N | config | search <query> | "
                "<digest_id> <run_id> | <run_id>])"
            ),
            handler=_digest_command,
        )
    )
    # Render each digest workflow's structured output as a digest. mash's default
    # `/workflow run` calls this renderer on the task's `request.completed`, so we
    # no longer fork the command — we just register how to draw the payload.
    def _render_digest_output(_task_id: str, _agent_id: str, data: dict) -> None:
        _render_digest_payload(shell.renderer, data, show_command=True)

    for workflow_id in _DIGEST_WORKFLOW_IDS:
        shell.register_structured_output_renderer(workflow_id, _render_digest_output)


def _run_repl(
    client: MashHostClient,
    renderer: RichRenderer,
    args: argparse.Namespace,
    base_url: str,
) -> int:
    if not args.agent and not args.target_host:
        renderer.info("Pick a host to enter:")
        _render_configured_hosts(renderer)
        renderer.info("Run `pa repl --host <id>`, or `pa compose` to create one.")
        return 0

    if args.agent:
        agent_id, host_id = args.agent, None
    else:
        # Hosts are config: publish them to the deployment (idempotent
        # PUTs), then enter the requested one.
        store.publish_hosts(client, renderer)
        host_id = args.target_host
        described = _describe_host(client, host_id)
        agent_id = described["primary"]["agent_id"].strip()

    target = ShellTarget(
        api_base_url=base_url,
        agent_id=agent_id,
        session_id=args.session_id or MashRemoteShell.new_session_id(),
        host_id=host_id,
    )
    # /agents and /workflow are host-scoped natively by mash >= 0.5.3
    # (default_commands reads ctx.host_id).
    shell = MashRemoteShell(client, target)
    _register_pa_commands(shell)
    shell.run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    renderer = RichRenderer()

    try:
        if args.command == "serve":
            return _run_serve(args)
        if args.command == "hosts":
            return _run_hosts(renderer)
        if args.command in ("repl", "browse", "compose"):
            base_url, api_key = _resolve_connection(args)
            client = MashHostClient(base_url, api_key=api_key)
            try:
                if args.command == "browse":
                    return _run_browse(client, renderer)
                if args.command == "compose":
                    return _run_compose(client, renderer, args)
                return _run_repl(client, renderer, args, base_url)
            finally:
                client.close()
    except Exception as exc:
        renderer.error(str(exc))
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
