from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.config import (
    CONFIG_KEYS,
    CONFIG_MASK_CHAR,
    CONFIG_MASK_LENGTH,
    CONFIG_MASK_MIN_LENGTH_TO_REVEAL,
    CONFIG_MASK_VISIBLE_CHARS,
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

    row = session.get(UserConfig, (user_id, key))
    if row is None:
        row = UserConfig(from_user_id=user_id, config_key=key, encrypted_value="")
        session.add(row)

    row.encrypted_value = encrypt(value)
    session.flush()
    session.refresh(row)

    return _entry(key, row)


def delete_config(session: Session, user_id: str, key: str) -> None:
    _require_known(key)

    row = session.get(UserConfig, (user_id, key))
    if row is None:
        raise ConfigNotSetError(f"config key not set: {key}")

    session.delete(row)


def resolve(session: Session, user_id: str) -> dict[str, str]:
    values = {}
    for row in _rows(session, user_id):
        if row.config_key not in CONFIG_KEYS:
            continue

        try:
            values[row.config_key] = decrypt(row.encrypted_value)
        except UndecryptableValueError:
            raise ConfigUnreadableError(
                f"stored {row.config_key} can't be decrypted; "
                "re-enter it on the Config page"
            ) from None

    return values


def require(values: Mapping[str, str], keys: Collection[str], name: str) -> None:
    missing = [key for key in keys if key not in values]
    if missing:
        raise ConfigMissingError(
            f"{name} is not configured: set {', '.join(missing)} on the Config page"
        )


def _rows(session: Session, user_id: str) -> list[UserConfig]:
    return list(
        session.scalars(select(UserConfig).where(UserConfig.from_user_id == user_id))
    )


def _require_known(key: str) -> None:
    if key not in CONFIG_KEYS:
        raise UnknownConfigKeyError(f"unknown config key: {key}")


def _entry(key: str, row: UserConfig | None) -> ConfigEntry:
    meta = CONFIG_KEYS[key]
    if row is None:
        return ConfigEntry(key, meta, is_set=False, value=None, updated_at=None)

    return ConfigEntry(
        key,
        meta,
        is_set=True,
        value=_display(meta, row.encrypted_value),
        updated_at=row.updated_at,
    )


def _display(meta: ConfigKey, encrypted_value: str) -> str:
    try:
        value = decrypt(encrypted_value)
    except UndecryptableValueError:
        return CONFIG_MASK_CHAR * CONFIG_MASK_LENGTH

    return mask(value) if meta.secret else value
