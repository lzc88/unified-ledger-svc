import os

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
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
IBKR_FLEX_USER_AGENT = "investment-tracker/0.1 (python-httpx2)"
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

AUTH_COOKIE_NAME = "session"
AUTH_JWT_ALGORITHM = "HS256"
AUTH_SESSION_TTL = timedelta(days=7)
AUTH_JWT_SECRET_MIN_LENGTH = 32


@dataclass(frozen=True)
class ConfigKey:
    group: str
    label: str
    description: str
    secret: bool
    required: bool


CONFIG_KEYS = {
    "BIRTH_YEAR": ConfigKey(
        group="profile",
        label="Birth year",
        description="used for cpf contribution rates in the forecast.",
        secret=False,
        required=False,
    ),
    "OTHER_RELIEFS": ConfigKey(
        group="profile",
        label="Other tax reliefs",
        description=(
            "yearly reliefs beyond cpf and earned income relief, e.g. srs or parent relief. "
            "used for the tax estimate in the forecast."
        ),
        secret=False,
        required=False,
    ),
    "OPENFIGI_API_KEY": ConfigKey(
        group="integrations",
        label="OpenFIGI API key",
        description="optional; raises the openfigi rate limit when mapping broker assets.",
        secret=True,
        required=False,
    ),
}
BIRTH_YEAR_MIN = 1900
OTHER_RELIEFS_MAX = 80000

OPENFIGI_API_KEY_KEY = "OPENFIGI_API_KEY"
IBKR_FLEX_TOKEN_CREDENTIAL = "flex_token"
IBKR_FLEX_QUERY_ID_CREDENTIAL = "flex_query_id"
IBKR_CREDENTIAL_KEYS = (IBKR_FLEX_TOKEN_CREDENTIAL, IBKR_FLEX_QUERY_ID_CREDENTIAL)

CONFIG_VALUE_MAX_LENGTH = 512
CONFIG_MASK_CHAR = "•"
CONFIG_MASK_LENGTH = 8
CONFIG_MASK_VISIBLE_CHARS = 4
CONFIG_MASK_MIN_LENGTH_TO_REVEAL = 12

API_JOBS_DEFAULT_LIMIT = 20
API_JOBS_MAX_LIMIT = 100

LEDGER_DEFAULT_LIMIT = 50
LEDGER_MAX_LIMIT = 200

PORTFOLIO_DEFAULT_CURRENCY = "SGD"
PORTFOLIO_DUST = Decimal("0.000001")

"""
Cash account configuration and constants.
"""

CashCurrency = Literal["SGD", "USD", "EUR", "GBP", "JPY", "AUD", "HKD", "CNY", "MYR"]
CASH_CURRENCIES: tuple[str, ...] = get_args(CashCurrency)

"""
CPF statement configuration and constants.
"""

