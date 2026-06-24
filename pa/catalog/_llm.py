"""LLM provider helpers for the PA agents.

The lighter management agents (digest-concierge, interview-user) run on Gemma
over OpenRouter. OpenRouter load-balances the same model across multiple backend
providers, and not all of them serve Gemma with a tool-call parser — when a
request lands on one that doesn't, Gemma's native tool-call tokens leak into the
message text, the harness sees no `tool_calls`, and the turn ends early (a tool
call silently dropped).

Two stock `OSSCompatibleProvider` controls (mashpy >= 0.6.4) guard against that,
so no provider subclass is needed:

- `default_provider_options` pins OpenRouter routing to backends that advertise
  support for the request's parameters (`tools` included), via
  `provider.require_parameters`.
- `on_tool_call_leak="raise"` turns a leaked tool call into a visible error
  rather than a silently dropped call that ends a workflow early.
"""

from __future__ import annotations

from typing import Any

from mash.core.llm import GeminiProvider, GemmaProvider, LLMProvider

from ._base import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMMA_MODEL,
    OPENROUTER_API_KEY,
    OSS_BASE_URL,
)

# OpenRouter provider-routing preferences, merged into every request's
# `provider_options`. `require_parameters` restricts routing to backends that
# support all parameters in the request — crucially `tools` — which excludes
# those that accept the field but lack a tool-call parser.
_OPENROUTER_OPTIONS: dict[str, Any] = {
    "extra_body": {"provider": {"require_parameters": True}}
}


def build_gemma_llm(app_id: str) -> LLMProvider:
    """Build the Gemma provider used by the PA management agents.

    Routing is pinned to tool-call-capable backends, and a leaked tool call is
    raised rather than silently dropped.
    """
    return GemmaProvider(
        app_id=app_id,
        model=GEMMA_MODEL,
        base_url=OSS_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_provider_options=_OPENROUTER_OPTIONS,
        on_tool_call_leak="raise",
    )


def build_gemini_llm(app_id: str) -> LLMProvider:
    """Build the Gemini provider used by the digest-curator.

    Runs on a Gemini frontier model over Google's Interactions API. The provider
    rewrites the agent's `web_search`/`web_fetch` tools into Gemini's native
    server-side `google_search`, so grounding comes from Google directly.
    """
    return GeminiProvider(
        app_id=app_id, model=GEMINI_MODEL, api_key=GEMINI_API_KEY, web_search=True
    )
