"""WCH-01 시청 방문 보고 API 검증 (PostgreSQL 필요)."""

from uuid import uuid4

import pytest
from sqlalchemy import text


def _url(content_id, visit_id):
    return f"/api/contents/{content_id}/watch-visits/{visit_id}"


def _headers(uid, generation=0):
    return {"X-Actor-Id": str(uid), "X-Record-Generation": str(generation)}


def _body(asset_id, context="FEED", elapsed=0.0, ranges=None, sequence=0):
    return {
        "video_asset_id": asset_id,
        "context": context,
        "elapsed_seconds": elapsed,
        "watched_ranges": ranges or [],
        "sequence": sequence,
    }


# ─────────────────────────── 기본 동작 ───────────────────────────


class TestWatchVisitBasic:
    def test_creates_visit_and_returns_200(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        visit_id = str(uuid4())
        resp = client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["view_counted"] is False
        assert body["completed"] is False
        assert body["coverage"] == pytest.approx(0.0)
        assert body["video_changed"] is False

    def test_visit_row_persisted(self, client, seed, published_content, database):
        uid = seed["learner_id"]
        pc = published_content
        visit_id = str(uuid4())
        client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"]),
        )
        row = database.execute(
            text("SELECT visit_id FROM sasu.watch_visits WHERE visit_id = :vid"),
            {"vid": visit_id},
        ).one_or_none()
        assert row is not None

    def test_requires_actor_header(self, client, seed, published_content):
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers={"X-Record-Generation": "0"},
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 422

    def test_requires_generation_header(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers={"X-Actor-Id": str(uid)},
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 422


# ─────────────────────────── 3초 조회 인정 ───────────────────────────


class TestViewCounting:
    def test_not_counted_below_3s(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=2.9),
        )
        assert resp.status_code == 200
        assert resp.json()["view_counted"] is False

    def test_counted_at_3s(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=3.0),
        )
        assert resp.status_code == 200
        assert resp.json()["view_counted"] is True

    def test_second_visit_above_3s_not_counted_again(
        self, client, seed, published_content, database
    ):
        uid = seed["learner_id"]
        pc = published_content
        # First visit: set view_counted_at
        client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=5.0),
        )
        # Second visit: same user, same content, elapsed >= 3 again
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=4.0),
        )
        assert resp.status_code == 200
        assert resp.json()["view_counted"] is False

    def test_watch_record_view_counted_at_set(
        self, client, seed, published_content, database
    ):
        uid = seed["learner_id"]
        pc = published_content
        client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=10.0),
        )
        row = database.execute(
            text(
                "SELECT view_counted_at FROM sasu.watch_records"
                " WHERE user_id = :uid AND content_id = :cid"
            ),
            {"uid": uid, "cid": pc["content_id"]},
        ).mappings().one_or_none()
        assert row is not None
        assert row["view_counted_at"] is not None


# ─────────────────────────── 90% 완료 ───────────────────────────


class TestCompletion:
    def test_not_completed_below_90_percent(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        # duration=60, 89% = 53.4s
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=55.0, ranges=[[0.0, 53.4]]),
        )
        assert resp.status_code == 200
        assert resp.json()["completed"] is False

    def test_completed_at_90_percent(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        # duration=60, 90% = 54s
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=56.0, ranges=[[0.0, 54.0]]),
        )
        assert resp.status_code == 200
        assert resp.json()["completed"] is True

    def test_completed_persists_across_visits(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        # First visit completes
        client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=60.0, ranges=[[0.0, 60.0]]),
        )
        # Second visit (no ranges)
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=0.0),
        )
        assert resp.json()["completed"] is True

    def test_coverage_calculation_with_overlapping_ranges(
        self, client, seed, published_content
    ):
        uid = seed["learner_id"]
        pc = published_content
        # duration=60; [[0,30],[20,50]] → merged [0,50] → 50/60 ≈ 0.833
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=50.0, ranges=[[0.0, 30.0], [20.0, 50.0]]),
        )
        assert resp.status_code == 200
        assert resp.json()["coverage"] == pytest.approx(50.0 / 60.0, abs=1e-6)

    def test_coverage_clips_to_duration(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        # End beyond duration should be clipped
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=60.0, ranges=[[0.0, 100.0]]),
        )
        assert resp.status_code == 200
        assert resp.json()["coverage"] == pytest.approx(1.0)


