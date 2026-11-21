from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, SecretStr

Username = Annotated[
    str,
    Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$"),
    AfterValidator(str.lower),
]
Password = Annotated[SecretStr, Field(min_length=8, max_length=128)]


class Credentials(BaseModel):
    username: Username
    password: Password


class Me(BaseModel):
    user_id: str
    username: str
