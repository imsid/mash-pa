"""Interview User — the onboarding workflow agent.

A workflow-only agent: the `interview-user` workflow runs it to interview the user
about their interests (via durable `AskUser` interactions) and persist them as
topics plus a `default` bundle. It honors a `reset` flag for re-onboarding. The
interview script and normalization rules are the shared `onboard-topics` skill.
"""

from __future__ import annotations

from typing import Any

from mash.core.config import AgentConfig
from mash.core.llm import LLMProvider
from mash.core.llm.anthropic import AnthropicProvider
from mash.runtime import AgentMetadata, AgentSpec
from mash.skills.registry import SkillRegistry
from mash.tools.ask_user import AskUserTool
from mash.tools.registry import ToolRegistry
from mash.workflows import TaskSpec, WorkflowSpec, WorkflowTaskMessageSpec

from ...._base import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, APP_NAME
from ..._skills import ONBOARD_TOPICS_SKILL, skill
from ..._tools import (
    ClearInterestsTool,
    ReadDigestsTool,
    ReadTopicsTool,
    WriteDigestTool,
    WriteTopicsTool,
)

INTERVIEW_USER_AGENT_ID = "interview-user"
INTERVIEW_USER_WORKFLOW_ID = "interview-user"
INTERVIEW_USER_TASK_ID = "interview"

_PROMPT = f"""You are the onboarding interviewer in {APP_NAME}. Your job is to
learn what the user wants digests about and save it.

Run the `{ONBOARD_TOPICS_SKILL}` skill: ask a few targeted questions with
`AskUser`, normalize the answers into topics, call `write_topics`, then create the
`default` bundle with `write_digest`. If the request carries `reset: true`, call
`clear_interests` first. Keep it short — interests evolve. Finish by confirming
what you saved.
"""


class InterviewUserSpec(AgentSpec):
    """Workflow agent that interviews the user and saves their interests."""

    def get_agent_id(self) -> str:
        return INTERVIEW_USER_AGENT_ID

    def build_tools(self) -> ToolRegistry:
        tools = ToolRegistry()
        tools.register(AskUserTool())
        tools.register(ReadTopicsTool())
        tools.register(ReadDigestsTool())
        tools.register(WriteTopicsTool())
        tools.register(WriteDigestTool())
        tools.register(ClearInterestsTool())
        return tools

    def build_skills(self) -> SkillRegistry:
        skills = SkillRegistry()
        skills.register(
            skill(
                ONBOARD_TOPICS_SKILL,
                "Interview the user and save interests as topics and a bundle.",
            )
        )
        return skills

    def build_llm(self) -> LLMProvider:
        return AnthropicProvider(
            app_id=INTERVIEW_USER_AGENT_ID,
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
            app_id=INTERVIEW_USER_AGENT_ID,
            system_prompt=self.build_system_prompt(),
            skills_enabled=True,
            max_steps=20,
            temperature=0.3,
        )


def create_spec() -> InterviewUserSpec:
    return InterviewUserSpec()


def build_workflow_spec() -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=INTERVIEW_USER_WORKFLOW_ID,
        tasks=[TaskSpec(task_id=INTERVIEW_USER_TASK_ID, agent_spec=create_spec())],
        task_message=WorkflowTaskMessageSpec(skill_name=ONBOARD_TOPICS_SKILL),
    )


def build_metadata() -> AgentMetadata:
    return AgentMetadata(
        display_name="Interview User",
        description="Onboarding interview that saves your digest interests.",
        capabilities=["interest onboarding interview"],
        usage_guidance="Run via `/workflow run interview-user`.",
    )
