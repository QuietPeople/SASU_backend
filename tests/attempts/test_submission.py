"""ATM-03의 고정 버전 채점·노출·멱등성·오답 트리거·롤백 계약."""

from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.attempts import repository
from app.modules.questions.schemas import VersionInput
from app.modules.questions.service import revise_question


def headers(records, user="learner", generation=0):
    return {"X-Actor-Id": str(records[user]), "X-Record-Generation": str(generation)}


def base(records, user="learner"):
    return f"/api/users/{records[user]}/question-attempts"


def create(client, records, *, context="VIDEO_QUIZ", question=None):
    question = question or records["questions"][0]
    response = client.post(
        base(records),
        headers=headers(records),
        json={
            "attempt_id": str(uuid4()),
            "question_id": question["question_id"],
            "expected_question_version_id": question["question_version_id"],
            "response_path": context,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def display(database, attempt):
    database.execute(
        text("""INSERT INTO sasu.learning_events
                (event_id, user_id, learning_epoch, event_type,
                 content_id, quiz_version_id, attempt_id)
                VALUES (:event, :user, :epoch, 'QUIZ_DISPLAYED', :content, :version, :attempt)"""),
        {
            "event": uuid4(),
            "user": attempt["user_id"],
            "epoch": attempt["record_generation"] + 1,
            "content": attempt["question"]["content_id"],
            "version": attempt["question"]["question_version_id"],
            "attempt": attempt["attempt_id"],
        },
    )
    database.commit()


def answer(attempt, *, correct=True):
    return {
        "action": "ANSWER",
        "selected_option_id": attempt["question"]["options"][0 if correct else 1]["option_id"],
    }


def submit(client, records, attempt, request, *, status=200):
    response = client.put(
        base(records) + f"/{attempt['attempt_id']}/response",
        headers=headers(records),
        json=request,
    )
    assert response.status_code == status, response.text
    return response.json()


def wrong_state(database, records, version=None):
    return (
        database.execute(
            text("SELECT * FROM sasu.wrong_answers WHERE user_id = :user AND quiz_version_id = :v"),
            {
                "user": records["learner"],
                "v": version or records["questions"][0]["question_version_id"],
            },
        )
        .mappings()
        .one_or_none()
    )


def completed_watch(database, records):
    database.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id,
                 first_played_at, last_watched_at, completed_at)
                VALUES (:user, 1, :content, now(), now(), now())"""),
        {"user": records["learner"], "content": records["questions"][0]["content_id"]},
    )
    database.commit()


def answered(client, database, records, *, correct=True):
    attempt = create(client, records)
    display(database, attempt)
    return attempt, submit(client, records, attempt, answer(attempt, correct=correct))


@pytest.mark.parametrize("result", ["CORRECT", "WRONG", "SKIP"])
def test_grade_skip_retry_and_attempt_recovery(client, database, records, result):
    attempt = create(client, records)
    display(database, attempt)
    request = (
        {"action": "SKIP"} if result == "SKIP" else answer(attempt, correct=result == "CORRECT")
    )
    response = submit(client, records, attempt, request)
    assert response["result"] == result
    assert response["attempt_id"] == attempt["attempt_id"]
    assert response["question"] == attempt["question"]
    assert response["correct_answer"] == "O" and response["explanation"] == "원래 해설"
    assert response["selected_option_id"] == request.get("selected_option_id")
    assert submit(client, records, attempt, request) == response
    recovered = client.get(base(records) + f"/{attempt['attempt_id']}", headers=headers(records))
    assert recovered.status_code == 200 and recovered.json()["response"] == response
    assert recovered.json()["submitted"] is True
    stored = database.execute(
        text("SELECT result, selected_option_id FROM sasu.quiz_responses")
    ).one()
    assert stored.result == ("SKIPPED" if result == "SKIP" else result)
    assert stored.selected_option_id == request.get("selected_option_id")
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 1
    assert database.scalar(text("SELECT count(*) FROM sasu.learning_events")) == 1
    wrong = wrong_state(database, records)
    assert (wrong is not None) is (result == "WRONG")
    if wrong:
        assert wrong["wrong_count"] == 1 and wrong["status"] == "UNRESOLVED"


def test_wrong_trigger_repeated_wrong_resolve_and_reopen(client, database, records):
    first, initial = answered(client, database, records, correct=False)
    answered(client, database, records, correct=False)
    assert wrong_state(database, records)["wrong_count"] == 2
    _, correct = answered(client, database, records)
    resolved = wrong_state(database, records)
    assert resolved["status"] == "RESOLVED" and resolved["wrong_count"] == 2
    assert resolved["resolved_response_id"] == correct["response_id"]
    assert resolved["resolved_at"] is not None
    retry = submit(client, records, first, answer(first, correct=False))
    assert retry["response_id"] == initial["response_id"]
    assert retry["result"] == "WRONG" and retry["submitted_at"] == initial["submitted_at"]
    assert retry["wrong_state"]["status"] == "RESOLVED"
    assert dict(wrong_state(database, records)) == dict(resolved)
    answered(client, database, records, correct=False)
    reopened = wrong_state(database, records)
    assert reopened["status"] == "UNRESOLVED" and reopened["wrong_count"] == 3
    assert reopened["resolved_at"] is None and reopened["resolved_response_id"] is None


@pytest.mark.parametrize("resolved", [False, True])
def test_skip_never_adds_or_resolves_existing_wrong(client, database, records, resolved):
    answered(client, database, records, correct=False)
    if resolved:
        answered(client, database, records)
    before = dict(wrong_state(database, records))
    attempt = create(client, records)
    display(database, attempt)
    response = submit(client, records, attempt, {"action": "SKIP", "selected_option_id": None})
    assert response["result"] == "SKIP"
    assert dict(wrong_state(database, records)) == before


def test_skip_excluded_from_first_valid_video_answer(client, database, records):
    attempt = create(client, records)
    display(database, attempt)
    submit(client, records, attempt, {"action": "SKIP"})
    assert database.scalar(text("SELECT count(*) FROM sasu.first_video_responses")) == 0
    _, response = answered(client, database, records, correct=False)
    assert (
        database.scalar(text("SELECT response_id FROM sasu.first_video_responses"))
        == response["response_id"]
    )


@pytest.mark.parametrize("context", ["VIDEO_QUIZ", "FEED_REVIEW"])
@pytest.mark.parametrize("action", ["ANSWER", "SKIP"])
def test_first_submission_waits_for_own_attempt_display(client, database, records, context, action):
    if context == "FEED_REVIEW":
        completed_watch(database, records)
    other = create(client, records, context=context)
    display(database, other)
    attempt = create(client, records, context=context)
    request = answer(attempt) if action == "ANSWER" else {"action": "SKIP"}
    response = submit(client, records, attempt, request, status=409)
    assert response["detail"]["code"] == "DISPLAY_NOT_RECORDED"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0
    assert wrong_state(database, records) is None
    display(database, attempt)
    assert submit(client, records, attempt, request)["response_path"] == context


@pytest.mark.parametrize("action", ["ANSWER", "SKIP"])
def test_wrong_note_submission_needs_no_separate_display(client, database, records, action):
    answered(client, database, records, correct=False)
    attempt = create(client, records, context="WRONG_NOTE")
    request = answer(attempt) if action == "ANSWER" else {"action": "SKIP"}
    response = submit(client, records, attempt, request)
    assert response["response_path"] == "WRONG_NOTE"
    assert response["result"] == ("CORRECT" if action == "ANSWER" else "SKIP")
    assert database.scalar(text("SELECT count(*) FROM sasu.learning_events")) == 1


def test_old_version_grading_never_resolves_new_version_wrong(client, database, records):
    answered(client, database, records, correct=False)
    original = create(client, records)
    display(database, original)
    question = records["questions"][0]
    new = revise_question(
        database,
        question["question_id"],
        VersionInput(
            expected_current_version_id=question["question_version_id"],
            question_type="OX",
            question_text="수정된 문제",
            explanation="수정된 해설",
            options=[
                {"option_order": 1, "option_text": "O", "is_correct": False},
                {"option_order": 2, "option_text": "X", "is_correct": True},
            ],
        ),
    )
    current = create(client, records, question=new.model_dump())
    display(database, current)
    submit(client, records, current, answer(current))  # 새 버전에서는 O가 오답이다.
    new_wrong = dict(wrong_state(database, records, new.question_version_id))
    result = submit(client, records, original, answer(original))
    assert result["result"] == "CORRECT" and result["correct_answer"] == "O"
    assert result["explanation"] == "원래 해설" and result["question"] == original["question"]
    assert wrong_state(database, records)["status"] == "RESOLVED"
    assert dict(wrong_state(database, records, new.question_version_id)) == new_wrong


@pytest.mark.parametrize("kind,count", [("MCQ_3", 3), ("MCQ_4", 4)])
def test_multiple_choice_grades_stored_correct_option(client, database, records, kind, count):
    question = records["questions"][0]
    version = revise_question(
        database,
        question["question_id"],
        VersionInput(
            expected_current_version_id=question["question_version_id"],
            question_type=kind,
            question_text="올바른 보기는?",
            explanation="마지막 보기가 정답입니다.",
            options=[
                {
                    "option_order": position,
                    "option_text": f"보기 {position}",
                    "is_correct": position == count,
                }
                for position in range(1, count + 1)
            ],
        ),
    )
    for correct in (False, True):
        attempt = create(client, records, question=version.model_dump())
        display(database, attempt)
        response = submit(
            client,
            records,
            attempt,
            {
                "action": "ANSWER",
                "selected_option_id": version.options[-1 if correct else 0].option_id,
            },
        )
        assert response["result"] == ("CORRECT" if correct else "WRONG")
        assert response["correct_option_id"] == version.options[-1].option_id
        assert response["correct_answer"] == f"보기 {count}"
    assert wrong_state(database, records, version.question_version_id)["status"] == "RESOLVED"


@pytest.mark.parametrize("unavailable", ["DRAFT", "missing_file"])
def test_unavailable_content_blocks_new_submission_but_allows_successful_retry(
    client, database, records, unavailable
):
    attempt = create(client, records)
    display(database, attempt)
    media = database.scalar(
        text(
            "SELECT storage_path FROM sasu.video_assets WHERE video_asset_id = "
            "(SELECT video_asset_id FROM sasu.contents WHERE content_id = :id)"
        ),
        {"id": attempt["question"]["content_id"]},
    )
    file = get_settings().video_storage_root / media
    original = file.read_bytes()

    def change(available):
        if unavailable == "DRAFT":
            database.execute(
                text("UPDATE sasu.contents SET status = :status WHERE content_id = :id"),
                {
                    "id": attempt["question"]["content_id"],
                    "status": "PUBLISHED" if available else "DRAFT",
                },
            )
            database.commit()
        elif available:
            file.write_bytes(original)
        else:
            file.unlink()

    change(False)
    response = submit(client, records, attempt, answer(attempt), status=404)
    assert response["detail"]["code"] == "CONTENT_NOT_FOUND"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0
    change(True)
    first = submit(client, records, attempt, answer(attempt))
    change(False)
    assert submit(client, records, attempt, answer(attempt)) == first


@pytest.mark.parametrize(
    "initial,retry", [("ANSWER", "OTHER_OPTION"), ("ANSWER", "SKIP"), ("SKIP", "ANSWER")]
)
def test_different_answer_or_action_cannot_replace_submission(
    client, database, records, initial, retry
):
    attempt = create(client, records)
    display(database, attempt)
    first = answer(attempt) if initial == "ANSWER" else {"action": "SKIP"}
    original = submit(client, records, attempt, first)
    changed = (
        {"action": "SKIP"} if retry == "SKIP" else answer(attempt, correct=retry != "OTHER_OPTION")
    )
    response = submit(client, records, attempt, changed, status=409)
    assert response["detail"]["code"] == "ALREADY_SUBMITTED"
    assert submit(client, records, attempt, first) == original
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 1


@pytest.mark.parametrize("foreign", [False, True])
def test_option_must_belong_to_fixed_version(client, database, records, foreign):
    attempt = create(client, records)
    display(database, attempt)
    option = records["questions"][1]["options"][0]["option_id"] if foreign else 2**63 - 1
    response = submit(
        client, records, attempt, {"action": "ANSWER", "selected_option_id": option}, status=422
    )
    assert response["detail"]["code"] == "INVALID_OPTION"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"action": "ANSWER"},
        {"action": "ANSWER", "selected_option_id": None},
        {"action": "OTHER"},
        {"action": "SKIP", "selected_option_id": 1},
        {"action": "ANSWER", "selected_option_id": True},
        {"action": "ANSWER", "selected_option_id": "1"},
        {"action": "ANSWER", "selected_option_id": 0},
        {"action": "ANSWER", "selected_option_id": 2**63},
        {"action": "ANSWER", "selected_option_id": -1},
        {"action": "SKIP", "result": "CORRECT"},
    ],
)
def test_submission_input_validation_has_no_writes(client, database, records, payload):
    attempt = create(client, records)
    response = submit(client, records, attempt, payload, status=422)
    assert response["detail"]["code"] == "VALIDATION_ERROR"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0


@pytest.mark.parametrize(
    "actor,target,status",
    [
        ("admin", "learner", 403),
        ("other", "learner", 404),
        ("other", "other", 404),
        ("no_state", "no_state", 404),
    ],
)
def test_submission_requires_own_current_learner(client, records, actor, target, status):
    attempt = create(client, records)
    response = client.put(
        base(records, target) + f"/{attempt['attempt_id']}/response",
        headers=headers(records, actor),
        json=answer(attempt),
    )
    assert response.status_code == status


def test_reset_rejects_stale_generation_and_hides_attempt(client, database, records):
    attempt, _ = answered(client, database, records)
    database.scalar(text("SELECT sasu.reset_learning(:user, 1)"), {"user": records["learner"]})
    database.commit()
    response = submit(client, records, attempt, answer(attempt), status=409)
    assert response["detail"]["code"] == "RECORD_GENERATION_MISMATCH"
    response = client.put(
        base(records) + f"/{attempt['attempt_id']}/response",
        headers=headers(records, generation=1),
        json=answer(attempt),
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"


@pytest.mark.parametrize("generation", [None, "-1", "invalid", str(2**31 - 1)])
def test_submission_requires_valid_generation_header(client, records, generation):
    attempt = create(client, records)
    actor_headers = {"X-Actor-Id": str(records["learner"])}
    if generation is not None:
        actor_headers["X-Record-Generation"] = generation
    response = client.put(
        base(records) + f"/{attempt['attempt_id']}/response",
        headers=actor_headers,
        json=answer(attempt),
    )
    assert response.status_code == 422


def test_submission_unknown_query_bad_json_uuid_and_missing_attempt(client, records):
    attempt = create(client, records)
    url = base(records) + f"/{attempt['attempt_id']}/response"
    assert (
        client.put(url + "?extra=1", headers=headers(records), json=answer(attempt)).status_code
        == 422
    )
    assert (
        client.put(url, headers={"X-Record-Generation": "0"}, json=answer(attempt)).status_code
        == 422
    )
    bad_json = client.put(
        url, headers={**headers(records), "Content-Type": "application/json"}, content="{"
    )
    assert bad_json.status_code == 400 and bad_json.json()["detail"]["code"] == "INVALID_REQUEST"
    assert (
        client.put(
            base(records) + "/bad/response", headers=headers(records), json=answer(attempt)
        ).status_code
        == 422
    )
    response = client.put(
        base(records) + f"/{uuid4()}/response", headers=headers(records), json=answer(attempt)
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "ATTEMPT_NOT_FOUND"


@pytest.mark.parametrize("failure", ["insert", "commit"])
def test_response_and_wrong_state_rollback_together_then_retry_once(
    client, database, records, monkeypatch, failure
):
    attempt = create(client, records)
    display(database, attempt)
    request = answer(attempt, correct=False)
    original = repository.insert_response

    def fail(*args):
        if failure == "insert":
            original(*args)
        raise OperationalError("private SQL", {}, Exception("secret password"))

    if failure == "insert":
        monkeypatch.setattr(repository, "insert_response", fail)
    else:
        event.listen(Session, "before_commit", fail)
    try:
        response = submit(client, records, attempt, request, status=500)
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail)
        else:
            monkeypatch.setattr(repository, "insert_response", original)
    assert response["detail"]["code"] == "INTERNAL_ERROR"
    assert "private" not in str(response) and "secret" not in str(response)
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0
    assert wrong_state(database, records) is None
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_attempts")) == 1
    result = submit(client, records, attempt, request)
    assert result["wrong_state"]["wrong_count"] == 1
    assert submit(client, records, attempt, request) == result
