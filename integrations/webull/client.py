from dataclasses import dataclass
from typing import Any

from webull.core.client import ApiClient
from webull.core.exception.exceptions import ClientException, ServerException
from webull.core.http.initializer.token.token_operation import TokenOperation
from webull.trade.trade.v2.account_info_v2 import AccountV2

from config.config import (
    WEBULL_API_HOST,
    WEBULL_CONNECT_TIMEOUT_SECONDS,
    WEBULL_HTTP_TIMEOUT_SECONDS,
    WEBULL_REGION,
    WEBULL_TOKEN_STATUSES,
)
from integrations.base import IntegrationError


class WebullApiError(IntegrationError):
    pass


@dataclass(frozen=True)
class AccessToken:
    token: str
    status: str
    expires: int | None


class WebullClient:
    def __init__(self, app_key: str, app_secret: str, token: str | None = None) -> None:
        self._api = ApiClient(
            app_key,
            app_secret,
            WEBULL_REGION,
            timeout=WEBULL_HTTP_TIMEOUT_SECONDS,
            connect_timeout=WEBULL_CONNECT_TIMEOUT_SECONDS,
        )
        if WEBULL_API_HOST:
            self._api.add_endpoint(WEBULL_REGION, WEBULL_API_HOST)

        if token:
            self._api.set_token(token)

        self._tokens = TokenOperation(self._api)
        self._account = AccountV2(self._api)

    def create_token(self) -> AccessToken:
        return _access_token(self._call(self._tokens.create_token, None))

    def check_token(self, token: str) -> AccessToken:
        return _access_token(self._call(self._tokens.check_token, token))

    def accounts(self) -> list[dict[str, Any]]:
        return _rows(self._call(self._account.get_account_list), "account list")

    def balance(self, account_id: str) -> dict[str, Any]:
        payload = self._call(self._account.get_account_balance, account_id)
        if not isinstance(payload, dict):
            raise WebullApiError("Webull returned an unexpected account balance")

        return payload

    def positions(self, account_id: str) -> list[dict[str, Any]]:
        payload = self._call(self._account.get_account_position, account_id)
        return _rows(payload, "position list")

    @staticmethod
    def _call(method, *args) -> Any:
        try:
            response = method(*args)
        except ServerException as exc:
            raise WebullApiError(
                f"Webull rejected the request "
                f"({exc.get_http_status()} {exc.get_error_code()})"
            ) from exc
        except ClientException as exc:
            raise WebullApiError(
                f"Webull request failed ({exc.get_error_code()})"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise WebullApiError("Webull returned a non-JSON response") from exc


def _access_token(payload: Any) -> AccessToken:
    if not isinstance(payload, dict) or not payload.get("token"):
        raise WebullApiError("Webull returned no access token")

    status = payload.get("status")
    if status not in WEBULL_TOKEN_STATUSES:
        raise WebullApiError(f"Webull returned an unknown token status {status!r}")

    expires = payload.get("expires_at", payload.get("expires"))

    return AccessToken(
        token=payload["token"],
        status=status,
        expires=int(expires) if expires not in (None, "") else None,
    )


def _rows(payload: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("data", "items", "list"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise WebullApiError(f"Webull returned an unexpected {label}")

    return payload
