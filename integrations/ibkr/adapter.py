from collections.abc import Mapping

from config.config import (
    IBKR_CREDENTIAL_KEYS,
    IBKR_FLEX_QUERY_ID_CREDENTIAL,
    IBKR_FLEX_TIMEZONE,
    IBKR_FLEX_TOKEN_CREDENTIAL,
)
from integrations.base import Snapshot

from .flex import fetch_document
from .mapping import map_snapshot


class IbkrAdapter:
    broker_id = "IBKR"
    broker_name = "Interactive Brokers"
    timezone = IBKR_FLEX_TIMEZONE
    credential_keys = IBKR_CREDENTIAL_KEYS

    def fetch_snapshot(self, credentials: Mapping[str, str]) -> Snapshot:

        document = fetch_document(
            credentials[IBKR_FLEX_TOKEN_CREDENTIAL],
            credentials[IBKR_FLEX_QUERY_ID_CREDENTIAL],
        )

        return map_snapshot(document)
