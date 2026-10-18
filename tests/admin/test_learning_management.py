"""문항 버전·응답 보존과 커리큘럼 단계 편성의 HTTP/실제 DB 통합 검증."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.modules.curricula import repository as curricula_repository
from app.modules.questions import repository as questions_repository


@pytest.fixture
def records(database):
    users = {}
    for username, role in (("admin", "ADMIN"), ("user1", "LEARNER"), ("other", "LEARNER")):
        users[username] = database.scalar(
            text("""INSERT INTO sasu.app_users (username, display_name, role)
                    VALUES (:name, :name, :role) RETURNING user_id"""),
            {"name": username, "role": role},
        )
        if role == "LEARNER":
            database.execute(
                text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"),
                {"id": users[username]},
            )
    category = database.scalar(
        text("INSERT INTO sasu.categories (name) VALUES ('엑셀') RETURNING category_id")
    )
    tag = database.scalar(text("INSERT INTO sasu.tags (name) VALUES ('기초') RETURNING tag_id"))
    root = get_settings().video_storage_root
    root.mkdir(parents=True, exist_ok=True)
    contents = []
    for index in range(4):
        asset = uuid4()
        relative = f"lesson{index}.mp4"
        if index != 3:
            (root / relative).write_bytes(b"fixture media")
        database.execute(
            text("""INSERT INTO sasu.video_assets (video_asset_id, storage_path, original_name,
                    mime_type, size_bytes, duration_seconds)
                    VALUES (:id, :path, :path, 'video/mp4', 13, 10)"""),
            {"id": asset, "path": relative},
        )
        content = database.scalar(
            text("""INSERT INTO sasu.contents (created_by_user_id, video_asset_id, category_id,
                    title, core_content, source, reviewed_on)
                    VALUES (:admin, :asset, :category, :title,
                            '핵심 내용', '검수 자료', CURRENT_DATE)
                    RETURNING content_id"""),
            {
                "admin": users["admin"],
                "asset": asset,
                "category": category,
                "title": f"영상{index}",
            },
        )
        database.execute(
            text("INSERT INTO sasu.content_tags VALUES (:content, :tag)"),
            {"content": content, "tag": tag},
        )
        if index != 2:
            database.execute(
                text(
                    "UPDATE sasu.contents SET status = 'PUBLISHED', published_at = now() "
                    "WHERE content_id = :id"
                ),
                {"id": content},
            )
        contents.append(content)
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    database.commit()
    return {**users, "contents": contents}


def headers(records, user="admin"):
    return {"X-Actor-Id": str(records[user])}


def question_body(kind="MCQ_3"):
    labels = (
        ["O", "X"]
        if kind == "OX"
        else [f"보기{index}" for index in range(1, 5 if kind == "MCQ_4" else 4)]
    )
    return {
        "question_type": kind,
        "question_text": "  문제  ",
        "explanation": "  정답 해설  ",
        "options": [
            {"option_order": index, "option_text": label, "is_correct": index == 1}
            for index, label in enumerate(labels, start=1)
        ],
    }


def register(client, records, index=0, body=None):
    response = client.post(
        f"/api/contents/{records['contents'][index]}/question",
        headers=headers(records),
        json=body or question_body(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_course(client, records, content_ids=None, title="기초 과정"):
    response = client.post(
        "/api/curriculums",
        headers=headers(records),
        json={"title": title, "description": "과정 설명"},
    )
    assert response.status_code == 201, response.text
    course = response.json()["summary"]["curriculum_id"]
    if content_ids is not None:
        response = client.put(
            f"/api/curriculums/{course}/steps",
            headers=headers(records),
            json={"content_ids": content_ids},
        )
        assert response.status_code == 200, response.text
    return course


def assert_constraints(database):
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def add_answer(database, records, question, correct=True, context="VIDEO_END"):
    attempt = uuid4()
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
                (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                VALUES (:id, :user, 1, :quiz, :version, :context)"""),
        {
            "id": attempt,
            "user": records["user1"],
            "quiz": question["question_id"],
            "version": question["question_version_id"],
            "context": context,
        },
    )
    response_id = database.scalar(
        text("""INSERT INTO sasu.quiz_responses
                (attempt_id, quiz_version_id, selected_option_id, result)
                VALUES (:id, :version, :option, :result) RETURNING response_id"""),
        {
            "id": attempt,
            "version": question["question_version_id"],
            "option": question["options"][0 if correct else 1]["option_id"],
            "result": "CORRECT" if correct else "WRONG",
        },
    )
    database.commit()
    return response_id


