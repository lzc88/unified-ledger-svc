from functools import lru_cache

from pwdlib import PasswordHash


@lru_cache
def _hasher() -> PasswordHash:
    return PasswordHash.recommended()


@lru_cache
def _dummy_hash() -> str:
    return _hasher().hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher().verify(password, _dummy_hash())
        return False

    return _hasher().verify(password, password_hash)
