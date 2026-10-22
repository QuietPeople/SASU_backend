"""REV-01~04의 대상·정렬·버전·개인 상태·읽기 전용 계약 검증."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import main
from app.db.session import get_db
from app.modules.questions.schemas import VersionInput
from app.modules.questions.service import revise_question
from app.modules.reviews import repository

AT = datetime(2026, 10, 20, tzinfo=UTC)


def base(records, target="learner"):
    return f"/api/users/{records[target]}/reviews"


def headers(records, user="learner"):
    return {"X-Actor-Id": str(records[user])}


def get(client, records, suffix, *, params=None):
    response = client.get(base(records) + suffix, headers=headers(records), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def candidate(client, records, *, shown=(), retry=(), status=200):
    response = client.post(
        base(records) + "/feed/candidate",
        headers=headers(records),
        json={"shown_question_version_ids": list(shown), "retry_question_version_ids": list(retry)},
    )
    assert response.status_code == status, response.text
    return response.json()


def snapshot(database):
    return {
        table: database.scalar(
            text(f"SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM sasu.{table} t")
        )
        for table in (
            "user_settings",
            "watch_records",
            "watch_visits",
            "content_likes",
            "saved_contents",
            "quiz_attempts",
            "quiz_responses",
            "wrong_answers",
            "learning_events",
        )
    }


def revise(database, records):
    question = records["questions"][0]
    return revise_question(
        database,
        question["question_id"],
        VersionInput(
            expected_current_version_id=question["question_version_id"],
            question_type="OX",
            question_text="수정한 질문",
            explanation="수정한 해설",
            options=[
                {"option_order": 1, "option_text": "O", "is_correct": False},
                {"option_order": 2, "option_text": "X", "is_correct": True},
            ],
        ),
    )


def test_flashcards_include_all_public_questions_without_watch_and_only_front(
    client, database, records, question_factory
):
    question_factory(with_quiz=False)
    before = snapshot(database)
    page = get(client, records, "/flashcards")
    assert page["total"] == 2 and page["page"] == 1 and page["size"] == 20
    assert page["has_next"] is False
    assert {item["question_version_id"] for item in page["items"]} == {
        records["questions"][i]["question_version_id"] for i in (0, 2)
    }
    for card in page["items"]:
        assert set(card) == {
            "question_id",
            "question_version_id",
            "content_id",
            "content_title",
            "category",
            "front",
        }
        assert card["front"] == "원래 문항" and card["content_title"] == "영상"
    assert snapshot(database) == before


def test_flashcard_pagination_order_and_out_of_range_total(
    client, database, records, question_factory
):
    database.execute(
        text("UPDATE sasu.contents SET published_at = :at WHERE status = 'PUBLISHED'"),
        {"at": AT - timedelta(days=1)},
    )
    database.commit()
    first = question_factory(published_at=AT + timedelta(days=2))
    second = question_factory(published_at=AT + timedelta(days=2))
    third = question_factory(published_at=AT)
    page = get(client, records, "/flashcards", params={"size": 1})
    all_cards = get(client, records, "/flashcards")["items"]
    assert [card["content_id"] for card in all_cards] == [
        first["content_id"],
        second["content_id"],
        third["content_id"],
        records["questions"][0]["content_id"],
        records["questions"][2]["content_id"],
    ]
    assert page["items"] == all_cards[:1] and page["total"] == 5 and page["has_next"]
    next_page = get(client, records, "/flashcards", params={"size": 1, "page": 2})
    assert next_page["items"] == all_cards[1:2] and next_page["total"] == 5
    for page_number in (100, 2**100):
        empty = get(client, records, "/flashcards", params={"page": page_number})
        assert empty["items"] == [] and empty["total"] == 5 and empty["has_next"] is False


def test_card_detail_preserves_requested_version_and_never_resolves_wrong(
    client, database, records, respond
):
    respond()
    question = records["questions"][0]
    old = get(client, records, f"/flashcards/{question['question_version_id']}")
    assert old["back"] == "O" and old["explanation"] == "원래 해설"
    before = snapshot(database)
    assert get(client, records, f"/flashcards/{question['question_version_id']}") == old
    assert snapshot(database) == before
    new = revise(database, records)
    assert get(client, records, f"/flashcards/{question['question_version_id']}") == old
    current = get(client, records, f"/flashcards/{new.question_version_id}")
    assert current["back"] == "X" and current["card"]["front"] == "수정한 질문"
    versions = {
        item["question_version_id"] for item in get(client, records, "/flashcards")["items"]
    }
    assert new.question_version_id in versions and question["question_version_id"] not in versions


@pytest.mark.parametrize("version_kind", ["draft", "missing"])
def test_card_detail_requires_existing_version_and_public_content(client, records, version_kind):
    version = (
        records["questions"][1]["question_version_id"] if version_kind == "draft" else 2**63 - 1
    )
    response = client.get(base(records) + f"/flashcards/{version}", headers=headers(records))
    assert (
        response.status_code == 404 and response.json()["detail"]["code"] == "FLASHCARD_NOT_FOUND"
    )


@pytest.mark.parametrize("suffix", ["/flashcards", "/wrong-answers"])
def test_category_filter_existing_empty_and_missing(
    client, database, records, question_factory, respond, suffix
):
    category = database.scalar(
        text("INSERT INTO sasu.categories (name) VALUES ('별도 분류') RETURNING category_id")
    )
    database.commit()
    assert get(client, records, suffix, params={"category_id": category})["total"] == 0
    question = question_factory(category=category)
    respond(question)
    filtered = get(client, records, suffix, params={"category_id": category})
    assert filtered["total"] == 1
    item = filtered["items"][0]
    assert (item.get("question") or item)["question_version_id"] == question["question_version_id"]
    response = client.get(
        base(records) + suffix, headers=headers(records), params={"category_id": 2**63 - 1}
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "CATEGORY_NOT_FOUND"


def test_wrong_answers_personal_content_counts_and_no_correct_answer_leak(
    client, database, records, respond, watch
):
    respond()
    respond()
    respond(user="other")
    watch()
    watch(user="other")
    content = records["questions"][0]["content_id"]
    for user in ("learner", "other"):
        database.execute(
            text(
                "INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id) "
                "VALUES (:u, 1, :c)"
            ),
            {"u": records[user], "c": content},
        )
    database.execute(
        text(
            "INSERT INTO sasu.saved_contents (user_id, learning_epoch, content_id) "
            "VALUES (:u, 1, :c)"
        ),
        {"u": records["learner"], "c": content},
    )
    database.commit()
    before = snapshot(database)
    page = get(client, records, "/wrong-answers")
    assert page["total"] == 1 and page["items"][0]["wrong_count"] == 2
    item = page["items"][0]
    assert item["status"] == "PENDING" and item["resolved_at"] is None
    assert set(item["question"]) == {
        "question_id",
        "question_version_id",
        "content_id",
        "question_type",
        "question_text",
        "options",
    }
    assert all("is_correct" not in option for option in item["question"]["options"])
    assert [option["option_order"] for option in item["question"]["options"]] == [1, 2]
    summary = item["content"]
    assert summary["liked"] and summary["saved"] and summary["watch_completed"]
    assert summary["view_count"] == 2 and summary["like_count"] == 2
    assert summary["has_quiz"] and summary["status"] == "PUBLISHED" and len(summary["tags"]) == 1
    url = urlsplit(summary["video_url"])
    assert url.path == f"/api/contents/{content}/video"
    assert parse_qs(url.query) == {"revision": [summary["media_revision"]]}
    assert "storage_path" not in str(summary)
    assert snapshot(database) == before


def test_wrong_status_filter_and_old_versions_preserved(client, database, records, respond):
    respond()
    respond(result="CORRECT")
    assert get(client, records, "/wrong-answers")["total"] == 0
    resolved = get(client, records, "/wrong-answers", params={"status": "RESOLVED"})
    assert resolved["total"] == 1 and resolved["items"][0]["status"] == "RESOLVED"
    assert resolved["items"][0]["resolved_at"] is not None
    new = revise(database, records)
    assert get(client, records, "/wrong-answers", params={"status": "RESOLVED"})["total"] == 0
    assert database.scalar(text("SELECT count(*) FROM sasu.wrong_answers")) == 1
    respond(new.model_dump())
    pending = get(client, records, "/wrong-answers")
    assert (
        pending["total"] == 1
        and pending["items"][0]["question"]["question_version_id"] == new.question_version_id
    )
    assert database.scalar(text("SELECT count(*) FROM sasu.wrong_answers")) == 2


def test_wrong_list_public_current_order_pagination_and_default_false_state(
    client, records, respond, question_factory
):
    first = question_factory()
    second = question_factory()
    respond(first, at=AT + timedelta(hours=1))
    respond(second, at=AT + timedelta(hours=1))
    respond(at=AT)
    respond(records["questions"][1], at=AT + timedelta(days=10))  # 비공개 제외
    respond(user="other", at=AT + timedelta(days=20))
    page = get(client, records, "/wrong-answers", params={"size": 1})
    assert page["total"] == 3 and page["has_next"]
    assert page["items"][0]["question"]["question_version_id"] == first["question_version_id"]
    summary = page["items"][0]["content"]
    assert summary["liked"] is summary["saved"] is summary["watch_completed"] is False
    second_page = get(client, records, "/wrong-answers", params={"size": 1, "page": 2})
    assert (
        second_page["items"][0]["question"]["question_version_id"] == second["question_version_id"]
    )
    empty = get(client, records, "/wrong-answers", params={"page": 99})
    assert empty["items"] == [] and empty["total"] == 3 and not empty["has_next"]


def test_empty_candidate_and_completion_public_quiz_media_conditions(
    client, database, records, watch, question_factory
):
    assert candidate(client, records) == {"candidate": None, "record_generation": 0}
    watch(completed=False)
    watch(records["questions"][1])  # 비공개
    watch(records["questions"][2])  # 영상 파일 없음
    no_quiz = question_factory(with_quiz=False)
    watch(no_quiz)
    assert candidate(client, records)["candidate"] is None
    database.execute(
        text(
            "UPDATE sasu.watch_records SET completed_at = now(), max_coverage_ratio = 0.9 "
            "WHERE user_id = :u AND content_id = :c"
        ),
        {"u": records["learner"], "c": records["questions"][0]["content_id"]},
    )
    database.commit()
    before = snapshot(database)
    selected = candidate(client, records)
    assert (
        selected["candidate"]["question_version_id"]
        == records["questions"][0]["question_version_id"]
    )
    assert "explanation" not in selected["candidate"]
    assert all("is_correct" not in option for option in selected["candidate"]["options"])
    assert candidate(client, records) == selected
    assert snapshot(database) == before


def test_candidate_priority_unresolved_then_oldest_watch_then_content_id(
    client, records, question_factory, watch, respond
):
    oldest = question_factory()
    tied = question_factory()
    pending = question_factory()
    watch(oldest, at=AT)
    watch(tied, at=AT)
    watch(pending, at=AT + timedelta(days=1))
    respond(pending)
    assert candidate(client, records)["candidate"]["content_id"] == pending["content_id"]
    shown = [pending["question_version_id"]]
    assert (
        candidate(client, records, shown=shown)["candidate"]["content_id"] == oldest["content_id"]
    )
    shown.append(oldest["question_version_id"])
    assert candidate(client, records, shown=shown)["candidate"]["content_id"] == tied["content_id"]
    respond(pending, result="CORRECT")
    assert candidate(client, records)["candidate"]["content_id"] == oldest["content_id"]


def test_shown_retry_deduplicated_and_requires_feed_wrong_history(client, records, watch, respond):
    watch()
    version = records["questions"][0]["question_version_id"]
    assert candidate(client, records, shown=[version, version])["candidate"] is None
    respond(context="FEED_REVIEW")
    assert candidate(client, records, shown=[version])["candidate"] is None
    restored = candidate(client, records, shown=[version, version], retry=[version, version])
    assert restored["candidate"]["question_version_id"] == version
    respond(context="FEED_REVIEW", result="CORRECT")
    # 재출제는 과거 FEED_REVIEW 오답 이력 조건이다. 현재 미해결 상태만 요구하지 않는다.
    assert candidate(client, records, shown=[version], retry=[version])["candidate"] is not None


@pytest.mark.parametrize(
    "history", ["none", "foreign_user", "video", "wrong_note", "correct", "skip"]
)
def test_retry_rejects_nonmatching_history(client, records, respond, history):
    if history != "none":
        respond(
            user="other" if history == "foreign_user" else "learner",
            context={"video": "VIDEO_END", "wrong_note": "WRONG_REVIEW"}.get(
                history, "FEED_REVIEW"
            ),
            result={"correct": "CORRECT", "skip": "SKIPPED"}.get(history, "WRONG"),
        )
    version = records["questions"][0]["question_version_id"]
    response = candidate(client, records, shown=[version], retry=[version], status=422)
    assert response["detail"]["code"] == "INVALID_REVIEW_FILTER"


def test_retry_must_be_subset_and_complete_history_set(client, records, respond):
    respond(context="FEED_REVIEW")
    version = records["questions"][0]["question_version_id"]
    response = candidate(client, records, retry=[version], status=422)
    assert response["detail"]["code"] == "INVALID_REVIEW_FILTER"
    response = candidate(
        client, records, shown=[version, 2**63 - 1], retry=[version, 2**63 - 1], status=422
    )
    assert response["detail"]["code"] == "INVALID_REVIEW_FILTER"


def test_revision_does_not_inherit_exposure_wrong_priority_or_retry_version(
    client, database, records, watch, respond
):
    watch()
    respond(context="FEED_REVIEW")
    old = records["questions"][0]["question_version_id"]
    new = revise(database, records)
    selected = candidate(client, records, shown=[old], retry=[old])
    assert selected["candidate"]["question_version_id"] == new.question_version_id
    assert candidate(client, records, shown=[new.question_version_id])["candidate"] is None
    invalid = candidate(
        client,
        records,
        shown=[new.question_version_id],
        retry=[new.question_version_id],
        status=422,
    )
    assert invalid["detail"]["code"] == "INVALID_REVIEW_FILTER"


def test_reset_clears_wrong_and_candidate_but_keeps_public_cards(
    client, database, records, watch, respond
):
    watch()
    respond(context="FEED_REVIEW")
    assert candidate(client, records)["candidate"] is not None
    before_cards = get(client, records, "/flashcards")
    database.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]})
    database.commit()
    assert candidate(client, records) == {"candidate": None, "record_generation": 1}
    assert get(client, records, "/wrong-answers")["total"] == 0
    assert get(client, records, "/flashcards") == before_cards
    version = records["questions"][0]["question_version_id"]
    assert (
        candidate(client, records, shown=[version], retry=[version], status=422)["detail"]["code"]
        == "INVALID_REVIEW_FILTER"
    )


@pytest.mark.parametrize(
    "suffix", ["/wrong-answers", "/flashcards", "/flashcards/1", "/feed/candidate"]
)
@pytest.mark.parametrize(
    "actor,target,status",
    [("admin", "learner", 403), ("other", "learner", 404), ("no_state", "no_state", 404)],
)
def test_learner_ownership_and_state(client, records, suffix, actor, target, status):
    kwargs = {"headers": headers(records, actor)}
    if suffix == "/feed/candidate":
        kwargs["json"] = {"shown_question_version_ids": [], "retry_question_version_ids": []}
    response = client.request(
        "POST" if "candidate" in suffix else "GET", base(records, target) + suffix, **kwargs
    )
    assert response.status_code == status


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"size": 0},
        {"size": 101},
        {"category_id": -1},
        {"category_id": 2**63},
        {"extra": 1},
        {"status": "OTHER"},
    ],
)
def test_wrong_list_rejects_invalid_query(client, records, params):
    response = client.get(base(records) + "/wrong-answers", headers=headers(records), params=params)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"shown_question_version_ids": []},
        {"shown_question_version_ids": [], "retry_question_version_ids": [], "extra": True},
        {"shown_question_version_ids": [True], "retry_question_version_ids": []},
        {"shown_question_version_ids": ["1"], "retry_question_version_ids": []},
        {"shown_question_version_ids": [0], "retry_question_version_ids": []},
        {"shown_question_version_ids": [2**63], "retry_question_version_ids": []},
        {"shown_question_version_ids": None, "retry_question_version_ids": []},
        {"shown_question_version_ids": [1] * 1001, "retry_question_version_ids": []},
        {"shown_question_version_ids": [], "retry_question_version_ids": [1] * 1001},
    ],
)
def test_candidate_body_validation(client, records, payload):
    response = client.post(
        base(records) + "/feed/candidate", headers=headers(records), json=payload
    )
    assert response.status_code == 422 and response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_candidate_filter_accepts_1000_ids(client, records):
    assert candidate(client, records, shown=range(1, 1001))["candidate"] is None


def test_query_headers_bad_json_and_id_validation(client, records):
    assert client.get(base(records) + "/flashcards").status_code == 422
    assert (
        client.get(
            base(records) + "/flashcards", headers=headers(records), params={"status": "PENDING"}
        ).status_code
        == 422
    )
    for version in ("bad", "0", str(2**63)):
        assert (
            client.get(
                base(records) + f"/flashcards/{version}", headers=headers(records)
            ).status_code
            == 422
        )
    question = records["questions"][0]
    assert (
        client.get(
            base(records) + f"/flashcards/{question['question_version_id']}?extra=1",
            headers=headers(records),
        ).status_code
        == 422
    )
    bad = client.post(
        base(records) + "/feed/candidate",
        headers={**headers(records), "Content-Type": "application/json"},
        content="{",
    )
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "INVALID_REQUEST"
    assert (
        client.post(
            base(records) + "/feed/candidate?extra=1",
            headers=headers(records),
            json={"shown_question_version_ids": [], "retry_question_version_ids": []},
        ).status_code
        == 422
    )
    assert candidate(client, records, shown=[2**63 - 1])["candidate"] is None


def test_database_failure_is_sanitized_error_not_empty_success(client, records, monkeypatch):
    def fail(*args):
        raise OperationalError("private SQL", {}, Exception("secret password"))

    monkeypatch.setattr(repository, "list_flashcards", fail)
    response = client.get(base(records) + "/flashcards", headers=headers(records))
    assert response.status_code == 500 and response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "private" not in response.text and "secret" not in response.text


def test_real_app_review_to_attempt_display_submit_and_wrong_list(
    database, records, watch, monkeypatch
):
    watch()
    monkeypatch.setattr(main, "check_database_connection", lambda: None)
    monkeypatch.setattr(main, "close_database", lambda: None)

    def provide_session():
        with Session(bind=database.get_bind(), join_transaction_mode="create_savepoint") as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    with TestClient(main.app, raise_server_exceptions=False) as http:
        assert http.get("/docs").status_code == 200
        paths = http.get("/openapi.json").json()["paths"]
        prefix = "/api/users/{user_id}/reviews"
        for suffix, method, api_id in (
            ("/feed/candidate", "post", "01"),
            ("/wrong-answers", "get", "02"),
            ("/flashcards", "get", "03"),
            ("/flashcards/{question_version_id}", "get", "04"),
        ):
            assert paths[prefix + suffix][method]["operationId"] == f"API-REV-{api_id}"
        routes = [
            (route.path, method)
            for route in main.app.routes
            for method in getattr(route, "methods", ())
        ]
        assert len(routes) == len(set(routes))
        selected = candidate(http, records)["candidate"]
        attempt_id = str(uuid4())
        attempts_url = f"/api/users/{records['learner']}/question-attempts"
        created = http.post(
            attempts_url,
            headers={**headers(records), "X-Record-Generation": "0"},
            json={
                "attempt_id": attempt_id,
                "question_id": selected["question_id"],
                "expected_question_version_id": selected["question_version_id"],
                "response_path": "FEED_REVIEW",
            },
        )
        assert created.status_code == 201, created.text
        database.execute(
            text("""INSERT INTO sasu.learning_events
                (event_id, user_id, learning_epoch, event_type,
                 content_id, quiz_version_id, attempt_id)
                VALUES (:id, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""),
            {
                "id": uuid4(),
                "user": records["learner"],
                "content": selected["content_id"],
                "version": selected["question_version_id"],
                "attempt": attempt_id,
            },
        )
        database.commit()
        submitted = http.put(
            attempts_url + f"/{attempt_id}/response",
            headers={**headers(records), "X-Record-Generation": "0"},
            json={"action": "ANSWER", "selected_option_id": selected["options"][1]["option_id"]},
        )
        assert submitted.status_code == 200 and submitted.json()["result"] == "WRONG"
        wrong = get(http, records, "/wrong-answers")
        assert wrong["items"][0]["question"] == selected
        assert wrong["items"][0]["wrong_count"] == 1
        before = snapshot(database)
        assert get(http, records, f"/flashcards/{selected['question_version_id']}")["back"] == "O"
        assert (
            candidate(
                http,
                records,
                shown=[selected["question_version_id"]],
                retry=[selected["question_version_id"]],
            )["candidate"]
            == selected
        )
        assert snapshot(database) == before
