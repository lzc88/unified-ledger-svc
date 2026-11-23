from integrations.base import BrokerAdapter
from integrations.ibkr import IbkrAdapter
from integrations.webull import WebullAdapter

ADAPTERS: dict[str, BrokerAdapter] = {
    "ibkr": IbkrAdapter(),
    "webull": WebullAdapter(),
}
