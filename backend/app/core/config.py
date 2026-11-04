"""Application settings, loaded from environment variables (see .env.example).

No secret has a default value. The app starts without Gemini/PayPal credentials;
the features that need them return explicit 503 "not configured" errors.
"""
from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./trustloop.db"
    cors_origins: str = "http://localhost:3000"
    jwt_secret: str = ""  # REQUIRED outside tests; see core/security.py
    jwt_expire_minutes: int = 60 * 12

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    # PayPal may not settle INR for every account/country. Orders are created in this
    # currency, converted server-side from the authoritative DB amount.
    paypal_currency: str = "USD"
    inr_per_unit_paypal_currency: Decimal = Decimal("83.00")  # demo rate, NOT live FX

    rate_limit_enabled: bool = True
    approval_ttl_minutes: int = 30

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Supabase/Render give `postgres://` or `postgresql://`; newer SQLAlchemy defaults those to psycopg v3,
        # but this project pins psycopg2, so make the driver explicit.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg2://" + v[len(prefix):]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
