from collections.abc import Iterable
from datetime import date

from config.config import IBKR_FLEX_TIMEZONE
from integrations.base import MappingResult

from .flex import fetch_documents
from .mapping import map_statements


class IbkrAdapter:
    broker_id = "IBKR"
    broker_name = "Interactive Brokers"
    timezone = IBKR_FLEX_TIMEZONE

    def fetch(self, start: date, end: date) -> list[bytes]:
        return fetch_documents(start, end)

    def map(self, documents: Iterable[bytes]) -> MappingResult:
        return map_statements(documents)
