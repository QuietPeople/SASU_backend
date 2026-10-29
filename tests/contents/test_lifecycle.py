from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import load_models
from app.db.session import get_db
from app.integrations.storage import LocalVideoStorage
from app.modules.categories.models import Category
from app.modules.contents import repository, video_service
from app.modules.contents.models import Content, ContentTag, VideoAsset
from app.modules.contents.schemas import VideoQuery
from app.modules.curricula.tables import curricula, curriculum_items
from app.modules.likes.tables import content_likes
from app.modules.questions.tables import quizzes
from app.modules.saved_contents.tables import saved_contents
from app.modules.statistics.tables import content_metrics
from app.modules.tags.models import Tag
from app.modules.users.models import User, UserRole
from app.modules.videos.service import get_video_ingest_service
from app.modules.watch_records.tables import watch_records


@pytest.fixture
def context(monkeypatch, stub_video_ingest):
    load_models()
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"sasu": None}},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    # 읽기 참조용 최소 테이블은 SQLite 테스트 안에서만 만든다.
    # 실제 PostgreSQL에서는 Alembic의 전체 테이블과 content_metrics 뷰를 검증한다.
    for table in (quizzes, content_metrics, curricula, curriculum_items):
        table.create(engine)
    content_likes.create(engine)
    saved_contents.create(engine)
    watch_records.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        admin = User(username="admin", display_name="관리자", role=UserRole.ADMIN)
        learner = User(username="learner", display_name="학습자", role=UserRole.LEARNER)
        other = User(username="other", display_name="다른 학습자", role=UserRole.LEARNER)
        category = Category(name="분류")
        tags = [Tag(name="태그"), Tag(name="SQL_100%")]
        session.add_all([admin, learner, other, category, *tags])
        session.flush()
        ids = dict(
            admin=admin.user_id,
            learner=learner.user_id,
            other=other.user_id,
            category=category.category_id,
            tags=[tag.tag_id for tag in tags],
        )

    def provide_session():
        with factory() as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    monkeypatch.setitem(main.app.dependency_overrides, get_video_ingest_service, stub_video_ingest)
    client = TestClient(main.app)
    ctx = SimpleNamespace(
        client=client,
        factory=factory,
        ids=ids,
        headers={"X-Actor-Id": str(ids["admin"])},
        root=get_settings().video_storage_root,
    )
    try:
        yield ctx
    finally:
        client.close()
        engine.dispose()


def draft(ctx, *, complete=False, **changes):
    body = (
        dict(
            title="영상 제목",
            category_id=ctx.ids["category"],
            tag_ids=ctx.ids["tags"][:1],
            core_content="첫 문장입니다. 두 번째 문장입니다.",
            source="문헌",
            reviewed_on="2026-10-18",
        )
        if complete
        else {}
    )
    body.update(changes)
    response = ctx.client.post("/api/contents", json=body, headers=ctx.headers)
    assert response.status_code == 201, response.text
    return response.json()["detail"]["content"]["content_id"]


def upload(ctx, content_id, data=b"original-video", revision=None):
    return ctx.client.put(
        f"/api/contents/{content_id}/video",
        headers=ctx.headers,
        files={"file": ("sample.mp4", data, "video/mp4")},
        data={"expected_media_revision": revision} if revision else {},
    )


def editor(ctx, content_id):
    return ctx.client.get(f"/api/contents/{content_id}?view=editor", headers=ctx.headers)


def published(ctx, **changes):
    content_id = draft(ctx, complete=True, **changes)
    assert upload(ctx, content_id).status_code == 200
    response = ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
    assert response.status_code == 200, response.text
    return content_id


