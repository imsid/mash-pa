"""The digest feature: agents, workflows, shared SKILLs, and store.

Exposes the two interactive agents as catalog entries (so they appear in the
store and can be composed into hosts) and the two workflow specs (registered on
the pool by `pa.store.build_pool`). The workflow-only agents are pulled in
automatically when their workflows register, via the bound `TaskSpec.agent_spec`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .agents import (
    digest_concierge,
    digest_curator,
    github_digest,
    interview_user,
    run_digest,
)

if TYPE_CHECKING:
    from mash.workflows import WorkflowSpec

DIGEST_CURATOR_AGENT_ID = digest_curator.DIGEST_CURATOR_AGENT_ID
DIGEST_CONCIERGE_AGENT_ID = digest_concierge.DIGEST_CONCIERGE_AGENT_ID
INTERVIEW_USER_WORKFLOW_ID = interview_user.INTERVIEW_USER_WORKFLOW_ID
RUN_DIGEST_WORKFLOW_ID = run_digest.RUN_DIGEST_WORKFLOW_ID
GITHUB_DIGEST_WORKFLOW_ID = github_digest.GITHUB_DIGEST_WORKFLOW_ID


def build_digest_workflow_specs() -> "list[WorkflowSpec]":
    """The digest workflows, in the order they should appear."""
    return [
        interview_user.build_workflow_spec(),
        run_digest.build_workflow_spec(),
        github_digest.build_workflow_spec(),
    ]


__all__ = [
    "DIGEST_CONCIERGE_AGENT_ID",
    "DIGEST_CURATOR_AGENT_ID",
    "GITHUB_DIGEST_WORKFLOW_ID",
    "INTERVIEW_USER_WORKFLOW_ID",
    "RUN_DIGEST_WORKFLOW_ID",
    "build_digest_workflow_specs",
    "digest_concierge",
    "digest_curator",
]
