import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import date, timedelta
from urllib.parse import urlsplit

import httpx2

from config.config import (
    IBKR_FLEX_API_VERSION,
    IBKR_FLEX_HTTP_TIMEOUT_SECONDS,
    IBKR_FLEX_MAX_ATTEMPTS,
    IBKR_FLEX_MAX_WINDOW_DAYS,
    IBKR_FLEX_MIN_REQUEST_INTERVAL,
    IBKR_FLEX_POLL_INTERVAL,
    IBKR_FLEX_RATE_LIMIT_BACKOFF,
    IBKR_FLEX_RATE_LIMITED_CODE,
    IBKR_FLEX_RETRYABLE_CODES,
    IBKR_FLEX_SEND_REQUEST_URL,
    IBKR_FLEX_USER_AGENT,
    get_ibkr_settings,
)
from integrations.base import IntegrationError


class FlexError(IntegrationError):

    def __init__(self, code: str | None, message: str) -> None:
        super().__init__(f"IBKR Flex error {code}: {message}" if code else message)
        self.code = code


def date_windows(start: date, end: date) -> list[tuple[date, date]]:

    if start > end:
        raise ValueError(f"start {start} is after end {end}")

    windows = []
    for year in range(start.year, end.year + 1):
        window_start = max(start, date(year, 1, 1))
        year_end = min(end, date(year, 12, 31))
        while window_start <= year_end:
            window_end = min(
                window_start + timedelta(days=IBKR_FLEX_MAX_WINDOW_DAYS - 1), year_end
            )
            windows.append((window_start, window_end))
            window_start = window_end + timedelta(days=1)

    return windows


class FlexClient:

    def __init__(
        self,
        token: str,
        query_id: str,
        *,
        http: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:

        self._token = token
        self._query_id = query_id
        self._http = http or httpx2.Client(timeout=IBKR_FLEX_HTTP_TIMEOUT_SECONDS)
        self._sleep = sleep
        self._last_request: float | None = None

    def fetch_range(self, start: date, end: date) -> list[bytes]:
        return [self.fetch(fd, td) for fd, td in date_windows(start, end)]

    def fetch(self, start: date, end: date) -> bytes:

        if (end - start).days + 1 > IBKR_FLEX_MAX_WINDOW_DAYS:
            raise ValueError(
                f"Flex requests cover at most {IBKR_FLEX_MAX_WINDOW_DAYS} days"
            )

        reference_code, statement_url = self._send_request(start, end)

        return self._get_statement(reference_code, statement_url)

    def _send_request(self, start: date, end: date) -> tuple[str, str]:

        params = {
            "t": self._token,
            "q": self._query_id,
            "fd": start.strftime("%Y%m%d"),
            "td": end.strftime("%Y%m%d"),
            "v": IBKR_FLEX_API_VERSION,
        }

        _, root = self._call_with_retry(IBKR_FLEX_SEND_REQUEST_URL, params)

        reference_code = root.findtext("ReferenceCode")
        statement_url = root.findtext("Url")

        if not reference_code or not statement_url:
            raise FlexError(
                None, "SendRequest response is missing ReferenceCode or Url"
            )

        _check_ibkr_url(statement_url.strip())

        return reference_code.strip(), statement_url.strip()

    def _get_statement(self, reference_code: str, statement_url: str) -> bytes:

        params = {"t": self._token, "q": reference_code, "v": IBKR_FLEX_API_VERSION}
        content, _ = self._call_with_retry(statement_url, params)

        return content

    def _call_with_retry(
        self, url: str, params: dict[str, str]
    ) -> tuple[bytes, ET.Element]:

        for attempt in range(1, IBKR_FLEX_MAX_ATTEMPTS + 1):

            content, root = self._call(url, params)

            if root.tag != "FlexStatementResponse":
                return content, root

            status = (root.findtext("Status") or "").strip()

            if status == "Success":
                return content, root

            code = (root.findtext("ErrorCode") or "").strip() or None

            message = (
                root.findtext("ErrorMessage") or status or "unknown error"
            ).strip()

            if (
                code not in IBKR_FLEX_RETRYABLE_CODES
                or attempt == IBKR_FLEX_MAX_ATTEMPTS
            ):
                raise FlexError(code, message)

            self._sleep(
                IBKR_FLEX_RATE_LIMIT_BACKOFF
                if code == IBKR_FLEX_RATE_LIMITED_CODE
                else IBKR_FLEX_POLL_INTERVAL
            )

        raise AssertionError("unreachable")

    def _call(self, url: str, params: dict[str, str]) -> tuple[bytes, ET.Element]:
        self._throttle()
        try:
            response = self._http.get(
                url, params=params, headers={"User-Agent": IBKR_FLEX_USER_AGENT}
            )
        except httpx2.HTTPError as exc:
            raise FlexError(
                None, f"{type(exc).__name__} calling {urlsplit(url).path}"
            ) from None
        if response.status_code != 200:
            raise FlexError(
                None, f"HTTP {response.status_code} from {urlsplit(url).path}"
            )
        try:
            return response.content, ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise FlexError(None, f"Response is not valid XML: {exc}") from exc

    def _throttle(self) -> None:

        if self._last_request is not None:
            wait = IBKR_FLEX_MIN_REQUEST_INTERVAL - (
                time.monotonic() - self._last_request
            )

            if wait > 0:
                self._sleep(wait)

        self._last_request = time.monotonic()


def fetch_documents(start: date, end: date) -> list[bytes]:

    settings = get_ibkr_settings()

    with httpx2.Client(timeout=IBKR_FLEX_HTTP_TIMEOUT_SECONDS) as http:
        client = FlexClient(
            settings.ibkr_flex_token.get_secret_value(),
            settings.ibkr_flex_query_id,
            http=http,
        )

        return client.fetch_range(start, end)


def _check_ibkr_url(url: str) -> None:

    parts = urlsplit(url)
    host = parts.hostname or ""

    if parts.scheme != "https" or not (
        host == "interactivebrokers.com" or host.endswith(".interactivebrokers.com")
    ):
        raise FlexError(None, f"Unexpected statement URL host: {host!r}")
