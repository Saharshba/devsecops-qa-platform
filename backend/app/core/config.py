"""Application settings."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Secure Issue Tracker"
    environment: str = "development"
    debug: bool = False

    database_url: str = "postgresql+psycopg://tracker:tracker_password@localhost:5432/tracker"
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False

    secret_key: str = "change-me-in-production-please-32-chars"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 7
    bcrypt_rounds: int = 12

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    rate_limit_requests: int = 300
    rate_limit_window_seconds: int = 60
    login_rate_limit_requests: int = 10
    login_rate_limit_window_seconds: int = 300

    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "ChangeMe!123"
    bootstrap_admin_email: str = "admin@example.com"
    seed_demo_data: bool = False

    max_upload_comment_length: int = 5000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, value):
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
