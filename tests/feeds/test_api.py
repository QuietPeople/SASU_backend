"""조회·연결 계약만 검증하며 파트 2의 추천 정책은 구현하지 않는다."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.modules.feeds.contracts import RankedFeedItem
from app.modules.feeds.service import get_feed_ranker


def feed(client, records, **kwargs):
    return client.get(
        f"/api/users/{records['learner']}/feed",
        headers={"X-Actor-Id": str(records["learner"])},
        **kwargs,
    )


def watch(database, records, content_id, *, completed=False, latest=True):
    database.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id, first_played_at, last_watched_at,
                 completed_at, max_coverage_ratio)
                VALUES (:user, 1, :content, now() - interval '2 days',
                        CASE WHEN :latest THEN now() ELSE now() - interval '1 day' END,
                        CASE WHEN :completed THEN now() ELSE NULL END,
                        CASE WHEN :completed THEN 0.95 ELSE 0.1 END)"""),
        {
            "user": records["learner"],
            "content": content_id,
            "completed": completed,
            "latest": latest,
        },
    )


def test_empty_feed_is_success_without_generation_header(client, records):
    def rank(context):
        assert context.candidates == ()
        assert context.interest_category_ids == frozenset()
        assert context.recent_watched_tag_ids == frozenset()
        assert context.resume_content_id is None
        return []

    client.app.dependency_overrides[get_feed_ranker] = lambda: rank
    response = feed(client, records)
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "resume_unavailable": False, "record_generation": 0}


def test_all_playable_public_contents_and_shared_summary(client, records, content_factory):
    valid = [content_factory(), content_factory(mime_type="video/webm")]
    content_factory(status="DRAFT")
    content_factory(media="missing")
    content_factory(media="truncated")
    content_factory(mime_type="video/quicktime")
    response = feed(client, records)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"items", "resume_unavailable", "record_generation"}
    assert {item["content"]["content_id"] for item in payload["items"]} == set(valid)
    for item in payload["items"]:
        summary = item["content"]
        assert summary["category"]["category_id"] == records["category_id"]
        assert [tag["tag_id"] for tag in summary["tags"]] == [records["tag_id"]]
        assert summary["liked"] is summary["saved"] is summary["watch_completed"] is False
        assert summary["has_quiz"] is False  # 퀴즈 유무는 영상 피드의 제외 조건이 아니다.
        assert summary["status"] == "PUBLISHED"
        assert summary["media_revision"] in summary["video_url"]
        assert set(item) == {"content", "recommendation_reason", "recommendation_label"}


def test_candidate_universe_has_no_search_page_limit(client, records, content_factory):
    published = datetime(2026, 10, 1, tzinfo=UTC)
    ids = [content_factory(published_at=published) for _ in range(105)]
    captured = []

    def rank(context):
        captured.append(context)
        return [
            RankedFeedItem(item.content_id, "LATEST", "연결 확인") for item in context.candidates
        ]

    client.app.dependency_overrides[get_feed_ranker] = lambda: rank
    response = feed(client, records)
    assert response.status_code == 200, response.text
    assert [item.content_id for item in captured[0].candidates] == ids
    assert len(response.json()["items"]) == 105


def test_ranker_receives_actual_watch_context_and_controls_response(
    client, database, records, content_factory
):
    resume = content_factory()
    incomplete = content_factory()
    fresh = content_factory()
    latest_tag = database.scalar(
        text("INSERT INTO sasu.tags (name) VALUES ('최근 시청 태그') RETURNING tag_id")
    )
    latest = content_factory(status="DRAFT", tag_ids=[latest_tag])
    database.execute(
        text("INSERT INTO sasu.user_interests (user_id, category_id) VALUES (:user, :category)"),
        {"user": records["learner"], "category": records["category_id"]},
    )
    database.execute(
        text("UPDATE sasu.user_settings SET last_content_id = :content WHERE user_id = :user"),
        {"user": records["learner"], "content": resume},
    )
    watch(database, records, resume, completed=True, latest=False)
    watch(database, records, incomplete, latest=False)
    watch(database, records, latest)
    for table in ("content_likes", "saved_contents"):
        database.execute(
            text(
                f"INSERT INTO sasu.{table} (user_id, learning_epoch, content_id) "
                "VALUES (:user, 1, :content)"
            ),
            {"user": records["learner"], "content": resume},
        )
    database.commit()
    captured = []

    def rank(context):
        captured.append(context)
        return [
            RankedFeedItem(fresh, "RELATED_TAG", "추천 담당자가 반환한 라벨"),
            RankedFeedItem(incomplete, "UNWATCHED", "순서 전달 확인"),
            RankedFeedItem(resume, "LAST_CONTENT", "재개 항목"),
        ]

    client.app.dependency_overrides[get_feed_ranker] = lambda: rank
    response = feed(client, records)
    assert response.status_code == 200, response.text
    context = captured[0]
    assert context.interest_category_ids == frozenset({records["category_id"]})
    assert context.recent_watched_tag_ids == frozenset({latest_tag})
    assert context.resume_content_id == resume
    assert {item.content_id: item.watched for item in context.candidates} == {
        resume: True,
        incomplete: True,
        fresh: False,
    }
    assert all(item.tag_ids == frozenset({records["tag_id"]}) for item in context.candidates)
    items = response.json()["items"]
    assert [item["content"]["content_id"] for item in items] == [fresh, incomplete, resume]
    assert items[0]["recommendation_reason"] == "RELATED_TAG"
    assert items[0]["recommendation_label"] == "추천 담당자가 반환한 라벨"
    assert items[1]["content"]["watch_completed"] is False
    assert items[2]["content"]["liked"] is True
    assert items[2]["content"]["saved"] is True
    assert items[2]["content"]["watch_completed"] is True
    assert response.json()["resume_unavailable"] is False


