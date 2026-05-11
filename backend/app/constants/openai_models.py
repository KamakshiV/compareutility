"""Allowed OpenAI chat model ids for per-job LLM calls (USE_LLM_SUMMARY)."""

from __future__ import annotations

# Curated list for dropdown + API validation. Extend as OpenAI adds models.
OPENAI_CHAT_MODEL_IDS: tuple[str, ...] = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-mini",
    "o1-preview",
    "o1",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
)

DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini"
