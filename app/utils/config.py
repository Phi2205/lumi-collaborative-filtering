"""Configuration settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")

    # Database for event logging (PostgreSQL for both dev and prod)
    # Set via DATABASE_URL env var or .env file (takes priority over default)
    # Example: postgresql://user:password@localhost:5432/lumi_cf_dev
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/lumi_cf_dev"

    # Path to saved model artifact (joblib)
    # Set via MODEL_PATH env var or .env file (takes priority over default)
    MODEL_PATH: str = "artifacts/model.joblib"

    # How many candidates to compute (API can request k <= this cap)
    DEFAULT_K: int = 20
    MAX_K: int = 200


settings = Settings()
