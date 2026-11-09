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
    gemini_fallback_model: str = "gemini-3.5-flash-lite"  # used when the primary model keeps failing; "" disables (listed stable in the Gemini model docs)
    gemini_retries: int = 2                    # extra attempts on transient errors (HTTP 500/503/504, timeouts) for the primary model
    gemini_timeout_seconds: float = 20.0       # per attempt
    gemini_total_budget_seconds: float = 45.0  # per call, across all attempts and models
    gemini_model_cooldown_seconds: float = 120.0  # a failing primary model is skipped this long (the fallback answers directly)
    gemini_circuit_seconds: float = 30.0       # after an outage, skip Gemini this long so the app stays responsive
    gemini_thinking_level: str = ""            # "", minimal|low|medium|high. Empty = model default. NOTE: 'minimal' is rejected by some models (e.g. 3.8 Flash)
    gemini_base_url: str = ""  # optional override (proxy / tests); empty = Google default
    gemini_model: str = "gemini-3.8-flash"  # verified in the official model list on 2026-11-04

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    # PayPal may not settle INR for every account/country. Orders are created in this
    # currency, converted server-side from the authoritative DB amount.
    paypal_disable_funding: str = ""  # e.g. "card" or "card,paylater": funding sources to hide in the PayPal buttons (JS SDK `disable-funding`)
    paypal_currency: str = "USD"
    inr_per_unit_paypal_currency: Decimal = Decimal("83.00")  # demo rate, NOT live FX

    # Product sources. "curated" = built-in demo catalog; "dummyjson" = free demo API with real product photos (not a real retailer).
    product_providers: str = "curated,dummyjson"
    dummyjson_base_url: str = "https://dummyjson.com"
    provider_timeout_seconds: float = 8.0
    provider_usd_to_inr: Decimal = Decimal("83.00")  # DEMO FX rate; keep equal to INR_PER_UNIT_PAYPAL_CURRENCY so PayPal USD == provider USD
    provider_max_results: int = 24

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
    def enabled_providers(self) -> list[str]:
        return [p.strip().lower() for p in self.product_providers.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
