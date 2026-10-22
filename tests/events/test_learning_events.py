"""EVT-01 학습 이벤트 보고 API 테스트."""

from uuid import uuid4

import pytest
from sqlalchemy import text


def _url(event_id=None):
    eid = event_id or str(uuid4())
    return f"/api/events/{eid}", eid


class TestBasic:
    def test_playback_error_returns_204(self, client, seed, published_content):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 204

    def test_search_empty_returns_204(self, client, seed):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "SEARCH_EMPTY"},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 204

    def test_missing_actor_header_returns_422(self, client, seed, published_content):
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Record-Generation": "0"},
        )
        assert resp.status_code == 422

    def test_missing_generation_header_returns_422(self, client, seed, published_content):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Actor-Id": str(learner_id)},
        )
        assert resp.status_code == 422

    def test_event_persisted_in_db(self, client, database, seed, published_content):
        learner_id = seed["learner_id"]
        url, event_id = _url()
        client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        row = database.execute(
            text("SELECT event_type FROM sasu.learning_events WHERE event_id = :eid"),
            {"eid": event_id},
        ).one_or_none()
        assert row is not None
        assert row[0] == "PLAYBACK_ERROR"


class TestQuizEvents:
    def test_card_opened_returns_204(self, client, seed, published_quiz):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={
                "event_type": "CARD_OPENED",
                "content_id": published_quiz["content_id"],
                "quiz_version_id": published_quiz["quiz_version_id"],
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 204

    def test_card_revealed_returns_204(self, client, seed, published_quiz):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={
                "event_type": "CARD_REVEALED",
                "content_id": published_quiz["content_id"],
                "quiz_version_id": published_quiz["quiz_version_id"],
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 204

    def test_quiz_displayed_returns_204(self, client, seed, quiz_attempt):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={
                "event_type": "QUIZ_DISPLAYED",
                "content_id": quiz_attempt["content_id"],
                "quiz_version_id": quiz_attempt["quiz_version_id"],
                "attempt_id": quiz_attempt["attempt_id"],
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 204

    def test_metadata_stored(self, client, database, seed, published_content):
        learner_id = seed["learner_id"]
        url, event_id = _url()
        client.put(
            url,
            json={
                "event_type": "PLAYBACK_ERROR",
                "content_id": published_content["content_id"],
                "metadata": {"error_code": "DECODE_ERROR"},
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        meta = database.scalar(
            text("SELECT metadata FROM sasu.learning_events WHERE event_id = :eid"),
            {"eid": event_id},
        )
        assert meta is not None
        assert meta.get("error_code") == "DECODE_ERROR"


class TestDedup:
    def test_same_event_id_twice_both_204(self, client, seed, published_content):
        learner_id = seed["learner_id"]
        url, _ = _url()
        body = {
            "event_type": "PLAYBACK_ERROR",
            "content_id": published_content["content_id"],
        }
        headers = {"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"}
        r1 = client.put(url, json=body, headers=headers)
        r2 = client.put(url, json=body, headers=headers)
        assert r1.status_code == 204
        assert r2.status_code == 204

    def test_duplicate_not_stored_twice(self, client, database, seed, published_content):
        learner_id = seed["learner_id"]
        url, event_id = _url()
        body = {
            "event_type": "PLAYBACK_ERROR",
            "content_id": published_content["content_id"],
        }
        headers = {"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"}
        client.put(url, json=body, headers=headers)
        client.put(url, json=body, headers=headers)
        count = database.scalar(
            text("SELECT count(*) FROM sasu.learning_events WHERE event_id = :eid"),
            {"eid": event_id},
        )
        assert count == 1


class TestErrorCases:
    def test_admin_returns_403(self, client, seed, published_content):
        admin_id = seed["admin_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Actor-Id": str(admin_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 403

    def test_unknown_actor_returns_404(self, client, seed):
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "SEARCH_EMPTY"},
            headers={"X-Actor-Id": "99999", "X-Record-Generation": "0"},
        )
        assert resp.status_code == 404

    def test_draft_content_returns_404(self, client, database, seed):
        admin_id = seed["admin_id"]
        learner_id = seed["learner_id"]
        cat_id = database.scalar(
            text("INSERT INTO sasu.categories (name) VALUES ('드래프트') RETURNING category_id")
        )
        content_id = database.scalar(
            text(
                "INSERT INTO sasu.contents"
                " (created_by_user_id, category_id, title, status)"
                " VALUES (:uid, :cat, '임시', 'DRAFT') RETURNING content_id"
            ),
            {"uid": admin_id, "cat": cat_id},
        )
        database.flush()
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": content_id},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 404

    def test_stale_epoch_returns_409(self, client, database, seed, published_content):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": published_content["content_id"]},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "99"},
        )
        assert resp.status_code == 409

    def test_search_empty_with_content_id_returns_422(self, client, seed, published_content):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={
                "event_type": "SEARCH_EMPTY",
                "content_id": published_content["content_id"],
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 422

    def test_quiz_displayed_without_attempt_returns_422(self, client, seed, published_quiz):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={
                "event_type": "QUIZ_DISPLAYED",
                "content_id": published_quiz["content_id"],
                "quiz_version_id": published_quiz["quiz_version_id"],
                # attempt_id missing
            },
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 422

    def test_playback_error_without_content_id_returns_422(self, client, seed):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR"},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 422

    def test_nonexistent_content_returns_404(self, client, seed):
        learner_id = seed["learner_id"]
        url, _ = _url()
        resp = client.put(
            url,
            json={"event_type": "PLAYBACK_ERROR", "content_id": 999999},
            headers={"X-Actor-Id": str(learner_id), "X-Record-Generation": "0"},
        )
        assert resp.status_code == 404