@pytest.mark.parametrize("condition", ["available", "draft", "missing", "truncated"])
def test_resume_availability_is_based_on_actual_candidates(
    client, database, records, content_factory, condition
):
    content = content_factory(
        status="DRAFT" if condition == "draft" else "PUBLISHED",
        media=condition if condition in {"missing", "truncated"} else "available",
    )
    database.execute(
        text("UPDATE sasu.user_settings SET last_content_id = :content WHERE user_id = :user"),
        {"user": records["learner"], "content": content},
    )
    database.commit()
    response = feed(client, records)
    assert response.status_code == 200, response.text
    assert response.json()["resume_unavailable"] is (condition != "available")


@pytest.mark.parametrize(
    ("actor", "target", "status", "code"),
    [
        ("admin", "learner", 403, "ROLE_NOT_ALLOWED"),
        ("other", "learner", 404, "USER_NOT_FOUND"),
        ("learner", "other", 404, "USER_NOT_FOUND"),
        ("no_state", "no_state", 404, "USER_NOT_FOUND"),
        (None, "learner", 422, "VALIDATION_ERROR"),
        (9223372036854775807, "learner", 404, "USER_NOT_FOUND"),
        ("learner", 0, 422, "VALIDATION_ERROR"),
        ("learner", 9223372036854775808, 422, "VALIDATION_ERROR"),
    ],
)
def test_access_and_id_validation(client, records, actor, target, status, code):
    actor_id = records.get(actor, actor)
    target_id = records.get(target, target)
    headers = {"X-Actor-Id": str(actor_id)} if actor is not None else {}
    response = client.get(f"/api/users/{target_id}/feed", headers=headers)
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def test_query_is_rejected(client, records):
    response = feed(client, records, params={"page": 1})
    assert response.status_code == 422
    assert response.json()["detail"]["fields"][0]["field"] == "query.page"


def test_personal_state_does_not_include_another_learner(
    client, database, records, content_factory
):
    content = content_factory()
    other = {**records, "learner": records["other"]}
    watch(database, other, content, completed=True)
    for table in ("content_likes", "saved_contents"):
        database.execute(
            text(
                f"INSERT INTO sasu.{table} (user_id, learning_epoch, content_id) "
                "VALUES (:user, 1, :content)"
            ),
            {"user": records["other"], "content": content},
        )
    database.commit()

    def rank(context):
        assert context.candidates[0].watched is False
        assert context.recent_watched_tag_ids == frozenset()
        return [RankedFeedItem(content, "LATEST", "연결 확인")]

    client.app.dependency_overrides[get_feed_ranker] = lambda: rank
    response = feed(client, records)
    assert response.status_code == 200, response.text
    summary = response.json()["items"][0]["content"]
    assert summary["liked"] is summary["saved"] is summary["watch_completed"] is False


@pytest.mark.parametrize("mode", ["duplicate", "missing", "foreign"])
def test_invalid_ranker_results_cannot_duplicate_drop_or_inject_content(
    client, records, content_factory, mode
):
    first, second = content_factory(), content_factory()

    def invalid(context):
        ids = {
            "duplicate": [first, first],
            "missing": [first],
            "foreign": [first, second + 10000],
        }[mode]
        return [RankedFeedItem(content_id, "LATEST", "테스트") for content_id in ids]

    client.app.dependency_overrides[get_feed_ranker] = lambda: invalid
    response = feed(client, records)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"


def test_get_does_not_write_learning_state(client, database, records, content_factory):
    content = content_factory()
    watch(database, records, content)
    database.commit()

    def snapshot():
        tables = (
            "user_settings",
            "watch_records",
            "watch_visits",
            "content_likes",
            "saved_contents",
            "learning_events",
        )
        return {
            table: database.execute(
                text(f"SELECT * FROM sasu.{table} WHERE user_id = :user"),
                {"user": records["learner"]},
            ).all()
            for table in tables
        }

    before = snapshot()
    database.commit()
    assert feed(client, records).status_code == 200
    assert feed(client, records).status_code == 200
    assert snapshot() == before
