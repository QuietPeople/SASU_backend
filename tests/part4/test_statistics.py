from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import get_settings


def execute(db, sql, **params):
    return db.execute(text(sql), params)


@pytest.fixture
def records(database):
    users = {}
    for name, role in [("admin", "ADMIN"), ("user1", "LEARNER"), ("other", "LEARNER")]:
        users[name] = execute(
            database,
            """INSERT INTO sasu.app_users(username,display_name,role)
            VALUES(:name,:name,:role) RETURNING user_id""",
            name=name,
            role=role,
        ).scalar_one()
        if role == "LEARNER":
            execute(database, "INSERT INTO sasu.user_settings(user_id) VALUES(:id)", id=users[name])
    category = execute(
        database, "INSERT INTO sasu.categories(name) VALUES('테스트') RETURNING category_id"
    ).scalar_one()
    tag = execute(
        database, "INSERT INTO sasu.tags(name) VALUES('태그') RETURNING tag_id"
    ).scalar_one()
    asset = uuid4()
    root = get_settings().video_storage_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "test.mp4").write_bytes(b"fixture")
    execute(
        database,
        """INSERT INTO sasu.video_assets(video_asset_id,storage_path,original_name,
        mime_type,size_bytes,duration_seconds)
        VALUES(:id,'test.mp4','test.mp4','video/mp4',7,10)""",
        id=asset,
    )
    content = execute(
        database,
        """INSERT INTO sasu.contents(created_by_user_id,video_asset_id,
        category_id,title,core_content,source,reviewed_on)
        VALUES(:admin,:asset,:cat,'영상','핵심','자체',current_date) RETURNING content_id""",
        admin=users["admin"],
        asset=asset,
        cat=category,
    ).scalar_one()
    execute(database, "INSERT INTO sasu.content_tags VALUES(:c,:t)", c=content, t=tag)
    execute(
        database,
        "UPDATE sasu.contents SET status='PUBLISHED',published_at=now() WHERE content_id=:c",
        c=content,
    )
    quiz = execute(
        database, "INSERT INTO sasu.quizzes(content_id) VALUES(:c) RETURNING quiz_id", c=content
    ).scalar_one()
    version = execute(
        database,
        """INSERT INTO sasu.quiz_versions(quiz_id,version_no,question_type,
        question_text,explanation) VALUES(:q,1,'OX','질문','설명') RETURNING quiz_version_id""",
        q=quiz,
    ).scalar_one()
    options = {}
    for pos, label, correct in [(1, "O", True), (2, "X", False)]:
        options[correct] = execute(
            database,
            """INSERT INTO sasu.quiz_options(quiz_version_id,position,
            option_text,is_correct) VALUES(:v,:p,:label,:correct) RETURNING option_id""",
            v=version,
            p=pos,
            label=label,
            correct=correct,
        ).scalar_one()
    execute(
        database,
        "UPDATE sasu.quizzes SET current_version_id=:v WHERE quiz_id=:q",
        v=version,
        q=quiz,
    )
    curriculum = execute(
        database, "INSERT INTO sasu.curricula(title) VALUES('과정') RETURNING curriculum_id"
    ).scalar_one()
    execute(
        database, "INSERT INTO sasu.curriculum_items VALUES(:cr,:c,1)", cr=curriculum, c=content
    )
    execute(database, "SET CONSTRAINTS ALL IMMEDIATE")
    execute(database, "SET CONSTRAINTS ALL DEFERRED")
    database.commit()
    return {
        **users,
        "content": content,
        "quiz": quiz,
        "version": version,
        "options": options,
        "category": category,
        "curriculum": curriculum,
    }


def headers(r, who="admin"):
    return {"X-Actor-Id": str(r[who])}


def answer(db, r, context, result, display=True, user=None):
    attempt = uuid4()
    user = user or r["user1"]
    execute(
        db,
        """INSERT INTO sasu.quiz_attempts(attempt_id,user_id,learning_epoch,quiz_id,
        quiz_version_id,context) VALUES(:a,:u,1,:q,:v,:ctx)""",
        a=attempt,
        u=user,
        q=r["quiz"],
        v=r["version"],
        ctx=context,
    )
    if display:
        execute(
            db,
            """INSERT INTO sasu.learning_events(event_id,user_id,learning_epoch,event_type,
            content_id,quiz_version_id,attempt_id)
            VALUES(:e,:u,1,'QUIZ_DISPLAYED',:c,:v,:a)""",
            e=uuid4(),
            u=user,
            c=r["content"],
            v=r["version"],
            a=attempt,
        )
    if result:
        execute(
            db,
            """INSERT INTO sasu.quiz_responses(attempt_id,quiz_version_id,selected_option_id,result)
            VALUES(:a,:v,:o,:r)""",
            a=attempt,
            v=r["version"],
            o=None if result == "SKIPPED" else r["options"][result == "CORRECT"],
            r=result,
        )
    db.commit()
    return attempt