def test_draft_edit_publish_and_learner_detail(context):
    ctx = context
    content_id = draft(ctx)
    detail = editor(ctx, content_id)
    assert detail.status_code == 200, detail.text
    assert len(detail.json()["missing_for_publish"]) == 7
    missing = ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "PUBLISH_REQUIREMENTS_MISSING"
    assert {f["field"] for f in missing.json()["detail"]["fields"]} == set(
        detail.json()["missing_for_publish"]
    )
    payload = dict(
        title="  완성 제목  ",
        category_id=ctx.ids["category"],
        tag_ids=ctx.ids["tags"] * 2,
        core_content="첫 문장. 두 번째 문장.",
        source="출처",
        reviewed_on="2026-10-18",
    )
    edited = ctx.client.patch(f"/api/contents/{content_id}", json=payload, headers=ctx.headers)
    assert edited.status_code == 200, edited.text
    assert edited.json()["missing_for_publish"] == ["video"]
    assert len(edited.json()["detail"]["content"]["tags"]) == 2
    uploaded = upload(ctx, content_id)
    assert uploaded.status_code == 200
    preview = ctx.client.get(uploaded.json()["video_url"])
    assert preview.status_code == 200 and preview.content == b"original-video"
    assert ctx.client.get(f"/api/contents/{content_id}/video").status_code == 404
    first = ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
    second = ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["detail"]["published_at"] == second.json()["detail"]["published_at"]
    assert first.json()["updated_at"] == second.json()["updated_at"]
    assert first.json()["missing_for_publish"] == []
    learner = ctx.client.get(
        f"/api/contents/{content_id}", headers={"X-Actor-Id": str(ctx.ids["learner"])}
    )
    assert learner.status_code == 200, learner.text
    assert "created_by_user_id" not in learner.json()
    assert learner.json()["one_line_summary"] == "첫 문장."
    assert learner.json()["content"]["liked"] is False
    assert "preview" not in learner.json()["content"]["video_url"]
    assert ctx.client.get(learner.json()["content"]["video_url"]).content == b"original-video"


def test_patch_omission_null_tag_replacement_and_caution(context):
    ctx = context
    content_id = draft(ctx, complete=True, caution_text="보관할 문구")
    response = ctx.client.patch(
        f"/api/contents/{content_id}", json={"title": "수정"}, headers=ctx.headers
    )
    assert response.status_code == 200, response.text
    content = response.json()["detail"]
    assert content["source"] == "문헌" and len(content["content"]["tags"]) == 1
    assert content["caution_text"] == "보관할 문구"
    enabled = ctx.client.patch(
        f"/api/contents/{content_id}", json={"caution_enabled": True}, headers=ctx.headers
    )
    assert enabled.status_code == 200
    invalid = ctx.client.patch(
        f"/api/contents/{content_id}",
        json={"caution_text": None, "title": "취소"},
        headers=ctx.headers,
    )
    assert invalid.status_code == 422
    assert editor(ctx, content_id).json()["detail"]["content"]["title"] == "수정"
    cleared = ctx.client.patch(
        f"/api/contents/{content_id}",
        json={
            "source": None,
            "category_id": None,
            "tag_ids": [],
            "caution_enabled": False,
            "caution_text": None,
        },
        headers=ctx.headers,
    )
    assert cleared.status_code == 200, cleared.text
    body = cleared.json()["detail"]
    assert body["source"] is None and body["content"]["category"] is None
    assert body["content"]["tags"] == [] and body["caution_text"] is None


