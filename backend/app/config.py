from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Fixed "today" of the golden dataset. The env-overridable setting below defaults to it;
# the seed generator uses this constant directly so its output never depends on env.
DEFAULT_DEMO_TODAY = date(2026, 10, 1)
MIN_JWT_SECRET_LENGTH = 32
DEV_DATABASE_PASSWORD = "ledgerwise"  # docker-compose.yml, local only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    database_url: str = "postgresql+psycopg://ledgerwise:ledgerwise@localhost:5432/ledgerwise"
    anthropic_api_key: str = ""
    llm_model: str = ""  # the agent
    llm_model_classifier: str = ""  # transaction categorizer; falls back to llm_model
    daily_llm_budget_usd: Decimal = Decimal("2")  # hard daily cap on LLM spend (UTC day)
    jwt_secret: str = ""
    demo_today: date = DEFAULT_DEMO_TODAY
    cors_origins: str = "http://localhost:3000"
    # Plaid sandbox bank feed (POST /bank-feed/plaid/sync). Sandbox keys only: the host is fixed to
    # sandbox.plaid.com in app/ingestion/plaid_feed.py, there is no production setting.
    plaid_client_id: str = ""
    plaid_secret: str = ""


    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def check_jwt_secret(settings: Settings) -> None:
    """Refuse to boot the API with a missing or weak JWT signing key."""
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


def check_production(settings: Settings) -> None:
    """With APP_ENV=production, refuse to boot on development defaults (deploy/env.production.example)."""
    if not settings.is_production:
        return
    problems = []
    if settings.database_url == Settings.model_fields["database_url"].default \
            or f":{DEV_DATABASE_PASSWORD}@" in settings.database_url:
        problems.append("DATABASE_URL uses the development default or password")
    if not settings.anthropic_api_key or not settings.llm_model:
        problems.append("ANTHROPIC_API_KEY and LLM_MODEL must be set")
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins or any(not o.startswith("https://") or "localhost" in o or "127.0.0.1" in o for o in origins):
        problems.append("CORS_ORIGINS must list only https:// origins of the real domain")
    if problems:
        raise RuntimeError("APP_ENV=production refuses to boot: " + "; ".join(problems))
