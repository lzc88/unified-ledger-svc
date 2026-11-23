from collections.abc import Iterable, Mapping
from datetime import date

from config.config import (
    IBKR_CREDENTIAL_KEYS,
    IBKR_FLEX_QUERY_ID_CREDENTIAL,
    IBKR_FLEX_TIMEZONE,
    IBKR_FLEX_TOKEN_CREDENTIAL,
)
from integrations.base import MappingResult

from .flex import fetch_documents
from .mapping import map_statements


class IbkrAdapter:
    broker_id = "IBKR"
    broker_name = "Interactive Brokers"
    timezone = IBKR_FLEX_TIMEZONE
    credential_keys = IBKR_CREDENTIAL_KEYS

    def fetch(
        self, start: date, end: date, credentials: Mapping[str, str]
    ) -> list[bytes]:
        return fetch_documents(
            credentials[IBKR_FLEX_TOKEN_CREDENTIAL],
            credentials[IBKR_FLEX_QUERY_ID_CREDENTIAL],
            start,
            end,
        )

    def map(self, documents: Iterable[bytes]) -> MappingResult:
        return map_statements(documents)
