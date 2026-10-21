"""ATM-01·02의 버전 고정·소유권·세대·중복 요청·조회 부작용 검증."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app import main
from app.db.session import get_db
from app.modules.attempts import repository
from app.modules.questions import repository as questions_repository
from app.modules.questions.schemas import QuestionInput


def path(records, user="learner"):
    return f"/api/users/{records[user]}/question-attempts"


def headers(records, user="learner", generation=0):
    return {"X-Actor-Id": str(records[user]), "X-Record-Generation": str(generation)}


def body(records, context="VIDEO_QUIZ", index=0):
    question = records["questions"][index]
    return {
        "attempt_id": str(uuid4()),
        "question_id": question["question_id"],
        "expected_question_version_id": question["question_version_id"],
        "response_path": context,
    }


def start(client, records, request=None, status=201):
    request = request or body(records)
    response = client.post(path(records), headers=headers(records), json=request)
    assert response.status_code == status, response.text
    return response.json()


def snapshot(database):
    return {
        table: database.scalar(text(f"SELECT jsonb_agg(to_jsonb(t)) FROM sasu.{table} t"))
        for table in (
            "quiz_attempts",
            "quiz_responses",
            "wrong_answers",
            "learning_events",
            "user_settings",
        )
    }


def answer(database, records, request, *, correct=False, user="learner"):
    attempt_id = uuid4()
    question = records["questions"][0]
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
                (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                VALUES (:id, :user, 1, :question, :version, 'WRONG_REVIEW')"""),
        {
            "id": attempt_id,
            "user": records[user],
            "question": question["question_id"],
            "version": request["expected_question_version_id"],
        },
    )
    response_id = database.scalar(
        text("""INSERT INTO sasu.quiz_responses
                (attempt_id, quiz_version_id, selected_option_id, result)
                VALUES (:id, :version, :option, :result) RETURNING response_id"""),
        {
            "id": attempt_id,
            "version": request["expected_question_version_id"],
            "option": question["options"][0 if correct else 1]["option_id"],
            "result": "CORRECT" if correct else "WRONG",
        },
    )
    database.commit()
    return response_id


def revise(database, records):
    question = records["questions"][0]
    request = QuestionInput(
        question_type="OX",
        question_text="새 문항",
        explanation="새 해설",
        options=[
            {"option_order": 1, "option_text": "O", "is_correct": False},
            {"option_order": 2, "option_text": "X", "is_correct": True},
        ],
    )
    version = questions_repository.create_version(database, question["question_id"], 2, request)
    questions_repository.create_options(database, version, request.options)
    questions_repository.set_current_version(database, question["question_id"], version)
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    database.commit()
    return version


def test_create_retry_and_recover_keep_version_and_no_answers_or_events(client, database, records):
    request = body(records)
    created = start(client, records, request)
    assert created["attempt_id"] == request["attempt_id"]
    assert created["record_generation"] == 0 and created["submitted"] is False
    assert created["response"] is None and created["response_path"] == "VIDEO_QUIZ"
    assert created["question"]["question_version_id"] == request["expected_question_version_id"]
    assert "explanation" not in created["question"]
    assert all("is_correct" not in option for option in created["question"]["options"])
    before = snapshot(database)
    assert start(client, records, request, status=200) == created
    recovery = client.get(
        path(records) + f"/{request['attempt_id']}", headers={"X-Actor-Id": str(records["learner"])}
    )
    assert recovery.status_code == 200 and recovery.json() == created
    assert snapshot(database) == before
    assert before["quiz_responses"] is None and before["learning_events"] is None


def test_retry_after_revision_and_unavailability_preserves_original(client, database, records):
    request = body(records)
    original = start(client, records, request)
    revise(database, records)
    database.execute(
        text("UPDATE sasu.contents SET status = 'DRAFT' WHERE content_id = :id"),
        {"id": original["question"]["content_id"]},
    )
    database.commit()
    assert start(client, records, request, status=200) == original
    response = client.get(path(records) + f"/{request['attempt_id']}", headers=headers(records))
    assert response.status_code == 200 and response.json() == original


def test_new_attempt_rejects_stale_version_without_writes(client, database, records):
    request = body(records)
    version = revise(database, records)
    before = snapshot(database)
    rejected = client.post(path(records), headers=headers(records), json=request)
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "VERSION_CONFLICT"
    assert snapshot(database) == before
    request["expected_question_version_id"] = version
    created = start(client, records, request)
    assert created["question"]["question_text"] == "새 문항"


@pytest.mark.parametrize("changed", ["question", "version", "context", "owner"])
def test_same_uuid_different_input_is_conflict(client, database, records, changed):
    request = body(records)
    original = start(client, records, request)
    altered = deepcopy(request)
    target = "learner"
    if changed == "question":
        altered["question_id"] = records["questions"][1]["question_id"]
    elif changed == "version":
        altered["expected_question_version_id"] += 1
    elif changed == "context":
        altered["response_path"] = "FEED_REVIEW"
    else:
        target = "other"
    response = client.post(path(records, target), headers=headers(records, target), json=altered)
    assert (
        response.status_code == 409 and response.json()["detail"]["code"] == "ATTEMPT_ID_CONFLICT"
    )
    assert start(client, records, request, status=200) == original
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 1


