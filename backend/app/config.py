from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Fixed "today" of the golden dataset. The env-overridable setting below defaults to it;
# the seed generator uses this constant directly so its output never depends on env.
DEFAULT_DEMO_TODAY = date(2026, 10, 1)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ledgerwise:ledgerwise@localhost:5432/ledgerwise"
    anthropic_api_key: str = ""
    llm_model: str = ""
    jwt_secret: str = ""
    demo_today: date = DEFAULT_DEMO_TODAY
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