def stats(client, r, suffix=""):
    response = client.get(f"/api/contents/{r['content']}/statistics{suffix}", headers=headers(r))
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_statistics_and_dashboard(client, records):
    r = records
    s = stats(client, r)
    assert s["quiz"]["first_accuracy"] == {"numerator": 0, "denominator": 0, "percent": None}
    assert s["quiz"]["first_accuracy"]["percent"] is None
    assert s["reactions"]["watch_completion"]["percent"] is None
    response = client.get(f"/api/users/{r['user1']}/dashboard", headers=headers(r, "user1"))
    assert response.status_code == 200, response.text
    assert response.json()["curriculums"] == []
    response = client.get(
        f"/api/users/{r['user1']}/dashboard/categories", headers=headers(r, "user1")
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["state"] == "NO_PENDING_WRONG"


def test_first_answer_repeat_skip_and_actual_display(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "SKIPPED")
    answer(database, r, "VIDEO_END", "WRONG")
    answer(database, r, "VIDEO_END", "CORRECT", display=False)
    answer(database, r, "VIDEO_END", None)
    s = stats(client, r)["quiz"]
    assert s["first_accuracy"] == {"numerator": 0, "denominator": 1, "percent": 0.0}
    assert s["participation"] == {"numerator": 2, "denominator": 3, "percent": 66.67}
    assert s["skipped_count"] == 1
    answer(database, r, "FEED_REVIEW", "WRONG")
    answer(database, r, "FEED_REVIEW", "CORRECT")
    answer(database, r, "FEED_REVIEW", "CORRECT")
    assert stats(client, r)["feed_review"]["accuracy"] == {
        "numerator": 2,
        "denominator": 3,
        "percent": 66.67,
    }


def test_wrong_cards_and_reset(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "WRONG")
    execute(
        database,
        """INSERT INTO sasu.watch_records(user_id,learning_epoch,content_id,
        first_played_at,last_watched_at,view_counted_at,completed_at,max_coverage_ratio)
        VALUES(:u,1,:c,now(),now(),now(),now(),1)""",
        u=r["user1"],
        c=r["content"],
    )
    execute(
        database,
        "INSERT INTO sasu.content_likes(user_id,learning_epoch,content_id) VALUES(:u,1,:c)",
        u=r["user1"],
        c=r["content"],
    )
    execute(
        database,
        "INSERT INTO sasu.saved_contents(user_id,learning_epoch,content_id) VALUES(:u,1,:c)",
        u=r["user1"],
        c=r["content"],
    )
    for event in ["CARD_OPENED", "CARD_OPENED", "CARD_REVEALED"]:
        execute(
            database,
            """INSERT INTO sasu.learning_events(event_id,user_id,learning_epoch,event_type,
            content_id,quiz_version_id) VALUES(:e,:u,1,:type,:c,:v)""",
            e=uuid4(),
            u=r["user1"],
            type=event,
            c=r["content"],
            v=r["version"],
        )
    database.commit()
    category_url = f"/api/users/{r['user1']}/dashboard/categories"
    assert (
        client.get(category_url, headers=headers(r)).json()["items"][0]["state"] == "NEEDS_REVIEW"
    )
    s = stats(client, r)
    assert s["flashcards"] == {
        "viewed_count": 2,
        "flipped_count": 1,
    }
    assert s["wrong_review"]["pending_count"] == 1
    assert s["reactions"]["view_count"] == 1
    dash = client.get(f"/api/users/{r['user1']}/dashboard", headers=headers(r)).json()
    assert dash["curriculums"] == []
    answer(database, r, "WRONG_REVIEW", "CORRECT")
    assert stats(client, r)["wrong_review"]["resolved_count"] == 1
    progress = client.get(
        f"/api/users/{r['user1']}/curriculums/{r['curriculum']}/progress", headers=headers(r)
    )
    assert progress.status_code == 200, progress.text
    assert progress.json()["progress_percent"] == 100
    reset = client.post(
        f"/api/users/{r['user1']}/test-records/reset",
        headers=headers(r),
        json={"confirm": True, "expected_record_generation": 0},
    )
    assert reset.status_code == 200, reset.text
    s = stats(client, r)
    assert (
        s["reactions"]["view_count"]
        == s["reactions"]["like_count"]
        == s["reactions"]["saved_count"]
        == 0
    )
    assert s["quiz"]["first_accuracy"]["percent"] is None
    assert s["flashcards"]["viewed_count"] == 0
    dash = client.get(f"/api/users/{r['user1']}/dashboard", headers=headers(r)).json()
    assert (
        dash["watched_content_count"]
        == dash["answered_count"]
        == dash["pending_question_count"]
        == 0
    )
    progress = client.get(
        f"/api/users/{r['user1']}/curriculums/{r['curriculum']}/progress", headers=headers(r)
    ).json()
    assert progress["completed_steps"] == 0


def test_permissions_validation_and_history(client, database, records):
    r = records
    for path in [
        "/api/statistics",
        "/api/statistics/contents",
        "/api/responses",
        f"/api/contents/{r['content']}/statistics",
    ]:
        assert client.get(path, headers=headers(r, "user1")).status_code == 403
        assert client.get(path).status_code == 422
    assert (
        client.get(f"/api/users/{r['other']}/dashboard", headers=headers(r, "user1")).status_code
        == 404
    )
    assert client.get("/api/users/999999/dashboard", headers=headers(r)).status_code == 404
    assert client.get(f"/api/users/{r['admin']}/dashboard", headers=headers(r)).status_code == 404
    assert client.get("/api/contents/999999/statistics", headers=headers(r)).status_code == 404
    for query in [
        "size=101",
        "page=0",
        "result=INVALID",
        "submitted_from=2026-01-01T00:00:00",
        "submitted_from=2026-02-01T00:00:00Z&submitted_to=2026-01-01T00:00:00Z",
        "extra=x",
    ]:
        assert client.get("/api/responses?" + query, headers=headers(r)).status_code == 422
    for result in ["WRONG", "CORRECT", "SKIPPED"]:
        answer(database, r, "VIDEO_END", result)
    response = client.get("/api/responses?size=2", headers=headers(r))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3 and body["has_next"] and len(body["items"]) == 2
    ids = [x["response_id"] for x in body["items"]]
    second = client.get("/api/responses?size=2&page=2", headers=headers(r)).json()
    assert len(second["items"]) == 1 and not second["has_next"]
    assert second["items"][0]["response_id"] not in ids
    assert client.get("/api/responses?page=99", headers=headers(r)).json()["total"] == 3
    assert client.get("/api/responses?result=CORRECT", headers=headers(r)).json()["total"] == 1
    assert (
        client.get(f"/api/responses?user_id={r['other']}", headers=headers(r)).json()["total"] == 0
    )
    assert client.get("/api/statistics", headers=headers(r)).status_code == 200
    assert client.get("/api/statistics/contents", headers=headers(r)).json()["total"] == 1
    for suffix in ["/quiz", "/feed-review", "/wrong-answer-review", "/flashcards"]:
        stats(client, r, suffix)


def test_latest_wrong_only_and_private_category(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "WRONG")
    execute(database, "UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:c", c=r["content"])
    database.commit()
    assert stats(client, r)["wrong_review"]["pending_count"] == 1
    categories = client.get(
        f"/api/users/{r['user1']}/dashboard/categories", headers=headers(r)
    ).json()
    assert categories["items"][0]["pending_question_count"] == 0
    assert categories["items"][0]["state"] == "NO_PENDING_WRONG"
    assert execute(database, "SELECT count(*) FROM sasu.wrong_answers").scalar_one() == 1


def test_integrated_routes_unique(client, records):
    app = client.app
    seen = set()
    for route in app.routes:
        for method in getattr(route, "methods", []):
            key = (method, route.path)
            assert key not in seen, key
            seen.add(key)
    assert ("GET", "/api/responses") in seen
    assert ("GET", "/api/responses/{response_id}") in seen
    assert ("GET", "/api/contents/{content_id}/statistics/reactions") in seen
    assert client.get("/openapi.json").status_code == 200


def test_version_change_preserves_history_but_hides_old_wrong(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "WRONG")
    version = execute(
        database,
        """INSERT INTO sasu.quiz_versions
        (quiz_id,version_no,question_type,question_text,explanation)
        VALUES(:q,2,'OX','새 문제','새 설명') RETURNING quiz_version_id""",
        q=r["quiz"],
    ).scalar_one()
    execute(
        database,
        """INSERT INTO sasu.quiz_options
        (quiz_version_id,position,option_text,is_correct)
        VALUES(:v,1,'O',true),(:v,2,'X',false)""",
        v=version,
    )
    execute(
        database,
        "UPDATE sasu.quizzes SET current_version_id=:v WHERE quiz_id=:q",
        v=version,
        q=r["quiz"],
    )
    database.commit()
    assert stats(client, r)["wrong_review"]["pending_count"] == 0
    # 과거 버전의 응답·오답 상태는 그대로 남고 최초 풀이 통계도 유지된다.
    assert stats(client, r)["quiz"]["first_accuracy"]["denominator"] == 1
    row = execute(database, "SELECT status,quiz_version_id FROM sasu.wrong_answers").one()
    assert row.status == "UNRESOLVED" and row.quiz_version_id == r["version"]
    history = client.get("/api/responses", headers=headers(r)).json()
    assert history["items"][0]["question"]["question_version_id"] == r["version"]


def test_multiuser_counts_do_not_multiply(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "WRONG")
    answer(database, r, "VIDEO_END", "CORRECT", user=r["other"])
    for user in (r["user1"], r["other"]):
        execute(
            database,
            """INSERT INTO sasu.content_likes(user_id,learning_epoch,content_id)
        VALUES(:u,1,:c)""",
            u=user,
            c=r["content"],
        )
        execute(
            database,
            """INSERT INTO sasu.watch_records(user_id,learning_epoch,content_id,
        first_played_at,last_watched_at,view_counted_at)
        VALUES(:u,1,:c,now(),now(),now())""",
            u=user,
            c=r["content"],
        )
    database.commit()
    s = stats(client, r)
    assert s["reactions"]["view_count"] == 2 and s["reactions"]["like_count"] == 2
    assert s["quiz"]["first_accuracy"] == {"numerator": 1, "denominator": 2, "percent": 50.0}
    own = client.get(f"/api/users/{r['user1']}/dashboard", headers=headers(r, "user1")).json()
    assert own["watched_content_count"] == own["answered_count"] == 1
    assert own["first_quiz_accuracy"]["percent"] == 0
    peer = client.get(f"/api/users/{r['other']}/dashboard", headers=headers(r)).json()
    assert peer["first_quiz_accuracy"]["percent"] == 100


def test_curriculum_reorder_private_steps_and_empty_course(client, database, records):
    r = records
    private = execute(
        database,
        """INSERT INTO sasu.contents(created_by_user_id,title)
        VALUES(:u,'비공개 제목') RETURNING content_id""",
        u=r["admin"],
    ).scalar_one()
    database.commit()
    steps = f"/api/curriculums/{r['curriculum']}/steps"
    for ids in [[r["content"], private], [private, r["content"]]]:
        result = client.put(steps, headers=headers(r), json={"content_ids": ids})
        assert result.status_code == 200, result.text
        assert [x["content_id"] for x in result.json()["items"]] == ids
    duplicate = client.put(steps, headers=headers(r), json={"content_ids": [private, private]})
    assert duplicate.status_code == 422
    detail = client.get(f"/api/curriculums/{r['curriculum']}", headers=headers(r, "user1"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["steps"][0]["content"] is None
    assert detail.json()["steps"][0]["available"] is False
    answer(database, r, "VIDEO_END", "CORRECT")
    execute(
        database,
        """INSERT INTO sasu.watch_records(user_id,learning_epoch,content_id,
        first_played_at,last_watched_at,completed_at,max_coverage_ratio)
        VALUES(:u,1,:c,now(),now(),now(),1)""",
        u=r["user1"],
        c=r["content"],
    )
    database.commit()
    progress = client.get(
        f"/api/users/{r['user1']}/curriculums/{r['curriculum']}/progress", headers=headers(r)
    ).json()
    assert progress["total_steps"] == 2 and progress["progress_percent"] == 50
    dashboard = client.get(f"/api/users/{r['user1']}/dashboard", headers=headers(r)).json()
    assert dashboard["curriculums"][0]["progress_percent"] == 50
    created = client.post("/api/curriculums", headers=headers(r), json={"title": "빈 과정"})
    assert created.status_code == 201, created.text
    cid = created.json()["summary"]["curriculum_id"]
    empty = client.get(f"/api/users/{r['user1']}/curriculums/{cid}/progress", headers=headers(r))
    assert empty.status_code == 200, empty.text
    assert empty.json()["total_steps"] == 0 and empty.json()["progress_percent"] is None
    assert (
        client.put(steps, headers=headers(r, "user1"), json={"content_ids": []}).status_code == 403
    )


def test_contract_filters_and_shared_response(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "SKIPPED")
    result = client.get(
        "/api/responses",
        params={
            "question_id": r["quiz"],
            "question_version_id": r["version"],
            "response_path": "VIDEO_QUIZ",
            "result": "SKIP",
        },
        headers=headers(r),
    )
    assert result.status_code == 200, result.text
    item = result.json()["items"][0]
    detail = client.get(f"/api/responses/{item['response_id']}", headers=headers(r))
    assert item == detail.json()
    assert item["result"] == "SKIP"
    assert client.get("/api/responses?question_id=999999", headers=headers(r)).status_code == 404
    private = execute(
        database,
        "INSERT INTO sasu.contents(created_by_user_id,title) "
        "VALUES(:u,'초안') RETURNING content_id",
        u=r["admin"],
    ).scalar_one()
    database.commit()
    assert (
        client.get(
            "/api/responses",
            params={"content_id": private, "question_id": r["quiz"]},
            headers=headers(r),
        ).status_code
        == 422
    )
    result = client.get(
        "/api/statistics/contents",
        params={"category_id": r["category"], "status": "PUBLISHED"},
        headers=headers(r),
    )
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 1
    assert result.json()["items"][0] == stats(client, r)
    assert (
        client.get("/api/statistics/contents?status=DRAFT", headers=headers(r)).json()["total"] == 1
    )
    assert (
        client.get("/api/statistics/contents?category_id=999999", headers=headers(r)).status_code
        == 404
    )
    overall = client.get("/api/statistics", headers=headers(r))
    assert overall.status_code == 200, overall.text
    assert overall.json()["content_count"] == 2
    assert overall.json()["quiz"] == stats(client, r)["quiz"]
    for suffix, key in [
        ("quiz", "quiz"),
        ("feed-review", "feed_review"),
        ("wrong-answer-review", "wrong_review"),
        ("flashcards", "flashcards"),
        ("reactions", "reactions"),
    ]:
        assert stats(client, r, "/" + suffix) == stats(client, r)[key]


def test_resolved_current_version_and_public_dashboard(client, database, records):
    r = records
    answer(database, r, "VIDEO_END", "WRONG")
    answer(database, r, "WRONG_REVIEW", "CORRECT")
    assert stats(client, r)["wrong_review"]["resolved_count"] == 1
    execute(
        database,
        """INSERT INTO sasu.watch_records(user_id,learning_epoch,content_id,
        first_played_at,last_watched_at,completed_at,max_coverage_ratio)
        VALUES(:u,1,:c,now(),now(),now(),1)""",
        u=r["user1"],
        c=r["content"],
    )
    database.commit()
    url = f"/api/users/{r['user1']}/dashboard"
    assert client.get(url, headers=headers(r)).json()["completed_content_count"] == 1
    execute(database, "UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:c", c=r["content"])
    database.commit()
    dash = client.get(url, headers=headers(r)).json()
    assert (
        dash["watched_content_count"]
        == dash["completed_content_count"]
        == dash["answered_count"]
        == 0
    )
    assert dash["first_quiz_accuracy"]["percent"] is None
    assert stats(client, r)["wrong_review"]["resolved_count"] == 1
    v = execute(
        database,
        """INSERT INTO sasu.quiz_versions(quiz_id,version_no,question_type,
        question_text,explanation) VALUES(:q,2,'OX','new','explanation')
        RETURNING quiz_version_id""",
        q=r["quiz"],
    ).scalar_one()
    execute(
        database,
        """INSERT INTO sasu.quiz_options(quiz_version_id,position,option_text,is_correct)
        VALUES(:v,1,'O',true),(:v,2,'X',false)""",
        v=v,
    )
    execute(
        database, "UPDATE sasu.quizzes SET current_version_id=:v WHERE quiz_id=:q", v=v, q=r["quiz"]
    )
    database.commit()
    assert stats(client, r)["wrong_review"]["resolved_count"] == 0
    assert stats(client, r)["wrong_review"]["answered_count"] == 1
    assert (
        execute(
            database, "SELECT count(*) FROM sasu.wrong_answers WHERE status='RESOLVED'"
        ).scalar_one()
        == 1
    )


def test_default_app_routes_and_contract():
    from app.main import app

    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/statistics" in paths
    assert "/api/users/{user_id}/dashboard" in paths
    pairs = [(r.path, m) for r in app.routes for m in getattr(r, "methods", [])]
    assert len(pairs) == len(set(pairs))
    assert set(schema["components"]["schemas"]["Overview"]["properties"]) == {
        "content_count",
        "published_content_count",
        "reactions",
        "quiz",
        "feed_review",
        "wrong_review",
        "flashcards",
    }
