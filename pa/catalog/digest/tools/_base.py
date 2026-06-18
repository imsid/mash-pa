"""Shared tool surface for the digest tools.

Every digest tool is a thin wrapper around `_store` that returns a `ToolResult`
and follows the same shape as `finance_watch`'s `ReadLedgerTool` (`name`,
`description`, `parameters`, async `execute`, `to_llm_format`). This module holds
what they all share; the tools themselves live in the sibling modules grouped by
domain (`topics`, `digests`, `runs`, `rss_feeds`).
"""

from __future__ import annotations

import json
from typing import Any, Dict

from mash.tools.base import ToolResult


def _ok(payload: Any) -> ToolResult:
    return ToolResult.success(json.dumps(payload, ensure_ascii=False, default=str))


class _BaseTool:
    """Shared tool surface: name, description, schema, and LLM formatting."""

    requires_approval = False
    parallel_safe = True
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    def to_llm_format(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }
