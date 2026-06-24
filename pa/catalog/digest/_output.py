"""Structured output schema for digest workflows.

Digest workflows (`run-digest`, `github-digest`) write their digest to the store
one section at a time, then return this structured payload as the task's
`structured_output`. The CLI is a dumb renderer of it: it prints the title, lead,
and sections, then composes the `/digest <digest_id> <run_id>` review command from
the two ids. mash's built-in `finalize_structured_output` step fills the schema
from the conversation — the ids come from `start_digest_run` and each section's
heading/content from the `append_digest_section` calls — so it echoes what was
written rather than re-summarizing.
"""

from __future__ import annotations

DIGEST_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "digest_id": {"type": "integer"},
        "run_id": {"type": "integer"},
        "title": {"type": "string"},
        "lead": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer"},
                    "heading": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["position", "heading", "content"],
            },
        },
    },
    "required": ["digest_id", "run_id", "title", "lead", "sections"],
}
