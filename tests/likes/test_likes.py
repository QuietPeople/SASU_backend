import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.likes import repository


def like_row(ctx):
    return (
        ctx.connection.execute(
            text(
                """
            SELECT learning_epoch, created_at FROM sasu.content_likes
            WHERE user_id = :user_id AND content_id = :content_id
            """
            ),
            {"user_id": ctx.ids["learner"], "content_id": ctx.ids["published"]},
        )
        .mappings()
        .one_or_none()
    )


def test_like_unlike_retries_personal_state_and_statistics(context):
    ctx = context
    expected = {"content_id": ctx.ids["published"], "liked": True, "like_count": 1}
    first = ctx.client.put(ctx.path, headers=ctx.headers)
    assert first.status_code == 200, first.text
    assert first.json() == expected
    created_at = like_row(ctx)["created_at"]
    assert ctx.client.put(ctx.path, headers=ctx.headers).json() == expected
    assert like_row(ctx)["created_at"] == created_at

    summary = ctx.client.get(f"/api/contents/{ctx.ids['published']}", headers=ctx.headers).json()[
        "content"
    ]
    assert summary["liked"] is True and summary["like_count"] == 1
    statistics = ctx.client.get(
        f"/api/contents/{ctx.ids['published']}/statistics/reactions",
        headers={"X-Actor-Id": str(ctx.ids["admin"])},
    )
    assert statistics.status_code == 200, statistics.text
    assert statistics.json()["like_count"] == 1

    expected.update(liked=False, like_count=0)
    for _ in range(2):
        response = ctx.client.delete(ctx.path, headers=ctx.headers)
        assert response.status_code == 200, response.text
        assert response.json() == expected
    assert like_row(ctx) is None
    summary = ctx.client.get(f"/api/contents/{ctx.ids['published']}", headers=ctx.headers).json()[
        "content"
    ]
    assert summary["liked"] is False and summary["like_count"] == 0


