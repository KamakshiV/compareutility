"""Shared optional LLM calls for pipeline agents (gated by USE_LLM_SUMMARY + OPENAI_API_KEY)."""

from __future__ import annotations

from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from app.config import get_settings


def _chat_model() -> AzureChatOpenAI | ChatOpenAI:
    s = get_settings()
    key = s.openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    if s.openai_api_base and s.openai_deployment_name and s.openai_api_version:
        return AzureChatOpenAI(
            azure_endpoint=s.openai_api_base,
            api_key=key,
            api_version=s.openai_api_version,
            azure_deployment=s.openai_deployment_name,
        )
    return ChatOpenAI(api_key=key, model="gpt-4o-mini")


def pipeline_llm_complete(
    system: str,
    user: str,
    *,
    max_user_chars: int = 8000,
) -> Optional[str]:
    """
    When USE_LLM_SUMMARY is false: return None (callers omit LLM-enriched fields).

    When true: return model text, or a short skip/error string (never raises).
    """
    s = get_settings()
    if not s.use_llm_summary:
        return None
    if not s.openai_api_key:
        return "LLM skipped: OPENAI_API_KEY not set."
    body = user[:max_user_chars]
    try:
        llm = _chat_model()
        out = llm.invoke([SystemMessage(content=system), HumanMessage(content=body)])
        return out.content if hasattr(out, "content") else str(out)
    except Exception as e:
        return f"LLM error: {e}"
