from collections.abc import Iterable, Mapping
from datetime import date

from config.config import IBKR_CONFIG_KEYS, IBKR_FLEX_TIMEZONE
from integrations.base import MappingResult

from .flex import fetch_documents
from .mapping import map_statements


class IbkrAdapter:
    broker_id = "IBKR"
    broker_name = "Interactive Brokers"
    timezone = IBKR_FLEX_TIMEZONE
    config_keys = IBKR_CONFIG_KEYS

    def fetch(self, start: date, end: date, config: Mapping[str, str]) -> list[bytes]:
        return fetch_documents(
            config["IBKR_FLEX_TOKEN"], config["IBKR_FLEX_QUERY_ID"], start, end
        )

    def map(self, documents: Iterable[bytes]) -> MappingResult:
        return map_statements(documents)
