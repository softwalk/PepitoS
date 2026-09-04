"""Configuración por variables de entorno."""
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "PEPITO OS API"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"  # development | staging | production
    DATABASE_URL: str = "postgresql+psycopg://pepito:pepito@localhost:5433/pepito"
    JWT_SECRET: str = "cambia-este-secreto"
    JWT_EXPIRES_HOURS: int = 12
    TZ_NAME: str = "America/Mexico_City"
    RULES_INTERVAL_SECONDS: int = 300
    CORS_ORIGINS: str = "*"
    RUN_SCHEDULER: bool = True
    SQL_ECHO: bool = False
    # Seed: demo | prod | none (ver README). En prod el admin inicial usa ADMIN_INITIAL_PASSWORD.
    SEED_MODE: str = "demo"
    ADMIN_INITIAL_PASSWORD: str | None = None
    # Rate limiting de login (B2)
    LOGIN_MAX_FAILS_USER: int = 5
    LOGIN_MAX_FAILS_IP: int = 30
    LOGIN_WINDOW_MINUTES: int = 15
    LOGIN_LOCK_MINUTES: int = 15
    LOGIN_ATTEMPTS_RETENTION_DAYS: int = 7
    # Refresh tokens rotativos (B3)
    REFRESH_EXPIRES_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 8

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TZ_NAME)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


INSECURE_SECRETS = {"cambia-este-secreto", "cambia-este-secreto-por-uno-largo-y-aleatorio-de-32-bytes", "", "secret", "changeme"}


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.APP_ENV == "production":
        if s.JWT_SECRET in INSECURE_SECRETS or len(s.JWT_SECRET) < 32:
            raise RuntimeError("JWT_SECRET inseguro: en producción debe ser aleatorio y de al menos 32 caracteres")
        if s.CORS_ORIGINS.strip() == "*":
            raise RuntimeError("CORS_ORIGINS no puede ser '*' en producción")
    return s


settings = get_settings()
