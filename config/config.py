import os

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url

"""
IBKR Flex Web Service API configuration and constants.
"""

IBKR_FLEX_SEND_REQUEST_URL = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
)
IBKR_FLEX_API_VERSION = "3"
IBKR_FLEX_USER_AGENT = "investment-tracker/0.1 (python-httpx)"
IBKR_FLEX_HTTP_TIMEOUT_SECONDS = 60.0
IBKR_FLEX_MAX_WINDOW_DAYS = 365
IBKR_FLEX_RETRYABLE_CODES = frozenset(
    {"1001", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"}
)
IBKR_FLEX_RATE_LIMITED_CODE = "1018"
IBKR_FLEX_MIN_REQUEST_INTERVAL = 1.1
IBKR_FLEX_RATE_LIMIT_BACKOFF = 60.0
IBKR_FLEX_POLL_INTERVAL = 5.0
IBKR_FLEX_MAX_ATTEMPTS = 20

IBKR_FLEX_TIMEZONE = ZoneInfo("America/New_York")
IBKR_FLEX_DATE_FORMATS = ("%Y%m%d", "%Y-%m-%d")
IBKR_FLEX_TIME_FORMATS = ("%H%M%S", "%H:%M:%S")
IBKR_SUB_CATEGORY_TO_LISTING_CATEGORY = {
    "ETF": "ETF",
    "COMMON": "STOCK",
}
IBKR_LISTING_EXCHANGE_TO_EXCH_CODES = {
    "NASDAQ": frozenset({"UW", "UQ", "UR"}),
    "NYSE": frozenset({"UN"}),
    "ARCA": frozenset({"UP"}),
    "AMEX": frozenset({"UA"}),
    "BATS": frozenset({"UF"}),
    "LSE": frozenset({"LN"}),
    "LSEETF": frozenset({"LN"}),
    "IBIS": frozenset({"GY"}),
    "IBIS2": frozenset({"GY"}),
    "FWB": frozenset({"GF"}),
    "AEB": frozenset({"NA"}),
    "SBF": frozenset({"FP"}),
    "EBS": frozenset({"SE"}),
    "BVME": frozenset({"IM"}),
    "SEHK": frozenset({"HK"}),
    "SGX": frozenset({"SP"}),
    "ASX": frozenset({"AT"}),
    "TSE": frozenset({"CT"}),
    "TSEJ": frozenset({"JT"}),
}

"""
OpenFIGI API configuration and constants.
"""

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_HTTP_TIMEOUT_SECONDS = 30.0
OPENFIGI_KEYLESS_BATCH_SIZE = 5
OPENFIGI_KEYED_BATCH_SIZE = 100
OPENFIGI_KEYLESS_REQUEST_INTERVAL = 60.0 / 25
OPENFIGI_KEYED_REQUEST_INTERVAL = 6.0 / 25
OPENFIGI_RATE_LIMIT_BACKOFF = 60.0
OPENFIGI_MAX_ATTEMPTS = 3

SYNC_REFRESH_OVERLAP_DAYS = 7

API_JOBS_DEFAULT_LIMIT = 20
API_JOBS_MAX_LIMIT = 100

PORTFOLIO_DEFAULT_CURRENCY = "SGD"
PORTFOLIO_DUST = Decimal("0.000001")

MARKET_CACHE_TTL_SECONDS = 300
MARKET_EXCH_CODE_SUFFIXES = {
    "US": "",
    "UW": "",
    "UQ": "",
    "UR": "",
    "UN": "",
    "UP": "",
    "UA": "",
    "UF": "",
    "LN": ".L",
    "GY": ".DE",
    "GF": ".F",
    "NA": ".AS",
    "FP": ".PA",
    "SE": ".SW",
    "IM": ".MI",
    "HK": ".HK",
    "SP": ".SI",
    "AT": ".AX",
    "CT": ".TO",
    "JT": ".T",
}

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