# ─────────────────────────── 순번(sequence) 처리 ───────────────────────────


class TestSequenceHandling:
    def test_stale_sequence_returns_current_state(
        self, client, seed, published_content
    ):
        uid = seed["learner_id"]
        pc = published_content
        visit_id = str(uuid4())
        # First report with sequence=2
        client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=3.0, sequence=2),
        )
        # Stale report with sequence=1 (lower)
        resp = client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=0.0, sequence=1),
        )
        assert resp.status_code == 200
        # view_counted should still reflect state from seq=2
        assert resp.json()["view_counted"] is False

    def test_higher_sequence_updates_visit(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        visit_id = str(uuid4())
        # First report: elapsed=2 (not yet counted)
        r1 = client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=2.0, sequence=1),
        )
        assert r1.json()["view_counted"] is False
        # Second report with higher seq: elapsed=5 (now counted)
        r2 = client.put(
            _url(pc["content_id"], visit_id),
            headers=_headers(uid),
            json=_body(pc["asset_id"], elapsed=5.0, sequence=2),
        )
        assert r2.json()["view_counted"] is True


# ─────────────────────────── 오류 처리 ───────────────────────────


class TestErrorCases:
    def test_rejects_admin_actor(self, client, seed, published_content):
        admin = seed["admin_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(admin),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "ROLE_NOT_ALLOWED"

    def test_rejects_unknown_actor(self, client, seed, published_content):
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(99999),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 404

    def test_rejects_unpublished_content(self, client, seed, published_content, database):
        uid = seed["learner_id"]
        pc = published_content
        database.execute(
            text("UPDATE sasu.contents SET status = 'DRAFT' WHERE content_id = :cid"),
            {"cid": pc["content_id"]},
        )
        database.flush()
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "CONTENT_NOT_FOUND"

    def test_rejects_stale_generation(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid, generation=5),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"

    def test_rejects_invalid_range_format(self, client, seed, published_content):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json={**_body(pc["asset_id"]), "watched_ranges": [[10.0, 5.0]]},
        )
        assert resp.status_code == 422

    def test_rejects_nonexistent_content(self, client, seed):
        uid = seed["learner_id"]
        resp = client.put(
            _url(99999, str(uuid4())),
            headers=_headers(uid),
            json=_body(str(uuid4())),
        )
        assert resp.status_code == 404


# ─────────────────────────── VIDEO_CHANGED ───────────────────────────


class TestVideoChanged:
    def test_video_changed_when_asset_differs(
        self, client, seed, published_content, database
    ):
        uid = seed["learner_id"]
        pc = published_content
        # Replace the content's video asset with a new one
        new_asset_id = str(uuid4())
        database.execute(
            text(
                "INSERT INTO sasu.video_assets"
                " (video_asset_id, storage_path, original_name, mime_type, size_bytes, duration_seconds)"
                " VALUES (:aid, 'videos/new.mp4', 'new.mp4', 'video/mp4', 1048576, 60.0)"
            ),
            {"aid": new_asset_id},
        )
        database.execute(
            text("UPDATE sasu.contents SET video_asset_id = :aid WHERE content_id = :cid"),
            {"aid": new_asset_id, "cid": pc["content_id"]},
        )
        database.flush()
        # Report using old asset_id
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["video_changed"] is True
        assert resp.json()["view_counted"] is False

    def test_no_video_changed_when_asset_matches(
        self, client, seed, published_content
    ):
        uid = seed["learner_id"]
        pc = published_content
        resp = client.put(
            _url(pc["content_id"], str(uuid4())),
            headers=_headers(uid),
            json=_body(pc["asset_id"]),
        )
        assert resp.status_code == 200
        assert resp.json()["video_changed"] is False
