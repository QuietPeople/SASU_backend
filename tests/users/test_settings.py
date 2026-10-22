"""USR-03~06 사용자 설정·피드 위치 API 검증 (PostgreSQL 필요)."""

import pytest
from sqlalchemy import text


# ───────────────────────────── USR-03 설정 조회 ─────────────────────────────


class TestGetSettings:
    def test_returns_defaults_for_learner(self, client, seed):
        uid = seed["learner_id"]
        resp = client.get(f"/api/users/{uid}/settings", headers={"X-Actor-Id": str(uid)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["onboarding_status"] == "PENDING"
        assert body["review_interval"] == 5
        assert body["interests"] == []
        assert body["record_generation"] == 0

    def test_includes_interests_when_set(self, client, seed, database):
        uid = seed["learner_id"]
        cat_id = seed["cat_ids"][0]
        database.execute(
            text("INSERT INTO sasu.user_interests (user_id, category_id) VALUES (:u, :c)"),
            {"u": uid, "c": cat_id},
        )
        database.flush()
        resp = client.get(f"/api/users/{uid}/settings", headers={"X-Actor-Id": str(uid)})
        assert resp.status_code == 200
        interests = resp.json()["interests"]
        assert len(interests) == 1
        assert interests[0]["category_id"] == cat_id

    def test_rejects_other_user(self, client, seed):
        learner = seed["learner_id"]
        admin = seed["admin_id"]
        resp = client.get(f"/api/users/{learner}/settings", headers={"X-Actor-Id": str(admin)})
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "USER_NOT_FOUND"

    def test_rejects_missing_actor(self, client, seed):
        uid = seed["learner_id"]
        resp = client.get(f"/api/users/{uid}/settings", headers={"X-Actor-Id": "99999"})
        assert resp.status_code == 404

    def test_requires_actor_header(self, client, seed):
        uid = seed["learner_id"]
        resp = client.get(f"/api/users/{uid}/settings")
        assert resp.status_code == 422


# ───────────────────────────── USR-04 설정 변경 ─────────────────────────────


class TestPatchSettings:
    def _headers(self, uid, generation=0):
        return {"X-Actor-Id": str(uid), "X-Record-Generation": str(generation)}

    def test_updates_onboarding_status(self, client, seed):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"onboarding_status": "DONE"},
        )
        assert resp.status_code == 200
        assert resp.json()["onboarding_status"] == "DONE"

    def test_updates_review_interval(self, client, seed):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"review_interval": 10},
        )
        assert resp.status_code == 200
        assert resp.json()["review_interval"] == 10

    def test_replaces_interests(self, client, seed):
        uid = seed["learner_id"]
        cat_ids = seed["cat_ids"][:2]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"interest_category_ids": cat_ids},
        )
        assert resp.status_code == 200
        returned_ids = [i["category_id"] for i in resp.json()["interests"]]
        assert sorted(returned_ids) == sorted(cat_ids)

    def test_clears_interests_with_empty_list(self, client, seed, database):
        uid = seed["learner_id"]
        database.execute(
            text("INSERT INTO sasu.user_interests (user_id, category_id) VALUES (:u, :c)"),
            {"u": uid, "c": seed["cat_ids"][0]},
        )
        database.flush()
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"interest_category_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["interests"] == []

    def test_empty_body_returns_unchanged_settings(self, client, seed):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["onboarding_status"] == "PENDING"

    def test_rejects_stale_generation(self, client, seed):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid, generation=5),
            json={"onboarding_status": "DONE"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"

    def test_rejects_admin_actor(self, client, seed):
        learner = seed["learner_id"]
        admin = seed["admin_id"]
        resp = client.patch(
            f"/api/users/{learner}/settings",
            headers={"X-Actor-Id": str(admin), "X-Record-Generation": "0"},
            json={"onboarding_status": "DONE"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"

    def test_rejects_other_learner(self, client, seed, database):
        uid = seed["learner_id"]
        other_id = database.scalar(
            text(
                "INSERT INTO sasu.app_users (username, display_name, role)"
                " VALUES ('other', '다른 학습자', 'LEARNER') RETURNING user_id"
            )
        )
        database.execute(
            text("INSERT INTO sasu.user_settings (user_id) VALUES (:uid)"),
            {"uid": other_id},
        )
        database.flush()
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers={"X-Actor-Id": str(other_id), "X-Record-Generation": "0"},
            json={"onboarding_status": "DONE"},
        )
        assert resp.status_code == 404

    def test_rejects_invalid_category_id(self, client, seed):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"interest_category_ids": [99999]},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize("interval", [0, 21])
    def test_rejects_out_of_range_review_interval(self, client, seed, interval):
        uid = seed["learner_id"]
        resp = client.patch(
            f"/api/users/{uid}/settings",
            headers=self._headers(uid),
            json={"review_interval": interval},
        )
        assert resp.status_code == 422


# ───────────────────────────── USR-05 피드 위치 조회 ─────────────────────────


class TestGetFeedPosition:
    def test_returns_null_when_not_set(self, client, seed):
        uid = seed["learner_id"]
        resp = client.get(
            f"/api/users/{uid}/feed-position", headers={"X-Actor-Id": str(uid)}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_content_id"] is None
        assert body["resume_unavailable"] is False

    def test_returns_content_id_when_set(self, client, seed, published_content, database):
        uid = seed["learner_id"]
        database.execute(
            text(
                "UPDATE sasu.user_settings SET last_content_id = :cid WHERE user_id = :uid"
            ),
            {"cid": published_content, "uid": uid},
        )
        database.flush()
        resp = client.get(
            f"/api/users/{uid}/feed-position", headers={"X-Actor-Id": str(uid)}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_content_id"] == published_content
        assert body["resume_unavailable"] is False

    def test_resume_unavailable_when_content_unpublished(self, client, seed, published_content, database):
        uid = seed["learner_id"]
        database.execute(
            text("UPDATE sasu.contents SET status = 'DRAFT' WHERE content_id = :cid"),
            {"cid": published_content},
        )
        database.execute(
            text("UPDATE sasu.user_settings SET last_content_id = :cid WHERE user_id = :uid"),
            {"cid": published_content, "uid": uid},
        )
        database.flush()
        resp = client.get(
            f"/api/users/{uid}/feed-position", headers={"X-Actor-Id": str(uid)}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["last_content_id"] is None
        assert body["resume_unavailable"] is True

    def test_rejects_other_user(self, client, seed):
        learner = seed["learner_id"]
        admin = seed["admin_id"]
        resp = client.get(
            f"/api/users/{learner}/feed-position", headers={"X-Actor-Id": str(admin)}
        )
        assert resp.status_code == 404


# ───────────────────────────── USR-06 피드 위치 반영 ─────────────────────────


class TestUpdateFeedPosition:
    def _headers(self, uid, generation=0):
        return {"X-Actor-Id": str(uid), "X-Record-Generation": str(generation)}

    def test_updates_last_content_id_when_feed_context(
        self, client, seed, published_content, database
    ):
        uid = seed["learner_id"]
        resp = client.put(
            f"/api/users/{uid}/feed-position",
            headers=self._headers(uid),
            json={"content_id": published_content, "context": "FEED"},
        )
        assert resp.status_code == 204
        stored = database.scalar(
            text("SELECT last_content_id FROM sasu.user_settings WHERE user_id = :uid"),
            {"uid": uid},
        )
        assert stored == published_content

    def test_does_not_update_on_non_feed_context(
        self, client, seed, published_content, database
    ):
        uid = seed["learner_id"]
        resp = client.put(
            f"/api/users/{uid}/feed-position",
            headers=self._headers(uid),
            json={"content_id": published_content, "context": "SEARCH"},
        )
        assert resp.status_code == 204
        stored = database.scalar(
            text("SELECT last_content_id FROM sasu.user_settings WHERE user_id = :uid"),
            {"uid": uid},
        )
        assert stored is None

    def test_rejects_unpublished_content_on_feed(self, client, seed, published_content, database):
        uid = seed["learner_id"]
        database.execute(
            text("UPDATE sasu.contents SET status = 'DRAFT' WHERE content_id = :cid"),
            {"cid": published_content},
        )
        database.flush()
        resp = client.put(
            f"/api/users/{uid}/feed-position",
            headers=self._headers(uid),
            json={"content_id": published_content, "context": "FEED"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "CONTENT_NOT_FOUND"

    def test_rejects_stale_generation(self, client, seed, published_content):
        uid = seed["learner_id"]
        resp = client.put(
            f"/api/users/{uid}/feed-position",
            headers=self._headers(uid, generation=3),
            json={"content_id": published_content, "context": "FEED"},
        )
        assert resp.status_code == 409

    def test_rejects_admin_actor(self, client, seed, published_content):
        learner = seed["learner_id"]
        admin = seed["admin_id"]
        resp = client.put(
            f"/api/users/{learner}/feed-position",
            headers={"X-Actor-Id": str(admin), "X-Record-Generation": "0"},
            json={"content_id": published_content, "context": "FEED"},
        )
        assert resp.status_code == 403
