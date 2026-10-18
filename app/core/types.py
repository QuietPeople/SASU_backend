from typing import Annotated

from pydantic import Field

MAX_BIGINT = 2**63 - 1
PositiveId = Annotated[int, Field(gt=0, le=MAX_BIGINT)]
