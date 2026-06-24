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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-2026-03-05")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

# Open-source model config (Gemma over OpenRouter's Chat Completions wire).
# The lighter management agents — digest-concierge, interview-user — run on
# Gemma to save frontier spend; the web-research agents stay on Anthropic for
# output quality. Defaults to the paid Gemma 4 endpoint (~$0.12/M in, $0.35/M
# out — cents per run): unlike the `:free` pool, it has backends that reliably
# advertise tool-call support, which the management agents depend on. The free
# tier intermittently routed to backends without a tool-call parser, leaking raw
# tool tokens and dropping the call mid-workflow.
OSS_BASE_URL = os.getenv("OSS_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "google/gemma-4-31b-it")


# Web search provider credential. The web-research digest agents back their
# `web_search`/`web_fetch` tools with Parallel AI; unset leaves web search off.
PARALLELAI_API_KEY = os.getenv("PARALLELAI_API_KEY")
