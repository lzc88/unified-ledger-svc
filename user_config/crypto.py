from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from config.config import get_config_store_settings


class UndecryptableValueError(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = get_config_store_settings().config_encryption_key.get_secret_value()
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise UndecryptableValueError from None
