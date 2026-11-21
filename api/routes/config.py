from fastapi import APIRouter, HTTPException, Response, status

from api.deps import CurrentUser, SessionFactory
from api.schemas.config import ConfigEntry, ConfigUpdate
from user_config.service import (
    ConfigNotSetError,
    UnknownConfigKeyError,
    delete_config,
    list_configs,
    set_config,
)

router = APIRouter(prefix="/config", tags=["config"])


@router.get("")
def get_config(user: CurrentUser, session_factory: SessionFactory) -> list[ConfigEntry]:
    with session_factory() as session:
        entries = list_configs(session, user.user_id)

    return [ConfigEntry.from_stored(entry) for entry in entries]


@router.put("/{key}")
def put_config(
    key: str, body: ConfigUpdate, user: CurrentUser, session_factory: SessionFactory
) -> ConfigEntry:
    try:
        with session_factory.begin() as session:
            entry = set_config(session, user.user_id, key, body.value)
    except UnknownConfigKeyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return ConfigEntry.from_stored(entry)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_config(
    key: str, user: CurrentUser, session_factory: SessionFactory
) -> Response:
    try:
        with session_factory.begin() as session:
            delete_config(session, user.user_id, key)
    except UnknownConfigKeyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except ConfigNotSetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
