"""Shared constants for the PA agent specs.

The personal agents are self-contained — each defines its own `AgentSpec`.
All they share is the app name and the LLM provider configuration read from
the environment.
"""

from __future__ import annotations

import os

APP_NAME = "PA"

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
