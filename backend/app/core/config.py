"""Application configuration."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Default key used for local development only
DEFAULT_SECRET_KEY = "change-me-in-production-use-openssl-rand-hex-32"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "mai-tai"
    debug: bool = False

    # Database (sync URL for alembic, async for app)
    database_url: str = "postgresql://maitai:maitai@postgres:5432/maitai"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # CORS - defaults to localhost, use CORS_ORIGINS env var for additional origins
    # Example: CORS_ORIGINS='["http://192.168.1.100:3000","https://myapp.example.com"]'
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Additional CORS origins for local network access (set via environment)
    # Example: EXTRA_CORS_ORIGIN=http://192.168.86.27:3000
    extra_cors_origin: str | None = None

    # Allow all origins in development mode (easier for LAN testing)
    # Set CORS_ALLOW_ALL=true to enable
    cors_allow_all: bool = False

    # Set REGISTRATION_ENABLED=false to prevent new user sign-ups
    registration_enabled: bool = True

    # JWT (for local development)
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    refresh_token_expire_days: int = 30

    # IAP (Google Identity-Aware Proxy) - for production
    use_iap: bool = False  # Set to True in production
    iap_audience: str = ""  # e.g., "/projects/PROJECT_NUMBER/global/backendServices/SERVICE_ID"

    @model_validator(mode="after")
    def validate_secret_key_not_default_in_production(self) -> "Settings":
        """Fail fast if default secret key is used in production."""
        if not self.debug and self.secret_key == DEFAULT_SECRET_KEY:
            raise ValueError(
                "CRITICAL: Cannot use default SECRET_KEY in production! "
                "Set SECRET_KEY environment variable to a secure random value. "
                "Generate one with: openssl rand -hex 32"
            )
        return self

    class Config:
        env_file = ".env"

    @property
    def async_database_url(self) -> str:
        """Get async database URL for SQLAlchemy."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

