import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import Session

from app import main
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.storage import LocalVideoStorage
from app.modules.categories.models import Category
from app.modules.contents.models import Content, ContentStatus, ContentTag, VideoAsset
from app.modules.saved_contents.tables import saved_contents
from app.modules.tags.models import Tag
from app.modules.users.models import User, UserRole

# 설정 격리 전에 연결 정보를 보관하고, 명시한 경우에만 기존 DB에서 롤백하며 검증한다.
TEST_URL = (
    get_settings().database_url if os.getenv("SASU_TEST_SAVED_CONTENTS_POSTGRES") == "1" else None
)


def _fingerprints(connection):
    tables = connection.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'sasu' ORDER BY tablename")
    )
    result = {}
    for table in tables:
        quoted = connection.dialect.identifier_preparer.quote(table)
        result[table] = tuple(
            connection.scalars(
                text(f"SELECT md5(row_to_json(t)::text) FROM sasu.{quoted} t ORDER BY 1")
            )
        )
    return result


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("기존 Docker DB 검증에는 SASU_TEST_SAVED_CONTENTS_POSTGRES=1 필요")
    engine = create_engine(TEST_URL)
    before = None
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT to_regclass('sasu.saved_contents')"))
            before = _fingerprints(connection)
        yield engine
    finally:
        try:
            if before is not None:
                with engine.connect() as connection:
                    assert _fingerprints(connection) == before, "기존 DB 레코드가 변경되었습니다."
        finally:
            engine.dispose()


def _create_records(session):
    prefix = f"save_test_{uuid4().hex[:12]}"
    admin, learner, other = [
        User(username=f"{prefix}_{name}", display_name=name, role=role)
        for name, role in (
            ("admin", UserRole.ADMIN),
            ("learner", UserRole.LEARNER),
            ("other", UserRole.LEARNER),
        )
    ]
    categories = [Category(name=f"{prefix}_{i}") for i in range(2)]
    tag = Tag(name=prefix)
    session.add_all([admin, learner, other, *categories, tag])
    session.flush()
    for user in (learner, other):
        # 테스트가 생성한 사용자에만 설정 행을 준비한다. 앱의 대체 모델은 만들지 않는다.
        session.execute(
            text("INSERT INTO sasu.user_settings (user_id) VALUES (:user_id)"),
            {"user_id": user.user_id},
        )
    assets = [
        VideoAsset(
            storage_path=f"{uuid4().hex}.mp4",
            original_name="sample.mp4",
            mime_type="video/mp4",
            size_bytes=10,
            duration_seconds=4.5,
        )
        for _ in range(3)
    ]
    session.add_all(assets)
    session.flush()
    contents = [
        Content(
            created_by_user_id=admin.user_id,
            category_id=categories[0 if i < 2 else 1].category_id,
            video_asset_id=asset.video_asset_id,
            title=f"{prefix}_{i}",
            core_content="저장 목록 테스트",
            source="테스트",
            reviewed_on=date(2026, 10, 21),
            status=ContentStatus.PUBLISHED,
            published_at=datetime(2026, 10, 21, tzinfo=UTC),
        )
        for i, asset in enumerate(assets)
    ]
    draft = Content(created_by_user_id=admin.user_id)
    session.add_all([*contents, draft])
    session.flush()
    session.add_all(
        ContentTag(content_id=content.content_id, tag_id=tag.tag_id) for content in contents
    )
    session.flush()
    session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    session.commit()
    return SimpleNamespace(
        session=session,
        admin=admin.user_id,
        learner=learner.user_id,
        other=other.user_id,
        categories=[category.category_id for category in categories],
        contents=[content.content_id for content in contents],
        draft=draft.content_id,
        assets=[asset.video_asset_id for asset in assets],
        tag=tag.tag_id,
    )


@pytest.fixture
def context(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(
                bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
            ) as session:
                yield _create_records(session)
        finally:
            # 요청의 commit도 savepoint에 한정하고 생성 행은 모두 롤백한다.
            transaction.rollback()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(main.app.dependency_overrides, get_db, lambda: None)
    test_client = TestClient(main.app, raise_server_exceptions=False)
    try:
        yield test_client
    finally:
        test_client.close()


def _configure_client(ctx, bind, monkeypatch):
    storage = LocalVideoStorage(get_settings().video_storage_root)
    storage.ensure_root()
    with ctx.session.begin():
        for content_id in ctx.contents:
            content = ctx.session.get(Content, content_id)
            video = ctx.session.get(VideoAsset, content.video_asset_id)
            storage.resolve_path(video.storage_path).write_bytes(b"test-video")

    def provide_session():
        with Session(
            bind=bind,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    ctx.client = TestClient(main.app, raise_server_exceptions=False)
    ctx.path = f"/api/users/{ctx.learner}/contents/{ctx.contents[0]}/saved"
    ctx.list_path = f"/api/users/{ctx.learner}/saved-contents"
    ctx.headers = {"X-Actor-Id": str(ctx.learner), "X-Record-Generation": "0"}
    ctx.storage = storage


@pytest.fixture
def api_context(context, monkeypatch):
    ctx = context
    _configure_client(ctx, ctx.session.get_bind(), monkeypatch)
    try:
        yield ctx
    finally:
        ctx.client.close()


@pytest.fixture
def committed_api_context(postgres_engine, monkeypatch):
    # 실제 두 연결의 경합에만 새 검증 행을 커밋하고, 아래에서 해당 ID만 정리한다.
    with Session(postgres_engine, expire_on_commit=False) as session:
        ctx = _create_records(session)
        try:
            _configure_client(ctx, postgres_engine, monkeypatch)
            ctx.engine = postgres_engine
            yield ctx
        finally:
            if hasattr(ctx, "client"):
                ctx.client.close()
            session.close()
            user_ids = [ctx.admin, ctx.learner, ctx.other]
            content_ids = [*ctx.contents, ctx.draft]
            with postgres_engine.begin() as connection:
                connection.execute(
                    delete(saved_contents).where(saved_contents.c.user_id.in_(user_ids))
                )
                connection.execute(
                    text("DELETE FROM sasu.user_settings WHERE user_id = ANY(:ids)"),
                    {"ids": user_ids},
                )
                connection.execute(delete(ContentTag).where(ContentTag.content_id.in_(content_ids)))
                connection.execute(delete(Content).where(Content.content_id.in_(content_ids)))
                connection.execute(
                    delete(VideoAsset).where(VideoAsset.video_asset_id.in_(ctx.assets))
                )
                connection.execute(delete(Tag).where(Tag.tag_id == ctx.tag))
                connection.execute(delete(Category).where(Category.category_id.in_(ctx.categories)))
                connection.execute(delete(User).where(User.user_id.in_(user_ids)))
