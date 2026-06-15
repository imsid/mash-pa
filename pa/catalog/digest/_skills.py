"""Shared SKILL registration for the digest agents.

The two SKILLs live once under `pa/catalog/digest/skills/` and are loaded by both
the interactive specs and the workflow-only specs, so the curate/onboard pipeline
is defined in a single place.
"""

from __future__ import annotations

from pathlib import Path

from mash.skills.base import Skill

_SKILLS_ROOT = Path(__file__).resolve().parent / "skills"

ONBOARD_TOPICS_SKILL = "onboard-topics"
CURATE_DIGEST_SKILL = "curate-digest"


def skill(name: str, description: str) -> Skill:
    return Skill(
        type="custom",
        name=name,
        description=description,
        location=str(_SKILLS_ROOT / name),
    )
