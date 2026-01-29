from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Database for event logging (PostgreSQL for both dev and prod)
    # Set via DATABASE_URL env var or .env file, e.g.:
    # postgresql://user:password@localhost:5432/lumi_cf_dev
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/lumi_cf_dev"

    # Path to saved model artifact (joblib)
    MODEL_PATH: str = "artifacts/model.joblib"

    # How many candidates to compute (API can request k <= this cap)
    DEFAULT_K: int = 20
    MAX_K: int = 200


settings = Settings()

