import os

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

CONFIG_DIR = Path(__file__).parent

ENV_FILES = {
    "local": CONFIG_DIR / ".env.local",
    "remote": CONFIG_DIR / ".env",
}


def _env_file() -> Path:
    app_env = os.environ.get("APP_ENV", "local")
    if app_env not in ENV_FILES:
        raise ValueError(f"APP_ENV must be one of {sorted(ENV_FILES)}, got {app_env!r}")
    return ENV_FILES[app_env]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def _must_be_postgres(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("DATABASE_URL must be a Postgres connection string")
        return value

    @property
    def sqlalchemy_url(self) -> URL:
        url = make_url(self.database_url.get_secret_value())
        return url.set(drivername="postgresql+psycopg")


class IbkrSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    ibkr_flex_token: SecretStr
    ibkr_flex_query_id: str


class OpenFigiSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    openfigi_api_key: SecretStr | None = None


def _existing_env_file() -> Path:
    env_file = _env_file()
    if not env_file.is_file():
        raise FileNotFoundError(f"Env file not found: {env_file}")
    return env_file


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_existing_env_file())  # pyright: ignore[reportCallIssue]


@lru_cache
def get_ibkr_settings() -> IbkrSettings:
    return IbkrSettings(
        _env_file=_existing_env_file()  # pyright: ignore[reportCallIssue]
    )


@lru_cache
def get_openfigi_settings() -> OpenFigiSettings:
    return OpenFigiSettings(
        _env_file=_existing_env_file()  # pyright: ignore[reportCallIssue]
    )
