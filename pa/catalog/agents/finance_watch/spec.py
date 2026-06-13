"""Finance Watch — a personal agent over your own data.

Watches a local transactions ledger (`$PA_DATA_DIR/transactions.csv`) and
answers questions about odd charges, duplicates, new merchants, and spending
drift. One read-only tool, no credentials, no network: nothing leaves the
deployment. A synthetic sample ledger is seeded on first build so the agent
works out of the box.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.base import ToolResult
from mash.tools.registry import ToolRegistry

from ..._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME

FINANCE_WATCH_AGENT_ID = "finance-watch"
SAMPLE_LEDGER_PATH = Path(__file__).resolve().parent / "transactions.sample.csv"


def pa_data_dir() -> Path:
    raw = os.environ.get("PA_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("~/.pa/data").expanduser()


def ledger_path() -> Path:
    return pa_data_dir() / "transactions.csv"


def seed_sample_ledger() -> None:
    """Copy the synthetic sample ledger into the data dir if none exists."""
    target = ledger_path()
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SAMPLE_LEDGER_PATH, target)


_PROMPT = f"""You are Finance Watch in {APP_NAME}: a personal finance watcher
over a local transactions ledger. The ledger lives on this deployment and
nothing you read leaves it.

How to work:
- Use `read_ledger` to fetch transactions (optionally date-bounded), then
  analyze the rows yourself. Never invent transactions; cite dates, merchants,
  and amounts from the ledger when you flag something.
- Things worth flagging: duplicate charges (same merchant, amount, and date),
  merchants that have never appeared before, price changes on recurring
  charges (subscriptions, memberships), and amounts far outside a merchant's
  or category's usual range.
- Answer concisely. For summaries, total by category and call out the
  notable lines rather than reciting every row.
- If the ledger is missing, explain that this deployment keeps it at
  `$PA_DATA_DIR/transactions.csv` and that a sample is seeded on startup.
"""


class ReadLedgerTool:
    """Read-only access to the local transactions ledger."""

    name = "read_ledger"
    requires_approval = False
    description = (
        "Read transactions from the local ledger CSV "
        "(columns: date, merchant, category, amount). Optionally bound by "
        "ISO dates. Returns matching rows with the header."
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Earliest date to include (YYYY-MM-DD).",
            },
            "end_date": {
                "type": "string",
                "description": "Latest date to include (YYYY-MM-DD).",
            },
        },
        "additionalProperties": False,
    }

    async def execute(self, args: Dict[str, Any]) -> ToolResult:
        path = ledger_path()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ToolResult.error(
                f"No ledger found at {path}. Place a transactions CSV there "
                "(columns: date, merchant, category, amount)."
            )
        if not lines:
            return ToolResult.error(f"Ledger at {path} is empty.")

        start = str(args.get("start_date") or "").strip()
        end = str(args.get("end_date") or "").strip()
        header, rows = lines[0], lines[1:]
        # ISO dates compare correctly as strings.
        selected = [
            row
            for row in rows
            if row.strip()
            and (not start or row.split(",", 1)[0] >= start)
            and (not end or row.split(",", 1)[0] <= end)
        ]
        if not selected:
            return ToolResult.success(
                f"{header}\n(no transactions in the requested range)"
            )
        return ToolResult.success("\n".join([header, *selected]))

    def to_llm_format(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class FinanceWatchSpec(AgentSpec):
    """Personal finance watcher over the local ledger."""

    def get_agent_id(self) -> str:
        return FINANCE_WATCH_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(ReadLedgerTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        return SkillRegistry()

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=FINANCE_WATCH_AGENT_ID,
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
        )

    def build_system_prompt(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": _PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def build_agent_config(self) -> AgentConfig:
        return AgentConfig(
            app_id=FINANCE_WATCH_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=False,
            max_steps=10,
            temperature=0.2,
        )


def create_spec(*, workspace_root: str) -> FinanceWatchSpec:
    del workspace_root  # personal agents do not operate on a code workspace
    seed_sample_ledger()
    return FinanceWatchSpec()


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="Finance Watch",
        description=(
            "Personal finance watcher over a local transactions ledger; "
            "flags odd charges, duplicates, new merchants, and spending "
            "drift. Data never leaves the deployment."
        ),
        capabilities=[
            "transaction anomaly detection",
            "duplicate charge detection",
            "subscription price-change tracking",
            "spending summaries by category",
        ],
        usage_guidance=(
            "Use for questions about personal spending: odd or duplicate "
            "charges, new merchants, subscription changes, or category "
            "summaries over the local ledger."
        ),
    )