def test_current_question_absence_and_visibility(client, records):
    path = f"/api/contents/{records['contents'][0]}/question"
    response = client.get(path, headers=headers(records, "user1"))
    assert response.status_code == 200 and response.json() is None
    path = f"/api/contents/{records['contents'][2]}/question"
    assert client.get(path, headers=headers(records, "user1")).status_code == 404
    assert client.get(path + "?view=editor", headers=headers(records)).json() is None
    assert client.get(path + "?view=editor", headers=headers(records, "user1")).status_code == 403
    assert client.get("/api/contents/999999/question", headers=headers(records)).status_code == 404


@pytest.mark.parametrize("kind", ["OX", "MCQ_3", "MCQ_4"])
def test_question_types_and_answer_separation(client, records, database, kind):
    body = question_body(kind)
    if kind == "MCQ_3":
        body.pop("question_type")
    question = register(client, records, body=body)
    assert question["question_type"] == kind
    assert question["question_text"] == "문제" and question["explanation"] == "정답 해설"
    assert question["version_no"] == 1 and question["is_current"] is True
    assert len({option["option_id"] for option in question["options"]}) == len(body["options"])
    assert database.scalar(text("SELECT question_type FROM sasu.quiz_versions")) == kind.replace(
        "_", ""
    )
    learner = client.get(
        f"/api/contents/{records['contents'][0]}/question", headers=headers(records, "user1")
    ).json()
    assert "explanation" not in learner
    assert all("is_correct" not in option for option in learner["options"])
    version_path = (
        f"/api/questions/{question['question_id']}/versions/{question['question_version_id']}"
    )
    assert client.get(version_path, headers=headers(records)).json() == question
    assert client.get(version_path, headers=headers(records, "user1")).status_code == 403
    assert_constraints(database)


