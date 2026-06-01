"""Central configuration, loaded from environment / `.env`.

Every setting has a safe default so that imports never fail; only the live agent
genuinely requires ``ANTHROPIC_API_KEY``. This lets the tools, retrieval layer,
eval metrics and tests run in environments without secrets.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for AssetScope."""

    model_config = SettingsConfigDict(
        env_prefix="ASSETSCOPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM backend -------------------------------------------------------
    # "anthropic" (default) or "local"/"openai" for any OpenAI-compatible server
    # (llama.cpp llama-server, Ollama, vLLM, ...).
    llm_backend: str = "anthropic"
    # For the local/openai backend:
    llm_base_url: str = ""          # e.g. http://127.0.0.1:8081/v1
    llm_model: str = "local"        # model name the server expects (often ignored)
    llm_api_key: str = "local"      # dummy bearer for local servers
    llm_max_tokens: int = 1536      # hard cap on generation (keeps CPU runs bounded)
    llm_temperature: float = 0.2

    # --- Anthropic ---------------------------------------------------------
    # The API key is read from the conventional ANTHROPIC_API_KEY (no prefix)
    # to match the Anthropic SDK's own convention.
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-4-6"
    planner_model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096

    # --- Agent budget ------------------------------------------------------
    max_tool_calls: int = 16
    max_iterations: int = 12

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql://assetscope:assetscope@localhost:5432/assetscope"

    # --- Embeddings --------------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    use_fake_embeddings: bool = False

    # --- External APIs -----------------------------------------------------
    contact_email: str = "assetscope@example.com"
    pubmed_api_key: str = ""
    fda_api_key: str = ""  # optional openFDA key (raises rate limits)
    http_timeout: float = 30.0

    # --- Server ------------------------------------------------------------
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:4173"
    # Comma-separated API keys. Empty => auth disabled (open; fine for localhost).
    # When set, /query and /query/stream require a matching X-API-Key header.
    api_keys: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def api_key_set(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key != "sk-ant-...")


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings instance."""
    return Settings()
