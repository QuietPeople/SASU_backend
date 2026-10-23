import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from sqlalchemy import text

from app.modules.saved_contents import temporary_bridge


def track_requests(monkeypatch, expected):
    original = temporary_bridge.lock_current_epoch
    pids = []
    entered = Event()
    guard = Lock()

    def tracked(session, user_id):
        pid = session.connection().connection.driver_connection.info.backend_pid
        with guard:
            pids.append(pid)
            if len(pids) == expected:
                entered.set()
        return original(session, user_id)

    monkeypatch.setattr(temporary_bridge, "lock_current_epoch", tracked)
    return pids, entered


def assert_waiting(connection, pids):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        count = connection.scalar(
            text("SELECT count(DISTINCT pid) FROM pg_locks WHERE pid = ANY(:ids) AND NOT granted"),
            {"ids": pids},
        )
        if count == len(pids):
            return
        time.sleep(0.01)
    pytest.fail("요청이 실제 PostgreSQL 행 잠금을 기다리지 않았습니다.")


def test_concurrent_saves_create_one_relationship(committed_api_context, monkeypatch):
    ctx = committed_api_context
    pids, entered = track_requests(monkeypatch, 2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with ctx.engine.begin() as connection:
            connection.execute(
                text("SELECT user_id FROM sasu.user_settings WHERE user_id=:id FOR UPDATE"),
                {"id": ctx.learner},
            )
            futures = [pool.submit(ctx.client.put, ctx.path, headers=ctx.headers) for _ in range(2)]
            assert entered.wait(timeout=5)
            assert_waiting(connection, pids)
        responses = [future.result(timeout=10) for future in futures]
    assert [response.status_code for response in responses] == [200, 200]
    with ctx.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM sasu.saved_contents WHERE user_id=:id"),
                {"id": ctx.learner},
            )
            == 1
        )


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_old_write_waiting_during_reset_preserves_new_save(
    committed_api_context, monkeypatch, method
):
    ctx = committed_api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    pids, entered = track_requests(monkeypatch, 1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ctx.engine.begin() as connection:
            assert (
                connection.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": ctx.learner})
                == 2
            )
            connection.execute(
                text(
                    "INSERT INTO sasu.saved_contents (user_id, content_id, learning_epoch) "
                    "VALUES (:user_id, :content_id, 2)"
                ),
                {"user_id": ctx.learner, "content_id": ctx.contents[0]},
            )
            future = pool.submit(ctx.client.request, method, ctx.path, headers=ctx.headers)
            assert entered.wait(timeout=5)
            assert_waiting(connection, pids)
        response = future.result(timeout=10)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    with ctx.engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT learning_epoch FROM sasu.saved_contents WHERE user_id=:id"),
                {"id": ctx.learner},
            )
            == 2
        )


def test_list_waits_for_reset_and_reads_current_records(committed_api_context, monkeypatch):
    ctx = committed_api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    pids, entered = track_requests(monkeypatch, 1)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with ctx.engine.begin() as connection:
            connection.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": ctx.learner})
            future = pool.submit(ctx.client.get, ctx.list_path, headers=ctx.headers)
            assert entered.wait(timeout=5)
            assert_waiting(connection, pids)
        response = future.result(timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0 and response.json()["items"] == []