@pytest.mark.parametrize(
    "invalid", ["count", "positions", "two_correct", "no_correct", "ox_labels"]
)
def test_invalid_options_never_create_partial_quiz(client, records, database, invalid):
    body = question_body("OX" if invalid == "ox_labels" else "MCQ_3")
    if invalid == "count":
        body["options"].pop()
    if invalid == "positions":
        body["options"][1]["option_order"] = 1
    if invalid == "two_correct":
        body["options"][1]["is_correct"] = True
    if invalid == "no_correct":
        body["options"][0]["is_correct"] = False
    if invalid == "ox_labels":
        body["options"][0]["option_text"] = "맞음"
    response = client.post(
        f"/api/contents/{records['contents'][0]}/question", headers=headers(records), json=body
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_OPTION"
    assert database.scalar(text("SELECT count(*) FROM sasu.quizzes")) == 0


def test_duplicate_registration_and_version_conflicts(client, records, database):
    first = register(client, records)
    response = client.post(
        f"/api/contents/{records['contents'][0]}/question",
        headers=headers(records),
        json=question_body(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "QUESTION_ALREADY_EXISTS"
    path = f"/api/questions/{first['question_id']}/versions"
    body = {**question_body(), "expected_current_version_id": first["question_version_id"]}
    assert client.post(path, headers=headers(records), json=body).status_code == 201
    response = client.post(path, headers=headers(records), json=body)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "VERSION_CONFLICT"
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_versions")) == 2
    assert_constraints(database)


def test_old_versions_responses_and_wrong_answers_are_preserved(client, records, database):
    first = register(client, records)
    response_id = add_answer(database, records, first, correct=False)
    body = {
        **question_body("MCQ_4"),
        "expected_current_version_id": first["question_version_id"],
        "question_text": "수정 문제",
        "explanation": "수정 해설",
    }
    path = f"/api/questions/{first['question_id']}/versions"
    updated = client.post(path, headers=headers(records), json=body)
    assert updated.status_code == 201, updated.text
    second = updated.json()
    assert second["version_no"] == 2 and second["question_id"] == first["question_id"]
    assert {option["option_id"] for option in first["options"]}.isdisjoint(
        option["option_id"] for option in second["options"]
    )
    previous = client.get(
        path + f"/{first['question_version_id']}", headers=headers(records)
    ).json()
    assert previous == {**first, "is_current": False}
    assert (
        database.scalar(
            text("SELECT quiz_version_id FROM sasu.quiz_responses WHERE response_id = :id"),
            {"id": response_id},
        )
        == first["question_version_id"]
    )
    assert (
        database.scalar(text("SELECT quiz_version_id FROM sasu.wrong_answers"))
        == first["question_version_id"]
    )
    listing = client.get(path + "?size=1", headers=headers(records)).json()
    assert listing["total"] == 2 and listing["has_next"] is True
    older = client.get(path + "?size=1&page=2", headers=headers(records)).json()["items"][0]
    assert older["response_count"] == 1 and older["is_current"] is False
    assert (
        client.get(path + "?page=99999999999999999999", headers=headers(records)).json()["items"]
        == []
    )
    assert (
        client.get(
            f"/api/questions/999999/versions/{first['question_version_id']}",
            headers=headers(records),
        ).status_code
        == 404
    )
    assert_constraints(database)


def test_question_insert_failure_rolls_back_whole_version(client, records, database, monkeypatch):
    original = questions_repository.create_options

    def fail(session, version_id, options):
        original(session, version_id, options)
        raise OperationalError("hidden query", {}, Exception("private connection"))

    monkeypatch.setattr(questions_repository, "create_options", fail)
    response = client.post(
        f"/api/contents/{records['contents'][0]}/question",
        headers=headers(records),
        json=question_body(),
    )
    assert response.status_code == 500 and "private" not in response.text
    for table in ("quizzes", "quiz_versions", "quiz_options"):
        assert database.scalar(text(f"SELECT count(*) FROM sasu.{table}")) == 0


def test_empty_course_create_patch_and_visibility(client, records):
    course = create_course(client, records)
    path = f"/api/curriculums/{course}"
    detail = client.get(path + "?view=editor", headers=headers(records)).json()
    assert detail["steps"] == [] and detail["summary"]["progress_percent"] is None
    assert client.get(path, headers=headers(records, "user1")).status_code == 404
    response = client.patch(path, headers=headers(records), json={"description": None})
    assert response.status_code == 200
    assert response.json()["description"] is None and response.json()["title"] == "기초 과정"
    for body in ({}, {"title": None}, {"title": " "}, {"unknown": 1}):
        assert client.patch(path, headers=headers(records), json=body).status_code == 422
    progress = client.get(
        f"/api/users/{records['user1']}/curriculums/{course}/progress",
        headers=headers(records, "user1"),
    ).json()
    assert progress["total_steps"] == progress["completed_steps"] == 0
    assert progress["progress_percent"] is None


def test_reordering_preserves_step_ids_and_exclusion_keeps_content(client, records, database):
    ids = records["contents"][:3]
    course = create_course(client, records, ids)
    path = f"/api/curriculums/{course}/steps"
    original = client.get(path + "?view=editor", headers=headers(records)).json()
    identifiers = {item["content_id"]: item["curriculum_content_id"] for item in original["items"]}
    # 즉시 UNIQUE 검사 모드에서도 순번 교환이 충돌하지 않아야 한다.
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    reordered = client.put(path, headers=headers(records), json={"content_ids": ids[::-1]})
    assert reordered.status_code == 200, reordered.text
    assert [item["content_id"] for item in reordered.json()["items"]] == ids[::-1]
    assert [item["step_order"] for item in reordered.json()["items"]] == [1, 2, 3]
    assert all(
        item["curriculum_content_id"] == identifiers[item["content_id"]]
        for item in reordered.json()["items"]
    )
    assert (
        client.put(path, headers=headers(records), json={"content_ids": [ids[1]]}).status_code
        == 200
    )
    assert client.put(path, headers=headers(records), json={"content_ids": []}).json() == {
        "items": [],
        "total_steps": 0,
    }
    assert database.scalar(text("SELECT count(*) FROM sasu.contents")) == 4


def test_invalid_step_replacement_keeps_existing_composition(client, records):
    ids = records["contents"][:2]
    course = create_course(client, records, ids)
    path = f"/api/curriculums/{course}/steps"
    for content_ids, status, code in (
        ([ids[0], ids[0]], 422, "DUPLICATE_CONTENT"),
        ([ids[0], 999999], 404, "CONTENT_NOT_FOUND"),
    ):
        response = client.put(path, headers=headers(records), json={"content_ids": content_ids})
        assert response.status_code == status and response.json()["detail"]["code"] == code
        current = client.get(path + "?view=editor", headers=headers(records)).json()
        assert [item["content_id"] for item in current["items"]] == ids
    assert (
        client.put(path, headers=headers(records), json={"content_ids": [True]}).status_code == 422
    )


def test_learner_hides_drafts_missing_media_and_keeps_all_slots(client, records):
    ids = [records["contents"][2], records["contents"][0], records["contents"][3]]
    course = create_course(client, records, ids)
    path = f"/api/curriculums/{course}"
    response = client.get(path, headers=headers(records, "user1"))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["summary"]["total_steps"] == 3 and detail["summary"]["available_steps"] == 1
    assert [item["available"] for item in detail["steps"]] == [False, True, False]
    assert detail["steps"][0]["content"] is None and detail["steps"][2]["content"] is None
    content = detail["steps"][1]["content"]
    assert content["category"]["name"] == "엑셀" and content["tags"][0]["name"] == "기초"
    assert "storage_path" not in content and content["video_duration"] == 10
    editor = client.get(path + "?view=editor", headers=headers(records)).json()
    assert editor["steps"][0]["content"]["status"] == "DRAFT"
    assert "preview=true" in editor["steps"][0]["content"]["video_url"]


def test_course_lists_filter_before_paging_and_enforce_personal_access(client, records):
    create_course(client, records)
    create_course(client, records, [records["contents"][2]])
    create_course(client, records, [records["contents"][0]])
    learner = client.get("/api/curriculums?size=1", headers=headers(records, "user1")).json()
    assert learner["total"] == 1 and learner["has_next"] is False
    editor = client.get("/api/curriculums?view=editor&size=1", headers=headers(records)).json()
    assert editor["total"] == 3 and editor["has_next"] is True
    assert (
        client.get("/api/curriculums?view=editor", headers=headers(records, "user1")).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/curriculums?user_id={records['other']}", headers=headers(records, "user1")
        ).status_code
        == 404
    )
    assert client.get("/api/curriculums?unknown=1", headers=headers(records)).status_code == 422
    assert client.get("/api/curriculums?page=0", headers=headers(records)).status_code == 422


def test_progress_counts_old_version_correct_and_requires_watch_completion(
    client, records, database
):
    first = register(client, records)
    add_answer(database, records, first, context="FEED_REVIEW")
    database.execute(
        text("""INSERT INTO sasu.watch_records
                (user_id, learning_epoch, content_id,
                 first_played_at, last_watched_at, completed_at)
                VALUES (:user, 1, :content, now(), now(), now())"""),
        {"user": records["user1"], "content": records["contents"][0]},
    )
    database.commit()
    course = create_course(client, records, records["contents"][:3])
    body = {**question_body(), "expected_current_version_id": first["question_version_id"]}
    assert (
        client.post(
            f"/api/questions/{first['question_id']}/versions", headers=headers(records), json=body
        ).status_code
        == 201
    )
    path = f"/api/users/{records['user1']}/curriculums/{course}/progress"
    response = client.get(path, headers=headers(records, "user1"))
    assert response.status_code == 200, response.text
    progress = response.json()
    assert (progress["total_steps"], progress["completed_steps"], progress["progress_percent"]) == (
        3,
        1,
        33.33,
    )
    assert [step["completed"] for step in progress["steps"]] == [True, False, False]
    assert client.get(path, headers=headers(records, "other")).status_code == 404
    assert client.get(path, headers=headers(records)).json() == progress
    assert_constraints(database)


def test_step_failure_rolls_back_reordering(client, records, database, monkeypatch):
    ids = records["contents"][:3]
    course = create_course(client, records, ids)
    original = curricula_repository.replace_steps

    def fail(session, course_id, content_ids):
        original(session, course_id, content_ids)
        raise OperationalError("hidden SQL", {}, Exception("private connection"))

    monkeypatch.setattr(curricula_repository, "replace_steps", fail)
    path = f"/api/curriculums/{course}/steps"
    response = client.put(path, headers=headers(records), json={"content_ids": ids[::-1]})
    assert response.status_code == 500
    result = client.get(path + "?view=editor", headers=headers(records)).json()
    assert [item["content_id"] for item in result["items"]] == ids


def test_unsafe_symlink_is_not_available_to_learner(client, records, database, tmp_path):
    root = get_settings().video_storage_root
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    (root / "escape.mp4").symlink_to(outside)
    database.execute(
        text("""UPDATE sasu.video_assets SET storage_path = 'escape.mp4'
                WHERE video_asset_id =
                    (SELECT video_asset_id FROM sasu.contents WHERE content_id = :id)"""),
        {"id": records["contents"][0]},
    )
    database.commit()
    course = create_course(client, records, records["contents"][:2])
    detail = client.get(f"/api/curriculums/{course}", headers=headers(records, "user1")).json()
    assert detail["steps"][0]["content"] is None
    assert detail["steps"][0]["available"] is False


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/contents/1/question", question_body()),
        (
            "post",
            "/api/questions/1/versions",
            {**question_body(), "expected_current_version_id": 1},
        ),
        ("get", "/api/questions/1/versions", None),
        ("post", "/api/curriculums", {"title": "과정"}),
        ("patch", "/api/curriculums/1", {"title": "수정"}),
        ("put", "/api/curriculums/1/steps", {"content_ids": []}),
    ],
)
def test_management_requires_admin(client, records, method, path, body):
    response = client.request(method, path, headers=headers(records, "user1"), json=deepcopy(body))
    assert response.status_code == 403
