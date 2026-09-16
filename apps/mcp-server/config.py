"""Configuration for the MCP server.

Everything is read from the environment. Nothing is hardcoded, and no secret
ever leaves this process: the MCP client sees tool results, never credentials.
That separation is the point of running a server at all - see
INSTRUCTIONS/day3/03-module8-security-sdk.md
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env - covers `python server.py` / `make mcp` direct runs.
# `docker compose --env-file .env` covers the container path separately.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    # ---------- identity ----------
    server_name: str = Field(default="nt-network", alias="MCP_SERVER_NAME")
    transport: str = Field(default="stdio", alias="MCP_TRANSPORT")
    port: int = Field(default=9000, alias="MCP_PORT")

    # ---------- PostgreSQL ----------
    # Always the read-only account. The server has no code path that writes.
    pg_dsn: str = Field(
        default="postgresql://mcp_reader:mcp_reader_password@localhost:5432/mplsdb",
        alias="PG_DSN",
    )

    # ---------- Neo4j ----------
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="neo4j_dev_password", alias="NEO4J_PASSWORD")

    # ---------- OpenSearch ----------
    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")
    log_index: str = Field(default="network-logs", alias="OPENSEARCH_LOG_INDEX")
    doc_index: str = Field(default="network-docs", alias="OPENSEARCH_DOC_INDEX")

    # ---------- embedding ----------
    embedding_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="EMBEDDING_BASE_URL"
    )
    embedding_model: str = Field(
        default="baai/bge-m3", alias="EMBEDDING_MODEL"
    )
    embedding_dim: int = Field(default=1024, alias="EMBEDDING_DIM")
    llm_api_key: str = Field(default="not-needed", alias="LLM_API_KEY")

    # ---------- guardrails ----------
    # These are not suggestions to the model. They are enforced in code,
    # before any query reaches a database.
    max_rows: int = Field(default=200, alias="MCP_MAX_ROWS")
    max_log_results: int = Field(default=50, alias="MCP_MAX_LOG_RESULTS")
    query_timeout_seconds: int = Field(default=15, alias="MCP_QUERY_TIMEOUT_SECONDS")

    # ---------- filesystem resource ----------
    mock_fs_root: str = Field(default="data/mock_fs", alias="MOCK_FS_ROOT")
    reports_dir: str = Field(default="scripts/reports", alias="REPORTS_DIR")

    # ---------- time ----------
    # Empty means "derive now from the newest log timestamp". See clock.py.
    demo_now: str = Field(default="", alias="DEMO_NOW")

    model_config = SettingsConfigDict(
        populate_by_name=True, extra="ignore", env_file=_ENV_FILE
    )


@lru_cache
def settings() -> Settings:
    return Settings()
