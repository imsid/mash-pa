"""PA pool assembly: register the catalog as a flat pool.

No hosts are defined here. Compositions are configuration, owned by the
CLI's host config file (`pa.store`) and published over the control API.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from mash.api import MashHostConfig, run_host
from mash.runtime import AgentPool, HostBuilder

from .catalog import CATALOG, build_digest_workflow_specs


def build_pool(workspace_root: Path | None = None) -> AgentPool:
    """Build the PA agent pool from the catalog. The pool ships no host
    compositions; personal agents do not operate on a code workspace, so
    `workspace_root` is accepted for spec-factory compatibility and ignored."""
    resolved_workspace_root = (
        workspace_root or Path(os.environ.get("PA_WORKSPACE_ROOT", "."))
    ).resolve()
    ws = str(resolved_workspace_root)

    builder = HostBuilder()
    for entry in CATALOG:
        builder.agent(
            entry.create_spec(workspace_root=ws), metadata=entry.build_metadata()
        )
    # Digest workflows; their workflow-only task agents register automatically.
    for workflow in build_digest_workflow_specs():
        builder.workflow(workflow)
    return builder.enable_masher(True).build()


def serve(
    *,
    workspace_root: str = ".",
    bind_host: str = "127.0.0.1",
    bind_port: int = 8000,
    api_key: str | None = None,
) -> int:
    """Run the PA host API over the pool. Blocks until shutdown."""
    run_host(
        build_pool(Path(workspace_root).resolve()),
        config=MashHostConfig(
            bind_host=bind_host,
            bind_port=bind_port,
            api_key=api_key,
        ),
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the PA host over the Mash host API."
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Accepted for compatibility; PA agents do not use a workspace.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API bind host.")
    parser.add_argument("--port", type=int, default=8000, help="API bind port.")
    parser.add_argument("--api-key", default=None, help="Optional API key.")
    args = parser.parse_args(argv)

    return serve(
        workspace_root=args.workspace_root,
        bind_host=args.host,
        bind_port=args.port,
        api_key=args.api_key,
    )


if __name__ == "__main__":
    raise SystemExit(main())