@pytest.mark.parametrize("index", [1, 2])
def test_new_attempt_requires_public_playable_question(client, database, records, index):
    response = client.post(path(records), headers=headers(records), json=body(records, index=index))
    assert response.status_code == 404 and response.json()["detail"]["code"] == "QUESTION_NOT_FOUND"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 0


def test_feed_review_needs_completion(client, database, records):
    request = body(records, "FEED_REVIEW")
    rejected = client.post(path(records), headers=headers(records), json=request)
    assert (
        rejected.status_code == 409 and rejected.json()["detail"]["code"] == "ATTEMPT_NOT_ELIGIBLE"
    )
    database.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id,
                 first_played_at, last_watched_at, completed_at)
                VALUES (:user, 1, :content, now(), now(), now())"""),
        {"user": records["learner"], "content": records["questions"][0]["content_id"]},
    )
    database.commit()
    assert start(client, records, request)["response_path"] == "FEED_REVIEW"


def test_wrong_note_needs_current_own_unresolved_wrong(client, database, records):
    request = body(records, "WRONG_NOTE")
    answer(database, records, request, user="other")
    rejected = client.post(path(records), headers=headers(records), json=request)
    assert (
        rejected.status_code == 409 and rejected.json()["detail"]["code"] == "ATTEMPT_NOT_ELIGIBLE"
    )
    answer(database, records, request)
    before = snapshot(database)
    assert start(client, records, request)["response_path"] == "WRONG_NOTE"
    assert snapshot(database)["wrong_answers"] == before["wrong_answers"]
    answer(database, records, request, correct=True)
    request["attempt_id"] = str(uuid4())
    assert client.post(path(records), headers=headers(records), json=request).status_code == 409


def test_new_version_does_not_inherit_old_wrong_note_eligibility(client, database, records):
    request = body(records, "WRONG_NOTE")
    answer(database, records, request)
    request["expected_question_version_id"] = revise(database, records)
    response = client.post(path(records), headers=headers(records), json=request)
    assert (
        response.status_code == 409 and response.json()["detail"]["code"] == "ATTEMPT_NOT_ELIGIBLE"
    )


@pytest.mark.parametrize("result", ["CORRECT", "WRONG", "SKIPPED"])
def test_restore_submitted_response_uses_fixed_result_and_current_wrong_state(
    client, database, records, result
):
    request = body(records)
    created = start(client, records, request)
    question = records["questions"][0]
    database.execute(
        text("""INSERT INTO sasu.quiz_responses
                (attempt_id, quiz_version_id, selected_option_id, result)
                VALUES (:id, :version, :option, :result)"""),
        {
            "id": request["attempt_id"],
            "version": request["expected_question_version_id"],
            "option": None
            if result == "SKIPPED"
            else question["options"][0 if result == "CORRECT" else 1]["option_id"],
            "result": result,
        },
    )
    database.commit()
    revise(database, records)
    before = snapshot(database)
    restored = client.get(path(records) + f"/{request['attempt_id']}", headers=headers(records))
    assert restored.status_code == 200, restored.text
    recovered = restored.json()
    assert recovered["submitted"] is True and recovered["question"] == created["question"]
    detail = recovered["response"]
    assert detail["result"] == ("SKIP" if result == "SKIPPED" else result)
    assert detail["correct_answer"] == "O" and detail["explanation"] == "원래 해설"
    assert start(client, records, request, status=200) == recovered
    assert snapshot(database) == before


def test_reset_rejects_old_generation_and_hides_old_attempt(client, database, records):
    request = body(records)
    start(client, records, request)
    database.scalar(text("SELECT sasu.reset_learning(:id, 1)"), {"id": records["learner"]})
    database.commit()
    response = client.post(path(records), headers=headers(records), json=request)
    assert (
        response.status_code == 409
        and response.json()["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    )
    recovered = client.get(path(records) + f"/{request['attempt_id']}", headers=headers(records))
    assert (
        recovered.status_code == 404 and recovered.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"
    )
    response = client.post(
        path(records), headers=headers(records, generation=1), json=body(records)
    )
    assert response.status_code == 201 and response.json()["record_generation"] == 1


@pytest.mark.parametrize("method", ["POST", "GET"])
@pytest.mark.parametrize(
    "actor,target,status",
    [("admin", "learner", 403), ("learner", "other", 404), ("no_state", "no_state", 404)],
)
def test_learner_ownership_and_state(client, records, method, actor, target, status):
    url = path(records, target)
    if method == "GET":
        url += f"/{uuid4()}"
    response = client.request(
        method,
        url,
        headers=headers(records, actor),
        **({"json": body(records)} if method == "POST" else {}),
    )
    assert response.status_code == status


def test_absent_or_foreign_attempt_cannot_be_recovered(client, records):
    request = body(records)
    start(client, records, request)
    for attempt in (request["attempt_id"], str(uuid4())):
        response = client.get(
            path(records, "other") + f"/{attempt}", headers=headers(records, "other")
        )
        assert (
            response.status_code == 404 and response.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("attempt_id", "bad"),
        ("question_id", True),
        ("question_id", "1"),
        ("question_id", 0),
        ("question_id", 2**63),
        ("expected_question_version_id", -1),
        ("response_path", "OTHER"),
        ("extra", "unknown"),
    ],
)
def test_request_validation_before_writes(client, database, records, field, value):
    request = body(records)
    request[field] = value
    response = client.post(path(records), headers=headers(records), json=request)
    assert response.status_code == 422
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 0


@pytest.mark.parametrize("generation", [None, "-1", "abc", str(2**31 - 1)])
def test_generation_header_validation(client, records, generation):
    actor_headers = {"X-Actor-Id": str(records["learner"])}
    if generation is not None:
        actor_headers["X-Record-Generation"] = generation
    assert client.post(path(records), headers=actor_headers, json=body(records)).status_code == 422


def test_unknown_query_and_malformed_json(client, records):
    assert (
        client.post(
            path(records) + "?extra=1", headers=headers(records), json=body(records)
        ).status_code
        == 422
    )
    assert (
        client.get(path(records) + f"/{uuid4()}?extra=1", headers=headers(records)).status_code
        == 422
    )
    response = client.post(
        path(records), content="{", headers={**headers(records), "Content-Type": "application/json"}
    )
    assert response.status_code == 400 and response.json()["detail"]["code"] == "INVALID_REQUEST"


def test_insert_failure_rolls_back(client, database, records, monkeypatch):
    original = repository.insert_attempt

    def fail(*args):
        original(*args)
        raise OperationalError("private SQL", {}, Exception("secret password"))

    monkeypatch.setattr(repository, "insert_attempt", fail)
    response = client.post(path(records), headers=headers(records), json=body(records))
    assert response.status_code == 500 and response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text and "private" not in response.text
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 0


def test_commit_failure_rolls_back_and_allows_retry(client, database, records):
    request = body(records)

    def fail_commit(session):
        raise OperationalError("private SQL", {}, Exception("secret password"))

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = client.post(path(records), headers=headers(records), json=request)
    finally:
        event.remove(Session, "before_commit", fail_commit)

    assert response.status_code == 500 and response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text and "private" not in response.text
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 0
    assert start(client, records, request)["attempt_id"] == request["attempt_id"]


def test_real_app_startup_docs_and_attempt_endpoints(database, records, monkeypatch):
    calls = []
    monkeypatch.setattr(main, "check_database_connection", lambda: calls.append("checked"))
    monkeypatch.setattr(main, "close_database", lambda: calls.append("closed"))

    def provide_session():
        with Session(bind=database.get_bind(), join_transaction_mode="create_savepoint") as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    request = body(records)
    with TestClient(main.app, raise_server_exceptions=False) as http:
        assert calls == ["checked"]
        assert http.get("/docs").status_code == 200
        response = http.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        base = "/api/users/{user_id}/question-attempts"
        assert paths[base]["post"]["operationId"] == "API-ATM-01"
        assert paths[base + "/{attempt_id}"]["get"]["operationId"] == "API-ATM-02"
        assert paths[base + "/{attempt_id}/response"]["put"]["operationId"] == "API-ATM-03"
        routes = [
            (route.path, method)
            for route in main.app.routes
            for method in getattr(route, "methods", ())
        ]
        assert len(routes) == len(set(routes))
        operation_ids = [
            operation["operationId"]
            for methods in paths.values()
            for operation in methods.values()
            if isinstance(operation, dict) and "operationId" in operation
        ]
        assert len(operation_ids) == len(set(operation_ids))
        created = start(http, records, request)
        assert start(http, records, request, status=200) == created
        recovered = http.get(path(records) + f"/{request['attempt_id']}", headers=headers(records))
        assert recovered.status_code == 200 and recovered.json() == created
        database.execute(
            text("""INSERT INTO sasu.learning_events
                    (event_id, user_id, learning_epoch, event_type,
                     content_id, quiz_version_id, attempt_id)
                    VALUES (:event, :user, 1, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""),
            {
                "event": uuid4(),
                "user": records["learner"],
                "content": created["question"]["content_id"],
                "version": created["question"]["question_version_id"],
                "attempt": request["attempt_id"],
            },
        )
        database.commit()
        submitted = http.put(
            path(records) + f"/{request['attempt_id']}/response",
            headers=headers(records),
            json={"action": "SKIP"},
        )
        assert submitted.status_code == 200 and submitted.json()["result"] == "SKIP"
        detail = http.get(
            f"/api/responses/{submitted.json()['response_id']}", headers=headers(records)
        )
        assert detail.status_code == 200 and detail.json() == submitted.json()
        restored = http.get(path(records) + f"/{request['attempt_id']}", headers=headers(records))
        assert restored.status_code == 200 and restored.json()["response"] == submitted.json()
    assert calls == ["checked", "closed"]