CPF_CURRENCY = "SGD"
CPF_TIMEZONE = ZoneInfo("Asia/Singapore")
CPF_ACCOUNTS = ("oa", "sa", "ma")
CPF_MAX_TRANSACTIONS = 5000
CPF_EMPLOYER_MAX_LENGTH = 200
CPF_CODES = {
    "ADJ": "Adjustment / Interest on recovered CPF contributions",
    "AMP": "Additional Monthly Payout",
    "APK": "Government Top-up: Assurance Package",
    "BAL": "Balance",
    "CLA": "CPF LIFE Premium",
    "CLC": "CPF LIFE Change of plan",
    "CLI": "CPF LIFE Payout",
    "CLR": "Refund from CPF LIFE",
    "CLS": "CPF LIFE Switch of plan",
    "CON": "Contributions / Government Cash Grant / Government Top-up",
    "CSA": (
        "Transfer of Special Account savings to Retirement Account / "
        "Ordinary Account due to closure of your Special Account"
    ),
    "CSL": "CareShield Life",
    "DPS": "Dependants' Protection Scheme",
    "EDN": "CPF Education Loan Scheme",
    "ESB": "Government Top-up: Earn and Save Bonus",
    "ESH": "Basic ElderShield",
    "GCH": "GovCash",
    "GOV": "Government Cash Benefits",
    "GSV": "Government Top-up: GST Voucher",
    "HHG": "CPF Housing Grant from HDB",
    "HPC": "Home Protection Scheme Claim",
    "HPR": "Home Protection Scheme Rebate",
    "HPS": "Home Protection Scheme",
    "HSE": "HDB flats and other residential properties",
    "INT": "Interest for the whole year",
    "INV": "CPF Investment Scheme",
    "IPA": "Government Top-up: ITE Progression Award",
    "LFM": "Government Top-up: Large Family MediSave Grant",
    "LTC": "Long-term care withdrawals under MediSave Care",
    "MCI": "MediSave Contribution by Institution",
    "MED": "MediSave deduction or reimbursement for medical expenses",
    "MGN": "Government Top-up: MediSave Grant for Newborns",
    "MGP": "Government Top-up: Merdeka Generation Package",
    "MHG": "CPF Grant from MSF",
    "MMS": "Government Top-up: Matched MediSave Scheme Grant",
    "MRS": "Matched Retirement Savings Scheme Grant",
    "MSB": "Government Top-up: MediSave Bonus",
    "MSH": "MediShield",
    "MSL": "MediShield Life / MediShield Life component of an Integrated Shield Plan",
    "NSA": "Government Top-up: NS HOME Awards",
    "ORN": "Government Top-up: ORNS Completion Award",
    "PCT": "Platform Workers CPF Transition Support",
    "PGP": "Government Top-up: Pioneer Generation Package",
    "PMI": (
        "Additional private insurance coverage component of an "
        "Integrated Shield Plan / Non-Integrated Shield Plan"
    ),
    "PSE": "Post Secondary Education Account",
    "PTY": "Non-residential property",
    "RFD": (
        "Refund of contributions to employer / employee / self-employed person "
        "or of Government Cash Grant"
    ),
    "RLE": "Withdrawal of CPF savings on reduced life expectancy",
    "RSB": "Government Top-up: Retirement Savings Bonus",
    "RSS": "Retirement Sum Scheme",
    "RST": "Top-ups under CPF Retirement Sum Topping-Up Scheme",
    "SDS": (
        "Dividends / proceeds / adjustments under the Special Discounted "
        "Shares Scheme (e.g. Singtel shares)"
    ),
    "SE": "Payment by self-employed person",
    "SNS": "Special Needs Savings Scheme",
    "SUP": "ElderShield Supplement / CareShield Life Supplement",
    "TFR": "Transfer between accounts",
    "WDL": "Withdrawal of CPF savings",
    "WIS": "Government Top-up: Workfare Income Supplement",
}

"""
Forecast plan configuration and constants.
"""

FORECAST_TIMEZONE = ZoneInfo("Asia/Singapore")
FORECAST_MAX_MONTHS_AHEAD = 600
FORECAST_MAX_DESTINATIONS = 30
FORECAST_DESTINATION_ID_MAX_LENGTH = 64
FORECAST_DESTINATION_NAME_MAX_LENGTH = 60

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
    "test": CONFIG_DIR / ".env.test",
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


class AuthSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    auth_jwt_secret: SecretStr
    auth_cookie_secure: bool = True

    @field_validator("auth_jwt_secret")
    @classmethod
    def _long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < AUTH_JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"AUTH_JWT_SECRET must be at least {AUTH_JWT_SECRET_MIN_LENGTH} characters"
            )
        return value


class ConfigStoreSettings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    config_encryption_key: SecretStr

    @field_validator("config_encryption_key")
    @classmethod
    def _valid_fernet_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value())
        except ValueError:
            raise ValueError(
                "CONFIG_ENCRYPTION_KEY must be a Fernet key "
                "(generate one with Fernet.generate_key())"
            ) from None
        return value


def _existing_env_file() -> Path:
    env_file = _env_file()
    if not env_file.is_file():
        raise FileNotFoundError(f"Env file not found: {env_file}")
    return env_file


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_existing_env_file())  # pyright: ignore[reportCallIssue]


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings(_env_file=_existing_env_file())  # pyright: ignore[reportCallIssue]


@lru_cache
def get_config_store_settings() -> ConfigStoreSettings:
    return ConfigStoreSettings(
        _env_file=_existing_env_file()  # pyright: ignore[reportCallIssue]
    )
