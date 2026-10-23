from uuid import uuid4

import pytest
from sqlalchemy import text


def send(client, uid, body, generation=0, actor=None):
    return client.post(
        f"/api/users/{uid}/events",
        json=body,
        headers={
            "X-Actor-Id": str(actor or uid),
            "X-Record-Generation": str(generation),
        },
    )


def event(kind="SEARCH_EMPTY", **fields):
    return {"client_event_id": str(uuid4()), "event_type": kind, **fields}


def test_event_contract_replay_and_conflict(client, seed, published_content, database):
    uid = seed["learner_id"]
    payload = event()
    created = send(client, uid, payload)
    assert created.status_code == 201, created.text
    result = created.json()
    assert set(result) == {"event_id", "client_event_id", "event_type", "occurred_at", "recorded"}
    assert result["event_id"] == payload["client_event_id"]
    assert result["recorded"]
    replay = send(client, uid, payload)
    assert replay.status_code == 200
    assert replay.json() == {**result, "recorded": False}
    conflict = send(
        client,
        uid,
        {**payload, "event_type": "PLAY_ERROR", "content_id": published_content["content_id"]},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "EVENT_ID_CONFLICT"
    assert database.scalar(text("SELECT count(*) FROM sasu.learning_events")) == 1


@pytest.mark.parametrize(
    "kind,db_kind", [("FLASHCARD_VIEWED", "CARD_OPENED"), ("FLASHCARD_FLIPPED", "CARD_REVEALED")]
)
def test_card_events_use_api_names_and_keep_db_types(
    client, seed, published_quiz, database, kind, db_kind
):
    q = published_quiz
    result = send(
        client,
        seed["learner_id"],
        event(kind, content_id=q["content_id"], question_version_id=q["quiz_version_id"]),
    )
    assert result.status_code == 201, result.text
    assert result.json()["event_type"] == kind
    assert database.scalar(text("SELECT event_type FROM sasu.learning_events")) == db_kind
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0


def test_quiz_derives_content_and_deduplicates_different_keys(client, seed, quiz_attempt, database):
    uid = seed["learner_id"]
    payload = event("VIDEO_QUIZ_SHOWN", attempt_id=quiz_attempt["attempt_id"])
    first = send(client, uid, payload)
    assert first.status_code == 201, first.text
    duplicate = {**payload, "client_event_id": str(uuid4())}
    second = send(client, uid, duplicate)
    assert second.status_code == 200, second.text
    assert second.json() == {**first.json(), "recorded": False}
    assert database.scalar(text("SELECT count(*) FROM sasu.learning_events")) == 1
    assert send(client, uid, duplicate).status_code == 200
    reused = send(
        client, uid, {"client_event_id": duplicate["client_event_id"], "event_type": "SEARCH_EMPTY"}
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "EVENT_ID_CONFLICT"


@pytest.mark.parametrize(
    "changes",
    [
        {"event_type": "FEED_REVIEW_SHOWN"},
        {"content_id": 9999999},
        {"question_version_id": 9999999},
    ],
)
def test_quiz_event_rejects_wrong_relation(client, seed, quiz_attempt, changes):
    payload = {**event("VIDEO_QUIZ_SHOWN", attempt_id=quiz_attempt["attempt_id"]), **changes}
    result = send(client, seed["learner_id"], payload)
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "INVALID_EVENT_RELATION"


def test_missing_attempt_and_version(client, seed, published_content):
    uid = seed["learner_id"]
    result = send(client, uid, event("VIDEO_QUIZ_SHOWN", attempt_id=str(uuid4())))
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"
    result = send(
        client,
        uid,
        event(
            "FLASHCARD_VIEWED",
            content_id=published_content["content_id"],
            question_version_id=9999999,
        ),
    )
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "QUESTION_VERSION_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"event_type": "VIDEO_QUIZ_SHOWN"},
        {"event_type": "FLASHCARD_VIEWED", "content_id": 1},
        {"event_type": "SEARCH_EMPTY", "content_id": 1},
        {"event_type": "SEARCH_EMPTY", "attempt_id": str(uuid4())},
        {"event_type": "PLAY_ERROR"},
        {"event_type": "SEARCH_EMPTY", "error_code": "ERR"},
    ],
)
def test_invalid_event_shapes(client, seed, payload):
    result = send(client, seed["learner_id"], {"client_event_id": str(uuid4()), **payload})
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "INVALID_EVENT_RELATION"


def test_arbitrary_metadata_rejected_and_error_code_not_persisted(
    client, seed, published_content, database
):
    uid = seed["learner_id"]
    payload = event("PLAY_ERROR", content_id=published_content["content_id"])
    assert send(client, uid, {**payload, "metadata": {"query": "private"}}).status_code == 422
    result = send(client, uid, {**payload, "error_code": "DECODE_ERROR"})
    assert result.status_code == 201
    assert database.scalar(text("SELECT metadata FROM sasu.learning_events")) == {}


def test_event_permissions_and_generation(client, seed):
    uid = seed["learner_id"]
    assert send(client, uid, event(), generation=5).status_code == 409
    assert send(client, uid, event(), actor=seed["admin_id"]).status_code == 403
    assert send(client, 9999999, event(), actor=uid).status_code == 404
    assert client.post(f"/api/users/{uid}/events", json=event()).status_code == 422


