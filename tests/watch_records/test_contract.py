from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError, register_exception_handlers
from app.db.session import get_db
from app.modules.watch_records import service
from app.modules.watch_records.router import router
from app.modules.watch_records.schemas import WatchVisitBody, WatchVisitResult


@pytest.fixture
def contract_client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        yield client


def watch_body(revision):
    return {
        "visit_id": str(uuid4()),
        "media_revision": revision,
        "actual_played_seconds": 3,
        "watched_segments": [[0, 3]],
        "context": "FEED",
    }


def test_revision_is_trimmed_before_service(contract_client, monkeypatch):
    revision = str(uuid4())

    def capture_report(session, actor_id, user_id, content_id, generation, body):
        assert body.media_revision == revision
        now = datetime.now(UTC)
        return WatchVisitResult(
            user_id=user_id, content_id=content_id, visit_id=body.visit_id,
            view_counted=True, newly_view_counted=True, watch_completed=False,
            visit_watch_percent=5, max_watch_percent=5, feed_completion_eligible=False,
            view_count=1, first_played_at=now, last_watched_at=now,
            completed_at=None, record_generation=generation,
        )

    monkeypatch.setattr(service, "report_watch_visit", capture_report)
    response = contract_client.post(
        "/api/users/1/contents/2/watch-reports",
        json=watch_body(f" \t{revision}\n "),
        headers={"X-Actor-Id": "1", "X-Record-Generation": "0"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("revision", ["", " \t\n ", "x" * 129])
def test_invalid_revision_is_rejected_before_service(contract_client, monkeypatch, revision):
    def unexpected_service_call(*args, **kwargs):
        pytest.fail("잘못된 영상 식별값은 서비스 호출 전에 거절해야 합니다.")

    monkeypatch.setattr(service, "report_watch_visit", unexpected_service_call)
    response = contract_client.post(
        "/api/users/1/contents/2/watch-reports",
        json=watch_body(revision),
        headers={"X-Actor-Id": "1", "X-Record-Generation": "0"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert response.json()["detail"]["fields"][0]["field"] == "body.media_revision"


def test_trimming_does_not_accept_a_different_video_revision(monkeypatch):
    session = Mock(spec=Session)
    session.in_transaction.return_value = False
    session.begin.return_value = nullcontext()
    monkeypatch.setattr(service, "require_learner", lambda *args: None)
    monkeypatch.setattr(service, "current_epoch", lambda *args: 1)
    monkeypatch.setattr(
        service.repo, "lock_content",
        lambda *args: {"status": "PUBLISHED", "video_asset_id": uuid4()},
    )
    write = Mock(side_effect=AssertionError("다른 영상의 시청 기록을 저장하면 안 됩니다."))
    monkeypatch.setattr(service.repo, "save_visit", write)
    body = WatchVisitBody.model_validate(watch_body(f" {uuid4()} "))
    with pytest.raises(ApiError) as caught:
        service.report_watch_visit(session, 1, 1, 2, 0, body)
    assert (caught.value.status_code, caught.value.code) == (409, "VIDEO_CHANGED")
    write.assert_not_called()
