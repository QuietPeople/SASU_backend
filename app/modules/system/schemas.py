"""API-SYS-01 상태 응답과 공통 오류 코드."""

from typing import Literal

from pydantic import BaseModel

from app.core.exceptions import ErrorDetail

ResourceStatus = Literal["ok", "unavailable"]


class Health(BaseModel):
    status: ResourceStatus
    database: ResourceStatus
    video_storage: ResourceStatus


class UnavailableHealth(Health):
    detail: ErrorDetail