def test_private_content_is_rejected(client, seed, published_content, database):
    cid = published_content["content_id"]
    database.execute(
        text("UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:c"), {"c": cid}
    )
    result = send(client, seed["learner_id"], event("PLAY_ERROR", content_id=cid))
    assert result.status_code == 404


def test_watch_quiz_event_response_review_and_statistics_flow(
    client, seed, published_quiz, database
):
    uid, admin = seed["learner_id"], seed["admin_id"]
    q = published_quiz
    cid, qid, vid = q["content_id"], q["quiz_id"], q["quiz_version_id"]
    headers = {"X-Actor-Id": str(uid), "X-Record-Generation": "0"}
    asset = database.scalar(
        text("SELECT video_asset_id FROM sasu.contents WHERE content_id=:c"), {"c": cid}
    )
    watch = client.post(
        f"/api/users/{uid}/contents/{cid}/watch-reports",
        headers=headers,
        json={
            "visit_id": str(uuid4()),
            "media_revision": str(asset),
            "actual_played_seconds": 54,
            "watched_segments": [[0, 54]],
            "context": "FEED",
        },
    )
    assert watch.status_code == 200, watch.text
    assert watch.json()["watch_completed"]
    attempt_id = str(uuid4())
    start = client.post(
        f"/api/users/{uid}/question-attempts",
        headers=headers,
        json={
            "attempt_id": attempt_id,
            "question_id": qid,
            "expected_question_version_id": vid,
            "response_path": "VIDEO_QUIZ",
        },
    )
    assert start.status_code == 201, start.text
    wrong_option = database.scalar(
        text(
            "SELECT option_id FROM sasu.quiz_options WHERE quiz_version_id=:v"
            " AND NOT is_correct ORDER BY position LIMIT 1"
        ),
        {"v": vid},
    )
    answer_url = f"/api/users/{uid}/question-attempts/{attempt_id}/response"
    answer = {"action": "ANSWER", "selected_option_id": wrong_option}
    assert client.put(answer_url, headers=headers, json=answer).status_code == 409
    shown = send(client, uid, event("VIDEO_QUIZ_SHOWN", attempt_id=attempt_id))
    assert shown.status_code == 201, shown.text
    submitted = client.put(answer_url, headers=headers, json=answer)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["result"] == "WRONG"
    assert (
        client.put(answer_url, headers=headers, json=answer).json()["response_id"]
        == submitted.json()["response_id"]
    )

    wrongs = client.get(f"/api/users/{uid}/reviews/wrong-answers", headers=headers)
    assert wrongs.status_code == 200, wrongs.text
    assert wrongs.json()["total"] == 1
    retry_id = str(uuid4())
    retry = client.post(
        f"/api/users/{uid}/question-attempts",
        headers=headers,
        json={
            "attempt_id": retry_id,
            "question_id": qid,
            "expected_question_version_id": vid,
            "response_path": "WRONG_NOTE",
        },
    )
    assert retry.status_code == 201, retry.text
    correct = database.scalar(
        text("SELECT option_id FROM sasu.quiz_options WHERE quiz_version_id=:v AND is_correct"),
        {"v": vid},
    )
    result = client.put(
        f"/api/users/{uid}/question-attempts/{retry_id}/response",
        headers=headers,
        json={"action": "ANSWER", "selected_option_id": correct},
    )
    assert result.status_code == 200, result.text
    assert result.json()["result"] == "CORRECT"
    assert (
        client.get(f"/api/users/{uid}/reviews/wrong-answers", headers=headers).json()["total"] == 0
    )
    dashboard = client.get(f"/api/users/{uid}/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["completed_content_count"] == 1
    assert dashboard.json()["pending_question_count"] == 0
    stats = client.get(f"/api/contents/{cid}/statistics", headers={"X-Actor-Id": str(admin)})
    assert stats.status_code == 200, stats.text
    assert stats.json()["reactions"]["view_count"] == 1
    assert stats.json()["quiz"]["shown_count"] == 1
    assert stats.json()["quiz"]["answered_count"] == 1
    assert stats.json()["wrong_review"]["answered_count"] == 1


def test_client_key_cannot_be_reused_by_another_learner(client, seed, database):
    payload = event()
    assert send(client, seed["learner_id"], payload).status_code == 201
    other = database.scalar(
        text(
            "INSERT INTO sasu.app_users (username, display_name, role) "
            "VALUES ('other_event', '다른 학습자', 'LEARNER') RETURNING user_id"
        )
    )
    database.execute(text("INSERT INTO sasu.user_settings(user_id) VALUES (:u)"), {"u": other})
    result = send(client, other, payload)
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "EVENT_ID_CONFLICT"
    assert database.scalar(text("SELECT count(*) FROM sasu.learning_events")) == 1


def test_feed_review_display_maps_to_existing_statistics_event(
    client, seed, quiz_attempt, database
):
    attempt_id = str(uuid4())
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
            (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
            SELECT :id, user_id, learning_epoch, quiz_id, quiz_version_id, 'FEED_REVIEW'
            FROM sasu.quiz_attempts WHERE attempt_id=:original"""),
        {"id": attempt_id, "original": quiz_attempt["attempt_id"]},
    )
    result = send(client, seed["learner_id"], event("FEED_REVIEW_SHOWN", attempt_id=attempt_id))
    assert result.status_code == 201, result.text
    assert result.json()["event_type"] == "FEED_REVIEW_SHOWN"
    assert database.scalar(text("SELECT event_type FROM sasu.learning_events")) == "QUIZ_DISPLAYED"