@pytest.mark.parametrize("name", ["가", "가" * 80])
def test_existing_tag_names_remain_readable_and_attachable(context, name):
    ctx = context
    with ctx.factory() as session, session.begin():
        tag = Tag(name=name)
        session.add(tag)
        session.flush()
        tag_id = tag.tag_id
    expected = {"tag_id": tag_id, "name": name}
    assert expected in ctx.client.get("/api/tags").json()["items"]
    content_id = draft(ctx, tag_ids=[tag_id])
    assert editor(ctx, content_id).json()["detail"]["content"]["tags"] == [expected]
    updated = ctx.client.patch(
        f"/api/contents/{content_id}", json={"tag_ids": [tag_id]}, headers=ctx.headers
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["detail"]["content"]["tags"] == [expected]


@pytest.mark.parametrize(
    "change,code",
    [
        ({"title": None}, "PUBLISH_REQUIREMENTS_MISSING"),
        ({"tag_ids": []}, "PUBLISH_REQUIREMENTS_MISSING"),
        ({"category_id": None}, "PUBLISH_REQUIREMENTS_MISSING"),
        ({"source": None}, "PUBLISH_REQUIREMENTS_MISSING"),
        ({"category_id": 999}, "CATEGORY_NOT_FOUND"),
        ({"tag_ids": [999]}, "TAG_NOT_FOUND"),
        ({"caution_enabled": True}, "VALIDATION_ERROR"),
    ],
)
def test_invalid_published_edits_are_atomic(context, change, code):
    ctx = context
    content_id = published(ctx)
    before = editor(ctx, content_id).json()
    response = ctx.client.patch(
        f"/api/contents/{content_id}",
        json={**change, "core_content": "취소할 변경"},
        headers=ctx.headers,
    )
    assert response.status_code in (404, 422), response.text
    assert response.json()["detail"]["code"] == code
    assert editor(ctx, content_id).json() == before


def test_role_visibility_and_personal_target_rules(context):
    ctx = context
    draft_id, public_id = draft(ctx), published(ctx)
    learner = {"X-Actor-Id": str(ctx.ids["learner"])}
    listing = ctx.client.get("/api/contents", headers=learner)
    assert listing.status_code == 200, listing.text
    assert [i["content_id"] for i in listing.json()["items"]] == [public_id]
    assert ctx.client.get("/api/contents?status=ALL", headers=learner).status_code == 403
    assert ctx.client.get(f"/api/contents/{draft_id}", headers=learner).status_code == 404
    assert (
        ctx.client.get(f"/api/contents/{draft_id}?view=editor", headers=learner).status_code == 403
    )
    assert ctx.client.get(f"/api/contents/{draft_id}", headers=ctx.headers).status_code == 404
    for path in ["/api/contents", f"/api/contents/{public_id}"]:
        assert (
            ctx.client.get(path + f"?user_id={ctx.ids['other']}", headers=learner).status_code
            == 404
        )
        assert ctx.client.get(path + "?user_id=999", headers=ctx.headers).status_code == 404
        assert ctx.client.get(path, headers={"X-Actor-Id": "999"}).status_code == 404
    assert (
        ctx.client.patch(
            f"/api/contents/{public_id}", json={"title": "금지"}, headers=learner
        ).status_code
        == 403
    )
    assert ctx.client.post(f"/api/contents/{draft_id}/publish", headers=learner).status_code == 403
    assert (
        ctx.client.get(
            f"/api/contents/{draft_id}/video?preview=true&actor_id={ctx.ids['learner']}"
        ).status_code
        == 403
    )
    listing = ctx.client.get("/api/contents", headers=ctx.headers).json()
    assert listing["total"] == 2
    assert all(item["liked"] is None for item in listing["items"])


def test_search_priority_literal_wildcards_and_pagination(context):
    ctx = context
    core = draft(ctx, core_content="sql_100% 핵심")
    tagged = draft(ctx, tag_ids=[ctx.ids["tags"][1]])
    titled = draft(ctx, title="SQL_100% 제목")
    draft(ctx, title="sqlX1000")
    response = ctx.client.get(
        "/api/contents", params={"q": " sql_100% ", "size": 2}, headers=ctx.headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 3 and response.json()["has_next"] is True
    assert [item["content_id"] for item in response.json()["items"]] == [titled, tagged]
    last = ctx.client.get(
        "/api/contents", params={"q": "sql_100%", "size": 2, "page": 2}, headers=ctx.headers
    ).json()
    assert [item["content_id"] for item in last["items"]] == [core]
    assert last["has_next"] is False
    beyond = ctx.client.get("/api/contents?page=99", headers=ctx.headers).json()
    assert beyond["items"] == [] and beyond["total"] == 4
    assert ctx.client.get("/api/contents?category_id=999", headers=ctx.headers).status_code == 404


def test_counts_personal_state_quiz_and_related_curriculums(context):
    ctx = context
    content_id = published(ctx)
    with ctx.factory() as session, session.begin():
        session.execute(
            content_metrics.insert().values(content_id=content_id, view_count=7, like_count=2)
        )
        session.execute(
            content_likes.insert().values(
                user_id=ctx.ids["learner"], content_id=content_id, learning_epoch=1
            )
        )
        session.execute(
            saved_contents.insert().values(
                user_id=ctx.ids["learner"], content_id=content_id, learning_epoch=1
            )
        )
        session.execute(
            watch_records.insert().values(
                user_id=ctx.ids["learner"], content_id=content_id, completed_at=datetime.now(UTC)
            )
        )
        session.execute(quizzes.insert().values(content_id=content_id, current_version_id=5))
        session.execute(curricula.insert().values(curriculum_id=3, title="연결 과정"))
        session.execute(curriculum_items.insert().values(curriculum_id=3, content_id=content_id))
    result = ctx.client.get(
        f"/api/contents/{content_id}", headers={"X-Actor-Id": str(ctx.ids["learner"])}
    ).json()
    summary = result["content"]
    assert (summary["view_count"], summary["like_count"]) == (7, 2)
    assert all(
        summary[field] is True for field in ("liked", "saved", "watch_completed", "has_quiz")
    )
    assert result["related_curriculums"] == [{"curriculum_id": 3, "title": "연결 과정"}]
    target = ctx.client.get(
        f"/api/contents/{content_id}?user_id={ctx.ids['learner']}", headers=ctx.headers
    ).json()
    assert target["content"]["liked"] is True
    other = ctx.client.get(
        f"/api/contents/{content_id}", headers={"X-Actor-Id": str(ctx.ids["other"])}
    ).json()
    assert other["content"]["liked"] is False
    assert other["content"]["like_count"] == 2
    assert target["content"]["saved"] is True
    other = ctx.client.get(
        f"/api/contents/{content_id}", headers={"X-Actor-Id": str(ctx.ids["other"])}
    ).json()
    assert other["content"]["saved"] is False
    with ctx.factory() as session, session.begin():
        session.execute(saved_contents.delete().where(saved_contents.c.content_id == content_id))
    after = ctx.client.get(
        f"/api/contents/{content_id}", headers={"X-Actor-Id": str(ctx.ids["learner"])}
    ).json()
    assert after["content"]["saved"] is False
    assert after["content"]["liked"] is True


@pytest.mark.parametrize(
    "header,status,start,end",
    [
        (None, 200, 0, None),
        ("bytes=0-0", 206, 0, 1),
        ("bytes=2-5", 206, 2, 6),
        ("bytes=5-", 206, 5, None),
        ("bytes=-4", 206, -4, None),
        ("bytes=-9999", 206, 0, None),
        ("bytes=0-9999", 206, 0, None),
        ("bytes=0-1,3-4", 200, 0, None),
    ],
)
def test_video_binary_and_range_headers(context, header, status, start, end):
    ctx = context
    content_id = published(ctx)
    headers = {"Range": header} if header else {}
    response = ctx.client.get(f"/api/contents/{content_id}/video", headers=headers)
    assert response.status_code == status, response.text
    assert response.content == b"original-video"[start:end]
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "no-store"
    assert int(response.headers["content-length"]) == len(response.content)
    if status == 206:
        actual_start = start if start >= 0 else len(b"original-video") + start
        actual_end = (end - 1) if end else len(b"original-video") - 1
        assert response.headers["content-range"] == f"bytes {actual_start}-{actual_end}/14"
    else:
        assert "content-range" not in response.headers


@pytest.mark.parametrize(
    "header", ["bytes=14-", "bytes=9-2", "bytes=-0", "bytes=-", "items=0-1", "garbage", "bytes=x-y"]
)
def test_invalid_range_returns_structured_416(context, header):
    ctx = context
    content_id = published(ctx)
    response = ctx.client.get(f"/api/contents/{content_id}/video", headers={"Range": header})
    assert response.status_code == 416, response.text
    assert response.headers["content-range"] == "bytes */14"
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["code"] == "RANGE_NOT_SATISFIABLE"


@pytest.mark.parametrize(
    "path",
    [
        "../outside.mp4",
        "/tmp/outside.mp4",
        "C:/outside.mp4",
        "..\\outside.mp4",
        "missing.mp4",
        "symlink.mp4",
    ],
)
def test_video_missing_or_unsafe_path_is_404(context, path, tmp_path):
    ctx = context
    content_id = published(ctx)
    if path == "symlink.mp4":
        outside = tmp_path / "outside.mp4"
        outside.write_bytes(b"secret")
        (ctx.root / path).symlink_to(outside)
    with ctx.factory() as session, session.begin():
        asset = session.get(VideoAsset, session.get(Content, content_id).video_asset_id)
        asset.storage_path = path
    response = ctx.client.get(f"/api/contents/{content_id}/video")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "VIDEO_NOT_FOUND"
    assert "secret" not in response.text


def test_publish_requires_actual_file_and_preserves_draft(context):
    ctx = context
    content_id = draft(ctx, complete=True)
    assert upload(ctx, content_id).status_code == 200
    next(ctx.root.iterdir()).unlink()
    response = ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == [
        {"field": "video", "reason": "required_for_publish"}
    ]
    assert editor(ctx, content_id).json()["detail"]["content"]["status"] == "DRAFT"


@pytest.mark.parametrize("public", [False, True])
def test_replacement_requires_current_revision_and_removes_old_file(context, public):
    ctx = context
    content_id = published(ctx) if public else draft(ctx)
    if not public:
        assert upload(ctx, content_id).status_code == 200
    before = editor(ctx, content_id).json()
    revision = before["detail"]["content"]["media_revision"]
    old_path = next(ctx.root.iterdir())
    assert upload(ctx, content_id, b"wrong", "stale-revision").status_code == 409
    assert old_path.read_bytes() == b"original-video"
    assert upload(ctx, content_id, b"new-video", revision).status_code == 200
    after = editor(ctx, content_id).json()
    assert after["detail"]["content"]["media_revision"] != revision
    assert after["detail"]["published_at"] == before["detail"]["published_at"]
    assert after["detail"]["content"]["status"] == before["detail"]["content"]["status"]
    assert not old_path.exists()
    assert [p.read_bytes() for p in ctx.root.iterdir()] == [b"new-video"]
    assert ctx.client.get(before["detail"]["content"]["video_url"]).status_code == 409
    assert ctx.client.get(after["detail"]["content"]["video_url"]).content == b"new-video"
    with ctx.factory() as session:
        # 이전 방문 등이 참조할 수 있으므로 이전 자산 메타데이터는 보존한다.
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 2


@pytest.mark.parametrize("public", [False, True])
def test_other_replacement_completed_during_processing_keeps_winner(
    context, monkeypatch, stub_video_ingest, public
):
    ctx = context
    content_id = published(ctx) if public else draft(ctx)
    if not public:
        assert upload(ctx, content_id).status_code == 200
    before = editor(ctx, content_id).json()
    revision = before["detail"]["content"]["media_revision"]

    class InterleavedIngest(stub_video_ingest):
        def ingest(self, src, original_name):
            result = super().ingest(src, original_name)
            monkeypatch.setitem(
                main.app.dependency_overrides, get_video_ingest_service, stub_video_ingest
            )
            winner = upload(ctx, content_id, b"winner", revision)
            assert winner.status_code == 200, winner.text
            return result

    monkeypatch.setitem(main.app.dependency_overrides, get_video_ingest_service, InterleavedIngest)
    response = upload(ctx, content_id, b"loser", revision)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "VIDEO_CHANGED"
    assert [path.read_bytes() for path in ctx.root.iterdir()] == [b"winner"]
    after = editor(ctx, content_id).json()
    assert after["detail"]["published_at"] == before["detail"]["published_at"]
    assert after["detail"]["content"]["status"] == before["detail"]["content"]["status"]
    with ctx.factory() as session:
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 2


def test_active_playback_survives_replacement(context):
    ctx = context
    content_id = published(ctx)
    revision = editor(ctx, content_id).json()["detail"]["content"]["media_revision"]
    old_path = next(ctx.root.iterdir())
    with ctx.factory() as session:
        stream = video_service.get_video(
            session, content_id, VideoQuery(), LocalVideoStorage(ctx.root), None
        )
    try:
        assert upload(ctx, content_id, b"new-video", revision).status_code == 200
        assert not old_path.exists()
        assert b"".join(stream.chunks()) == b"original-video"
    finally:
        stream.close()
    assert [path.read_bytes() for path in ctx.root.iterdir()] == [b"new-video"]


@pytest.mark.parametrize("failure", ["inspection", "after_flush", "commit"])
def test_failed_replacement_keeps_old_connection_and_file(context, monkeypatch, failure):
    ctx = context
    content_id = published(ctx)
    before = editor(ctx, content_id).json()
    revision = before["detail"]["content"]["media_revision"]
    old_path = next(ctx.root.iterdir())
    original_attach = repository.attach_video
    attempted = []
    commit_failures = []

    def attach_then_fail(session, content, asset):
        original_attach(session, content, asset)
        new_path = ctx.root / asset.storage_path
        assert new_path.is_file() and old_path.is_file()
        attempted.append((asset.video_asset_id, new_path))
        if failure == "after_flush":
            raise SQLAlchemyError("private database failure")

    def fail_commit(session):
        if attempted:
            asset_id, new_path = attempted[0]
            assert new_path.is_file() and old_path.is_file()
            assert session.get(Content, content_id).video_asset_id == asset_id
            commit_failures.append(asset_id)
            raise SQLAlchemyError("private commit failure")

    if failure == "inspection":
        # 실제 데이터 처리: 영상이 아닌 바이트는 시그니처 판별에서 415로 거절된다.
        monkeypatch.delitem(main.app.dependency_overrides, get_video_ingest_service)
    else:
        monkeypatch.setattr(repository, "attach_video", attach_then_fail)
        if failure == "commit":
            event.listen(Session, "before_commit", fail_commit)
    try:
        response = upload(ctx, content_id, b"invalid or new file", revision)
    finally:
        if failure == "commit":
            event.remove(Session, "before_commit", fail_commit)
    assert len(attempted) == (0 if failure == "inspection" else 1)
    if failure == "commit":
        assert commit_failures == [attempted[0][0]]
    assert response.status_code == (415 if failure == "inspection" else 500), response.text
    assert "private" not in response.text
    assert editor(ctx, content_id).json() == before
    assert list(ctx.root.iterdir()) == [old_path] and old_path.read_bytes() == b"original-video"
    with ctx.factory() as session:
        assert session.scalar(select(func.count()).select_from(VideoAsset)) == 1


@pytest.mark.parametrize("operation", ["patch", "publish"])
def test_edit_and_publish_commit_failure_rolls_back(context, operation):
    ctx = context
    content_id = draft(ctx, complete=True)
    assert upload(ctx, content_id).status_code == 200
    before = editor(ctx, content_id).json()

    def fail_commit(*args, **kwargs):
        raise SQLAlchemyError("private commit failure")

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = (
            ctx.client.patch(
                f"/api/contents/{content_id}",
                json={"title": "취소", "tag_ids": ctx.ids["tags"][1:]},
                headers=ctx.headers,
            )
            if operation == "patch"
            else ctx.client.post(f"/api/contents/{content_id}/publish", headers=ctx.headers)
        )
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 500
    assert editor(ctx, content_id).json() == before
    with ctx.factory() as session:
        assert session.scalar(select(func.count()).select_from(ContentTag)) == 1


def test_not_found_and_revision_without_existing_video(context):
    ctx = context
    for method, path, kwargs in [
        ("GET", "/api/contents/999?view=editor", {}),
        ("PATCH", "/api/contents/999", {"json": {"title": "없음"}}),
        ("POST", "/api/contents/999/publish", {}),
        ("GET", "/api/contents/999/video", {}),
    ]:
        assert ctx.client.request(method, path, headers=ctx.headers, **kwargs).status_code == 404
    content_id = draft(ctx)
    assert upload(ctx, content_id, revision="stale").status_code == 409
    assert (
        ctx.client.get(
            f"/api/contents/{content_id}/video?preview=true&actor_id={ctx.ids['admin']}"
        ).status_code
        == 404
    )
