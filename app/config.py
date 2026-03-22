from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    database_path: str = os.getenv("DATABASE_PATH", "cornell_demo.db")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    ramp_client_id: str = os.getenv("RAMP_CLIENT_ID", "")
    ramp_client_secret: str = os.getenv("RAMP_CLIENT_SECRET", "")
    ramp_token_url: str = os.getenv(
        "RAMP_TOKEN_URL", "https://api.ramp.com/developer/v1/token"
    )
    ramp_api_base_url: str = os.getenv(
        "RAMP_API_BASE_URL", "https://api.ramp.com/developer/v1"
    )
    default_recruiting_staff_emails: str = os.getenv(
        "DEFAULT_RECRUITING_STAFF_EMAILS", ""
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
