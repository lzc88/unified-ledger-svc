from typing import Annotated

from fastapi import Query

Currency = Annotated[str, Query(pattern="^[A-Z]{3}$", description="Reporting currency")]
