from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Reconiq API"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://compare:compare@127.0.0.1:5433/reconiq"

    # Local storage root (POC)
    storage_local_path: str = "./data/storage"

    # Azure Blob (optional)
    azure_storage_connection_string: Optional[str] = None
    azure_container_name: str = "comparisons"

    # OpenAI / Azure OpenAI
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None  # Azure: https://<resource>.openai.azure.com/
    openai_api_version: Optional[str] = None  # Azure: e.g. 2024-08-01-preview
    openai_deployment_name: Optional[str] = None  # Azure deployment name

    use_llm_summary: bool = False  # env: USE_LLM_SUMMARY
    # Structured LLM discrepancy pass (post-reconciliation); can be on without USE_LLM_SUMMARY
    use_llm_discrepancy_identification: bool = False  # env: USE_LLM_DISCREPANCY_IDENTIFICATION

    # Comma-separated origins for browser clients (add your Vercel preview / production URL).
    # Include every origin you open the UI from (port matters): Vite dev 5173, preview 4173, LAN IPs, etc.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
