"""Server settings, loaded from environment variables or a .env file.

Copy `.env.example` to `.env` for local development. The server itself needs no API key.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "stdio" (local client launches the server) or "streamable-http" (hosted).
    # app.py also switches to HTTP whenever the platform injects PORT or DATABRICKS_APP_PORT.
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000


settings = Settings()
