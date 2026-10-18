"""관리자 API의 요청·응답. 외부 세대 0은 DB learning_epoch 1에 대응한다."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Rate(BaseModel):
    numerator: int
    denominator: int
    percent: float | None


class ReactionStats(BaseModel):
    view_count: int
    like_count: int
    saved_count: int
    watch_completion: Rate


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    confirm: StrictBool
    expected_record_generation: int = Field(ge=0, le=2**31 - 3)


class DeletedCounts(BaseModel):
    watch_visits: int
    watch_records: int
    likes: int
    saved_contents: int
    responses: int
    attempts: int
    wrong_answers: int
    events: int


class ResetResult(BaseModel):
    user_id: int
    record_generation: int
    deleted_counts: DeletedCounts
    clear_client_feed_state: bool
    preserved: list[str]