def test_draft_cannot_be_liked_but_existing_like_can_be_removed(context):
    ctx = context
    draft_path = f"/api/users/{ctx.ids['learner']}/contents/{ctx.ids['draft']}/like"
    response = ctx.client.put(draft_path, headers=ctx.headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CONTENT_NOT_FOUND"
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    ctx.connection.execute(
        text("UPDATE sasu.contents SET status = 'DRAFT' WHERE content_id = :id"),
        {"id": ctx.ids["published"]},
    )
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 404
    assert like_row(ctx) is not None
    response = ctx.client.delete(ctx.path, headers=ctx.headers)
    assert response.status_code == 200 and response.json()["liked"] is False
    assert like_row(ctx) is None


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize(
    "actor,target,status",
    [
        ("admin", "learner", 403),
        ("admin", "admin", 403),
        ("other", "learner", 404),
        ("learner", "other", 404),
        ("no_settings", "no_settings", 404),
        ("missing", "learner", 404),
    ],
)
def test_only_the_target_learner_can_change_likes(context, method, actor, target, status):
    ctx = context
    actor_id = ctx.ids[actor] if actor != "missing" else 2**63 - 1
    response = ctx.client.request(
        method,
        f"/api/users/{ctx.ids[target]}/contents/{ctx.ids['published']}/like",
        headers={"X-Actor-Id": str(actor_id), "X-Record-Generation": "0"},
    )
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == (
        "ROLE_NOT_ALLOWED" if status == 403 else "USER_NOT_FOUND"
    )
    assert like_row(ctx) is None


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_missing_content_has_no_side_effect(context, method):
    ctx = context
    response = ctx.client.request(
        method,
        f"/api/users/{ctx.ids['learner']}/contents/{2**63 - 1}/like",
        headers=ctx.headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CONTENT_NOT_FOUND"
    assert like_row(ctx) is None


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("generation", [1, 2**31 - 2])
def test_generation_mismatch_rejects_the_write(context, method, generation):
    ctx = context
    response = ctx.client.request(
        method,
        ctx.path,
        headers={**ctx.headers, "X-Record-Generation": str(generation)},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    assert like_row(ctx) is None


def test_real_reset_and_late_request_preserve_new_like(context):
    ctx = context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    response = ctx.client.post(
        f"/api/users/{ctx.ids['learner']}/test-records/reset",
        headers={"X-Actor-Id": str(ctx.ids["admin"])},
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert response.status_code == 200, response.text
    assert response.json()["deleted_counts"]["likes"] == 1
    assert response.json()["record_generation"] == 1
    assert like_row(ctx) is None
    current_headers = {**ctx.headers, "X-Record-Generation": "1"}
    assert ctx.client.put(ctx.path, headers=current_headers).status_code == 200
    new_row = dict(like_row(ctx))
    for method in ("DELETE", "PUT"):
        response = ctx.client.request(method, ctx.path, headers=ctx.headers)
        assert response.status_code == 409
        assert dict(like_row(ctx)) == new_row
    assert new_row["learning_epoch"] == 2
    assert ctx.client.delete(ctx.path, headers=current_headers).status_code == 200


def test_unlike_preserves_other_users_and_other_records(context):
    ctx = context
    other_path = f"/api/users/{ctx.ids['other']}/contents/{ctx.ids['published']}/like"
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    other_response = ctx.client.put(
        other_path, headers={**ctx.headers, "X-Actor-Id": str(ctx.ids["other"])}
    )
    assert other_response.status_code == 200 and other_response.json()["like_count"] == 2
    params = {"user_id": ctx.ids["learner"], "content_id": ctx.ids["published"]}
    ctx.connection.execute(
        text(
            "INSERT INTO sasu.saved_contents (user_id, content_id, learning_epoch) "
            "VALUES (:user_id, :content_id, 1)"
        ),
        params,
    )
    ctx.connection.execute(
        text(
            """
            INSERT INTO sasu.watch_records
                (user_id, content_id, learning_epoch, first_played_at, last_watched_at)
            VALUES (:user_id, :content_id, 1, now(), now())
            """
        ),
        params,
    )
    response = ctx.client.delete(ctx.path, headers=ctx.headers)
    assert response.status_code == 200 and response.json()["like_count"] == 1
    for table in ("saved_contents", "watch_records"):
        assert (
            ctx.connection.scalar(
                text(
                    f"SELECT count(*) FROM sasu.{table} "
                    "WHERE user_id = :user_id AND content_id = :content_id"
                ),
                params,
            )
            == 1
        )
    assert (
        ctx.connection.scalar(
            text("SELECT count(*) FROM sasu.contents WHERE content_id = :content_id"), params
        )
        == 1
    )


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_database_failure_rolls_back_the_relationship(context, monkeypatch, method):
    ctx = context
    if method == "DELETE":
        assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200

    def fail_count(*args):
        raise SQLAlchemyError("SQL details must not be exposed")

    monkeypatch.setattr(repository, "get_like_count", fail_count)
    response = ctx.client.request(method, ctx.path, headers=ctx.headers)
    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "INTERNAL_ERROR", "message": "처리에 실패했습니다."}
    }
    assert (like_row(ctx) is not None) == (method == "DELETE")


def test_final_commit_failure_rolls_back_and_allows_retry(context):
    ctx = context
    reached_commit = []

    def fail_commit(session):
        count = session.scalar(
            text("SELECT count(*) FROM sasu.content_likes WHERE user_id = :user_id"),
            {"user_id": ctx.ids["learner"]},
        )
        assert count == 1
        reached_commit.append(True)
        raise SQLAlchemyError("final commit failure")

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = ctx.client.put(ctx.path, headers=ctx.headers)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert reached_commit == [True]
    assert response.status_code == 500
    assert like_row(ctx) is None
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200


def track_lock_requests(monkeypatch, expected):
    original = repository.lock_learner_state
    pids = []
    guard = Lock()
    entered = Event()

    def tracked(session, user_id):
        pid = session.connection().connection.driver_connection.info.backend_pid
        with guard:
            pids.append(pid)
            if len(pids) == expected:
                entered.set()
        return original(session, user_id)

    monkeypatch.setattr(repository, "lock_learner_state", tracked)
    return pids, entered


def assert_waiting_on_locks(connection, pids):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        waiting = connection.scalar(
            text("SELECT count(DISTINCT pid) FROM pg_locks WHERE pid = ANY(:pids) AND NOT granted"),
            {"pids": pids},
        )
        if waiting == len(pids):
            return
        time.sleep(0.01)
    pytest.fail("요청이 PostgreSQL 행 잠금을 기다리는 상태에 도달하지 못했습니다.")


def test_concurrent_puts_wait_for_the_user_lock_and_create_one_row(committed_context, monkeypatch):
    ctx = committed_context
    pids, entered = track_lock_requests(monkeypatch, expected=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with ctx.engine.begin() as connection:
            connection.execute(
                text("SELECT user_id FROM sasu.user_settings WHERE user_id = :id FOR UPDATE"),
                {"id": ctx.ids["learner"]},
            )
            futures = [pool.submit(ctx.client.put, ctx.path, headers=ctx.headers) for _ in range(2)]
            assert entered.wait(timeout=5)
            assert_waiting_on_locks(connection, pids)
        responses = [future.result(timeout=10) for future in futures]
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["like_count"] == 1 for response in responses)
    with ctx.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM sasu.content_likes WHERE user_id = :id"),
                {"id": ctx.ids["learner"]},
            )
            == 1
        )


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_request_waiting_during_reset_cannot_change_new_like(
    committed_context, monkeypatch, method
):
    ctx = committed_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    pids, entered = track_lock_requests(monkeypatch, expected=1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ctx.engine.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT sasu.reset_learning(:id, 1)"), {"id": ctx.ids["learner"]}
                )
                == 2
            )
            connection.execute(
                text(
                    "INSERT INTO sasu.content_likes (user_id, content_id, learning_epoch) "
                    "VALUES (:user_id, :content_id, 2)"
                ),
                {"user_id": ctx.ids["learner"], "content_id": ctx.ids["published"]},
            )
            future = pool.submit(ctx.client.request, method, ctx.path, headers=ctx.headers)
            assert entered.wait(timeout=5)
            assert_waiting_on_locks(connection, pids)
        response = future.result(timeout=10)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    with ctx.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT learning_epoch FROM sasu.content_likes WHERE user_id = :id"),
                {"id": ctx.ids["learner"]},
            )
            == 2
        )
