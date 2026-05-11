"""Shared optional LLM calls for pipeline agents (gated by USE_LLM_SUMMARY + OPENAI_API_KEY)."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.config import get_settings
from app.constants.openai_models import DEFAULT_OPENAI_CHAT_MODEL

logger = logging.getLogger(__name__)

# Human-readable labels for logs ("Starting LLM service for <purpose> via Agent …").
_DEFAULT_PURPOSE_FOR_STAGE: dict[str, str] = {
    "ingestion": "ingestion readiness review",
    "schema_profiler": "schema and comparison-mode profiling",
    "mapping": "column mapping guidance",
    "rules": "reconciliation rules explanation",
    "insight": "comparison result summarization",
    "pipeline": "pipeline LLM step",
}


def _resolve_purpose(stage: str, purpose: Optional[str]) -> str:
    if purpose and purpose.strip():
        return purpose.strip()
    return _DEFAULT_PURPOSE_FOR_STAGE.get(stage, stage.replace("_", " "))


def _chat_model(chat_model_id: Optional[str] = None) -> Any:
    """Load OpenAI/Azure client only when an LLM call is about to run."""
    from langchain_openai import AzureChatOpenAI, ChatOpenAI

    s = get_settings()
    key = s.openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    requested = (chat_model_id or "").strip()
    if s.openai_api_base and s.openai_deployment_name and s.openai_api_version:
        deployment = requested or (s.openai_deployment_name or "").strip()
        if not deployment:
            raise RuntimeError("Azure OpenAI requires OPENAI_DEPLOYMENT_NAME or a job-selected model id")
        return AzureChatOpenAI(
            azure_endpoint=s.openai_api_base,
            api_key=key,
            api_version=s.openai_api_version,
            azure_deployment=deployment,
        )
    model = requested or DEFAULT_OPENAI_CHAT_MODEL
    return ChatOpenAI(api_key=key, model=model)


def pipeline_llm_complete(
    system: str,
    user: str,
    *,
    stage: str = "pipeline",
    purpose: Optional[str] = None,
    max_user_chars: int = 8000,
    chat_model_id: Optional[str] = None,
) -> Optional[str]:
    """
    When USE_LLM_SUMMARY is false: return None (callers omit LLM-enriched fields).

    When true: return model text, or a short skip/error string (never raises).

    ``purpose`` is the human-facing LLM service name in logs; defaults by ``stage``.
    """
    s = get_settings()
    svc_purpose = _resolve_purpose(stage, purpose)
    if not s.use_llm_summary:
        return None
    if not s.openai_api_key:
        logger.info(
            "Skipped LLM service for %r via Agent [%s]: OPENAI_API_KEY not set",
            svc_purpose,
            stage,
        )
        return "LLM skipped: OPENAI_API_KEY not set."
    body = user[:max_user_chars]
    use_azure = bool(
        s.openai_api_base and s.openai_deployment_name and s.openai_api_version
    )
    backend = "azure_openai" if use_azure else "openai"
    model_note = (chat_model_id or "").strip() or "(default)"
    logger.info(
        'Starting LLM service for "%s" via Agent [%s] (backend=%s model=%s system_chars=%s user_chars=%s)',
        svc_purpose,
        stage,
        backend,
        model_note,
        len(system),
        len(body),
    )
    from langchain_core.messages import HumanMessage, SystemMessage

    t0 = time.perf_counter()
    try:
        llm = _chat_model(chat_model_id)
        out = llm.invoke([SystemMessage(content=system), HumanMessage(content=body)])
        content = out.content if hasattr(out, "content") else str(out)
        text = content if isinstance(content, str) else str(content)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            'Finished LLM service for "%s" via Agent [%s]: success elapsed_ms=%.1f response_chars=%s',
            svc_purpose,
            stage,
            elapsed_ms,
            len(text),
        )
        return text
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            'Finished LLM service for "%s" via Agent [%s]: error elapsed_ms=%.1f error=%s',
            svc_purpose,
            stage,
            elapsed_ms,
            str(e)[:500],
        )
        return f"LLM error: {e}"
