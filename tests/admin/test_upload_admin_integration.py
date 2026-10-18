"""실제 PostgreSQL·MP4에서 콘텐츠 업로드와 관리자 모듈의 연계를 검증한다."""

import subprocess
from uuid import uuid4

from sqlalchemy import text

from app.core.config import get_settings


def payload(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def test_uploaded_content_connects_to_quiz_course_statistics_and_reset(client, database, tmp_path):
    users = {}
    for username, role in (("admin", "ADMIN"), ("learner", "LEARNER")):
        users[username] = database.scalar(
            text("""INSERT INTO sasu.app_users (username, display_name, role)
                    VALUES (:username, :username, :role) RETURNING user_id"""),
            {"username": username, "role": role},
        )
    database.execute(
        text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"),
        {"id": users["learner"]},
    )
    database.commit()
    admin = {"X-Actor-Id": str(users["admin"])}
    learner = {"X-Actor-Id": str(users["learner"])}
    category = payload(
        client.post("/api/categories", headers=admin, json={"name": "업로드 분류"}), 201
    )
    tag = payload(client.post("/api/tags", headers=admin, json={"name": "통합 태그"}), 201)
    content = payload(
        client.post(
            "/api/contents",
            headers=admin,
            json={
                "title": "통합 콘텐츠",
                "category_id": category["category_id"],
                "tag_ids": [tag["tag_id"]],
                "core_content": "업로드한 콘텐츠의 퀴즈와 학습 구조를 관리합니다.",
                "source": "통합 검증 자료",
                "reviewed_on": "2026-10-18",
            },
        ),
        201,
    )["detail"]["content"]
    content_id = content["content_id"]
    source = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:r=10",
            "-t",
            "1.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    video = payload(
        client.put(
            f"/api/contents/{content_id}/video",
            headers=admin,
            files={"file": ("sample.mp4", source.read_bytes(), "video/mp4")},
        )
    )
    assert video["video_duration"] > 0 and video["media_revision"]
    question = payload(
        client.post(
            f"/api/contents/{content_id}/question",
            headers=admin,
            json={
                "question_type": "OX",
                "question_text": "업로드된 콘텐츠의 퀴즈인가요?",
                "explanation": "콘텐츠와 같은 문항·버전 ID를 사용합니다.",
                "options": [
                    {"option_order": 1, "option_text": "O", "is_correct": True},
                    {"option_order": 2, "option_text": "X", "is_correct": False},
                ],
            },
        ),
        201,
    )
    published = payload(client.post(f"/api/contents/{content_id}/publish", headers=admin))
    assert published["detail"]["content"]["status"] == "PUBLISHED"
    course = payload(
        client.post("/api/curriculums", headers=admin, json={"title": "통합 과정"}), 201
    )
    course_id = course["summary"]["curriculum_id"]
    steps = payload(
        client.put(
            f"/api/curriculums/{course_id}/steps", headers=admin, json={"content_ids": [content_id]}
        )
    )
    assert steps["items"][0]["content_id"] == content_id

    for table in ("content_likes", "saved_contents"):
        database.execute(
            text(
                f"INSERT INTO sasu.{table} (user_id, learning_epoch, content_id) "
                "VALUES (:user, 1, :content)"
            ),
            {"user": users["learner"], "content": content_id},
        )
    attempt = uuid4()
    database.execute(
        text("""INSERT INTO sasu.quiz_attempts
                (attempt_id, user_id, learning_epoch, quiz_id, quiz_version_id, context)
                VALUES (:id, :user, 1, :quiz, :version, 'WRONG_REVIEW')"""),
        {
            "id": attempt,
            "user": users["learner"],
            "quiz": question["question_id"],
            "version": question["question_version_id"],
        },
    )
    response_id = database.scalar(
        text("""INSERT INTO sasu.quiz_responses
                (attempt_id, quiz_version_id, selected_option_id, result)
                VALUES (:id, :version, :option, 'WRONG') RETURNING response_id"""),
        {
            "id": attempt,
            "version": question["question_version_id"],
            "option": question["options"][1]["option_id"],
        },
    )
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    database.commit()

    detail = payload(client.get(f"/api/contents/{content_id}", headers=learner))
    assert detail["content"]["has_quiz"] is True
    assert detail["content"]["liked"] is True and detail["content"]["saved"] is True
    assert detail["content"]["like_count"] == 1
    assert detail["related_curriculums"] == [{"curriculum_id": course_id, "title": "통합 과정"}]
    renamed = payload(
        client.patch(
            f"/api/categories/{category['category_id']}", headers=admin, json={"name": "수정 분류"}
        )
    )
    assert (
        payload(client.get(f"/api/contents/{content_id}", headers=learner))["content"]["category"]
        == renamed
    )
    stats = payload(client.get(f"/api/contents/{content_id}/statistics/reactions", headers=admin))
    assert stats["like_count"] == stats["saved_count"] == 1
    result = payload(client.get(f"/api/responses/{response_id}", headers=learner))
    assert result["question"]["question_version_id"] == question["question_version_id"]
    assert result["result"] == "WRONG" and result["wrong_state"]["status"] == "PENDING"

    reset = payload(
        client.post(
            f"/api/users/{users['learner']}/test-records/reset",
            headers=admin,
            json={"confirm": True, "expected_record_generation": 0},
        )
    )
    assert reset["record_generation"] == 1
    assert reset["deleted_counts"]["responses"] == reset["deleted_counts"]["attempts"] == 1
    assert client.get(f"/api/responses/{response_id}", headers=learner).status_code == 404
    assert (
        database.scalar(
            text("SELECT count(*) FROM sasu.contents WHERE content_id = :id"), {"id": content_id}
        )
        == 1
    )
    assert len(list(get_settings().video_storage_root.glob("*.mp4"))) == 1
