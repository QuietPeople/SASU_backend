import json
from uuid import uuid4

import pytest
from sqlalchemy import text


def body(pc, *, visit=None, seconds=3, segments=None, context="FEED"):
    return {
        "visit_id": visit or str(uuid4()),
        "media_revision": pc["asset_id"],
        "actual_played_seconds": seconds,
        "watched_segments": segments if segments is not None else [[0, seconds]],
        "context": context,
    }


def report(client, uid, pc, payload, generation=0):
    return client.post(
        f"/api/users/{uid}/contents/{pc['content_id']}/watch-reports",
        json=payload,
        headers={"X-Actor-Id": str(uid), "X-Record-Generation": str(generation)},
    )


def test_report_contract_and_replay(client, seed, published_content, database):
    uid, pc = seed["learner_id"], published_content
    payload = body(pc)
    result = report(client, uid, pc, payload)
    assert result.status_code == 200, result.text
    state = result.json()
    assert set(state) == {
        "user_id",
        "content_id",
        "visit_id",
        "view_counted",
        "newly_view_counted",
        "watch_completed",
        "visit_watch_percent",
        "max_watch_percent",
        "feed_completion_eligible",
        "view_count",
        "first_played_at",
        "last_watched_at",
        "completed_at",
        "record_generation",
    }
    assert state["view_counted"] and state["newly_view_counted"]
    assert state["view_count"] == 1
    again = report(client, uid, pc, payload).json()
    assert again["view_counted"] and not again["newly_view_counted"]
    assert again["first_played_at"] == state["first_played_at"]
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_visits")) == 1


@pytest.mark.parametrize(
    "seconds,counted,completed",
    [
        (0.1, False, False),
        (2.999, False, False),
        (3, True, False),
        (53.9999999, True, False),
        (54, True, True),
    ],
)
def test_raw_thresholds(client, seed, published_content, seconds, counted, completed):
    result = report(
        client, seed["learner_id"], published_content, body(published_content, seconds=seconds)
    )
    assert result.status_code == 200, result.text
    state = result.json()
    assert state["view_counted"] is counted
    assert state["watch_completed"] is completed
    assert state["feed_completion_eligible"] is completed


def test_union_is_not_double_counted(client, seed, published_content):
    payload = body(published_content, seconds=40, segments=[[0, 30], [10, 40], [5, 15]])
    result = report(client, seed["learner_id"], published_content, payload)
    assert result.status_code == 200
    assert result.json()["visit_watch_percent"] == pytest.approx(66.67)
    assert not result.json()["watch_completed"]


def test_different_visits_do_not_accumulate(client, seed, published_content):
    uid, pc = seed["learner_id"], published_content
    assert report(client, uid, pc, body(pc, seconds=30, segments=[[0, 30]])).status_code == 200
    state = report(client, uid, pc, body(pc, seconds=30, segments=[[30, 60]])).json()
    assert not state["watch_completed"]
    assert state["max_watch_percent"] == 50


def test_delayed_lower_snapshot_cannot_undo_completion(client, seed, published_content):
    uid, pc = seed["learner_id"], published_content
    visit = str(uuid4())
    high = report(client, uid, pc, body(pc, visit=visit, seconds=54)).json()
    low = report(client, uid, pc, body(pc, visit=visit, seconds=1)).json()
    assert low["watch_completed"] and low["view_counted"]
    assert low["completed_at"] == high["completed_at"]
    assert low["max_watch_percent"] == 90
    assert low["visit_watch_percent"] == pytest.approx(1.67)
    assert not low["feed_completion_eligible"]


@pytest.mark.parametrize("context", ["SEARCH", "CURRICULUM", "LIBRARY", "REVIEW"])
def test_non_feed_completion_does_not_count_for_feed(client, seed, published_content, context):
    result = report(
        client,
        seed["learner_id"],
        published_content,
        body(published_content, seconds=54, context=context),
    )
    assert result.status_code == 200
    assert result.json()["watch_completed"]
    assert not result.json()["feed_completion_eligible"]


@pytest.mark.parametrize(
    "changes",
    [
        {"actual_played_seconds": 0},
        {"actual_played_seconds": -1},
        {"watched_segments": []},
        {"watched_segments": [[0, 61]], "actual_played_seconds": 61},
        {"watched_segments": [[-1, 1]]},
        {"watched_segments": [[1, 1]]},
        {"watched_segments": [[0, 4]], "actual_played_seconds": 3},
        {"watched_segments": [[0, 1]] * 4001},
        {"watched_segments": [[0]]},
    ],
)
def test_invalid_reports_do_not_write(client, seed, published_content, database, changes):
    payload = {**body(published_content), **changes}
    result = report(client, seed["learner_id"], published_content, payload)
    assert result.status_code == 422, result.text
    assert result.json()["detail"]["code"] == "INVALID_WATCH_REPORT"
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_records")) == 0
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_visits")) == 0


def test_numeric_tolerance(client, seed, published_content):
    payload = body(published_content, seconds=2.9991, segments=[[0, 3]])
    assert report(client, seed["learner_id"], published_content, payload).status_code == 200


def test_video_changed_is_conflict_without_writes(client, seed, published_content, database):
    payload = {**body(published_content), "media_revision": str(uuid4())}
    result = report(client, seed["learner_id"], published_content, payload)
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "VIDEO_CHANGED"
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_visits")) == 0


def test_visit_cannot_change_context(client, seed, published_content):
    payload = body(published_content)
    assert report(client, seed["learner_id"], published_content, payload).status_code == 200
    result = report(client, seed["learner_id"], published_content, {**payload, "context": "SEARCH"})
    assert result.status_code == 422


def test_generation_role_and_target(client, seed, published_content):
    uid, pc = seed["learner_id"], published_content
    assert report(client, uid, pc, body(pc), generation=3).status_code == 409
    path = f"/api/users/{uid}/contents/{pc['content_id']}/watch-reports"
    assert client.post(path, json=body(pc), headers={"X-Actor-Id": str(uid)}).status_code == 422
    assert (
        client.post(
            path,
            json=body(pc),
            headers={
                "X-Actor-Id": str(seed["admin_id"]),
                "X-Record-Generation": "0",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            path.replace(f"/users/{uid}/", "/users/9999999/"),
            json=body(pc),
            headers={
                "X-Actor-Id": str(uid),
                "X-Record-Generation": "0",
            },
        ).status_code
        == 404
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["actual_played_seconds", "watched_segments"])
def test_nonfinite_reports_are_rejected(client, seed, published_content, value, field):
    uid, pc = seed["learner_id"], published_content
    payload = body(pc)
    payload[field] = value if field == "actual_played_seconds" else [[0, value]]
    result = client.post(
        f"/api/users/{uid}/contents/{pc['content_id']}/watch-reports",
        content=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "X-Actor-Id": str(uid),
            "X-Record-Generation": "0",
        },
    )
    assert result.status_code == 422, result.text
    assert result.json()["detail"]["code"] == "INVALID_WATCH_REPORT"


def test_visit_id_cannot_be_reused_by_another_learner(client, seed, published_content, database):
    uid, pc = seed["learner_id"], published_content
    payload = body(pc)
    assert report(client, uid, pc, payload).status_code == 200
    other = database.scalar(
        text(
            "INSERT INTO sasu.app_users (username, display_name, role) "
            "VALUES ('other_visit', '다른 학습자', 'LEARNER') RETURNING user_id"
        )
    )
    database.execute(text("INSERT INTO sasu.user_settings(user_id) VALUES (:u)"), {"u": other})
    result = report(client, other, pc, payload)
    assert result.status_code == 422
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_records")) == 1
