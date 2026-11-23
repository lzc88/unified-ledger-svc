from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config.config import (
    BIRTH_YEAR_MIN,
    CONFIG_KEYS,
    CONFIG_MASK_CHAR,
    CONFIG_MASK_LENGTH,
    CONFIG_MASK_MIN_LENGTH_TO_REVEAL,
    CONFIG_MASK_VISIBLE_CHARS,
    CPF_TIMEZONE,
    INTEGRATION_KEYS,
    ConfigKey,
)
from database.models import UserConfig

from .crypto import UndecryptableValueError, decrypt, encrypt


class UnknownConfigKeyError(Exception):
    pass


class ConfigNotSetError(Exception):
    pass


class ConfigMissingError(Exception):
    pass


class ConfigUnreadableError(Exception):
    pass


class InvalidConfigValueError(Exception):
    pass


@dataclass(frozen=True)
class ConfigEntry:
    key: str
    meta: ConfigKey
    is_set: bool
    value: str | None
    updated_at: datetime | None


def mask(value: str) -> str:
    hidden = CONFIG_MASK_CHAR * CONFIG_MASK_LENGTH
    if len(value) < CONFIG_MASK_MIN_LENGTH_TO_REVEAL:
        return hidden

    return hidden + value[-CONFIG_MASK_VISIBLE_CHARS:]


def list_configs(session: Session, user_id: str) -> list[ConfigEntry]:
    rows = {row.config_key: row for row in _rows(session, user_id)}
    return [_entry(key, rows.get(key)) for key in CONFIG_KEYS]


def set_config(session: Session, user_id: str, key: str, value: str) -> ConfigEntry:
    _require_known(key)

    if (validate := _VALIDATORS.get(key)) is not None:
        validate(value)

    return _entry(key, _store(session, user_id, key, value))


def delete_config(session: Session, user_id: str, key: str) -> None:
    _require_known(key)

    row = session.get(UserConfig, (user_id, key))
    if row is None:
        raise ConfigNotSetError(f"config key not set: {key}")

    session.delete(row)


def integration_rows(session: Session, user_id: str) -> dict[str, UserConfig]:
    return {
        row.config_key: row
        for row in _rows(session, user_id)
        if row.config_key in INTEGRATION_KEYS
    }


def set_integration_value(
    session: Session, user_id: str, key: str, value: str
) -> UserConfig:
    _require_integration(key)
    return _store(session, user_id, key, value)


def delete_integration_values(
    session: Session, user_id: str, keys: Collection[str]
) -> None:
    for key in keys:
        _require_integration(key)

    session.execute(
        delete(UserConfig).where(
            UserConfig.from_user_id == user_id, UserConfig.config_key.in_(keys)
        )
    )


def resolve(session: Session, user_id: str) -> dict[str, str]:
    values = {}
    for key, row in integration_rows(session, user_id).items():
        try:
            values[key] = decrypt(row.encrypted_value)
        except UndecryptableValueError:
            raise ConfigUnreadableError(
                f"stored {key} can't be decrypted; edit the broker under my investments"
            ) from None

    return values


def require(values: Mapping[str, str], keys: Collection[str], name: str) -> None:
    if any(key not in values for key in keys):
        raise ConfigMissingError(
            f"{name} is not connected: add it under my investments"
        )


def display(encrypted_value: str, secret: bool) -> str:
    try:
        value = decrypt(encrypted_value)
    except UndecryptableValueError:
        return CONFIG_MASK_CHAR * CONFIG_MASK_LENGTH

    return mask(value) if secret else value


def _rows(session: Session, user_id: str) -> list[UserConfig]:
    return list(
        session.scalars(select(UserConfig).where(UserConfig.from_user_id == user_id))
    )


def _store(session: Session, user_id: str, key: str, value: str) -> UserConfig:
    row = session.get(UserConfig, (user_id, key))
    if row is None:
        row = UserConfig(from_user_id=user_id, config_key=key, encrypted_value="")
        session.add(row)

    row.encrypted_value = encrypt(value)
    session.flush()
    session.refresh(row)

    return row


def _validate_birth_year(value: str) -> None:
    current_year = datetime.now(CPF_TIMEZONE).year
    if not (
        len(value) == 4
        and value.isascii()
        and value.isdigit()
        and BIRTH_YEAR_MIN <= int(value) <= current_year
    ):
        raise InvalidConfigValueError("birth year: enter a year like 1994.")


_VALIDATORS: dict[str, Callable[[str], None]] = {
    "BIRTH_YEAR": _validate_birth_year,
}


def _require_known(key: str) -> None:
    if key not in CONFIG_KEYS:
        raise UnknownConfigKeyError(f"unknown config key: {key}")


def _require_integration(key: str) -> None:
    if key not in INTEGRATION_KEYS:
        raise UnknownConfigKeyError(f"unknown integration key: {key}")


def _entry(key: str, row: UserConfig | None) -> ConfigEntry:
    meta = CONFIG_KEYS[key]
    if row is None:
        return ConfigEntry(key, meta, is_set=False, value=None, updated_at=None)

    return ConfigEntry(
        key,
        meta,
        is_set=True,
        value=display(row.encrypted_value, meta.secret),
        updated_at=row.updated_at,
    )
