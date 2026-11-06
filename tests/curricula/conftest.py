import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.modules.categories.models import Category
from app.modules.contents.models import Content, ContentStatus, ContentTag, VideoAsset
from app.modules.tags.models import Tag
from app.modules.users.models import User, UserRole

TEST_URL = get_settings().database_url if os.getenv("SASU_TEST_POSTGRES") == "1" else None


@pytest.fixture(scope="module")
def postgres_engine():
    if TEST_URL is None:
        pytest.skip("기존 Docker DB 검증에는 SASU_TEST_POSTGRES=1 필요")
    engine = create_engine(TEST_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def search_context(postgres_engine, monkeypatch):
    prefix = f"crs_search_{uuid4().hex[:12]}"
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            users = [
                User(username=f"{prefix}_{name}", display_name=name, role=role)
                for name, role in (
                    ("admin", UserRole.ADMIN),
                    ("learner", UserRole.LEARNER),
                    ("other", UserRole.LEARNER),
                )
            ]
            category = Category(name=prefix)
            tag = Tag(name=prefix)
            session.add_all([*users, category, tag])
            session.flush()
            for user in users[1:]:
                session.execute(
                    text("INSERT INTO sasu.user_settings (user_id) VALUES (:id)"),
                    {"id": user.user_id},
                )
            assets = [
                VideoAsset(
                    storage_path=f"{prefix}_{name}.mp4",
                    original_name="sample.mp4",
                    size_bytes=5,
                    mime_type="video/mp4",
                    duration_seconds=10,
                )
                for name in ("available", "missing")
            ]
            session.add_all(assets)
            session.flush()
            contents = [
                Content(
                    title=f"{prefix}_{index}",
                    created_by_user_id=users[0].user_id,
                    video_asset_id=asset.video_asset_id,
                    category_id=category.category_id,
                    core_content="검색 검증",
                    source="테스트",
                    reviewed_on=date(2026, 11, 6),
                    status=ContentStatus.PUBLISHED,
                    published_at=datetime(2026, 11, 6, tzinfo=UTC),
                )
                for index, asset in enumerate(assets)
            ]
            draft = Content(created_by_user_id=users[0].user_id)
            session.add_all([*contents, draft])
            session.flush()
            session.add_all(
                ContentTag(content_id=content.content_id, tag_id=tag.tag_id) for content in contents
            )
            session.flush()
            session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            session.commit()
            root = get_settings().video_storage_root
            root.mkdir(parents=True, exist_ok=True)
            (root / assets[0].storage_path).write_bytes(b"video")
            monkeypatch.setitem(app.dependency_overrides, get_db, lambda: session)
            client = TestClient(app, raise_server_exceptions=False)
            try:
                yield SimpleNamespace(
                    session=session,
                    client=client,
                    prefix=prefix,
                    admin=users[0].user_id,
                    learner=users[1].user_id,
                    other=users[2].user_id,
                    available=contents[0].content_id,
                    missing=contents[1].content_id,
                    draft=draft.content_id,
                )
            finally:
                client.close()
        # API 내부 commit도 savepoint에 한정하며 기존 DB와 검증 레코드를 분리한다.
        transaction.rollback()
