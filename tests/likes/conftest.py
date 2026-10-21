import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import main
from app.core.config import get_settings
from app.db.session import get_db

POSTGRES_URL = get_settings().database_url if os.getenv("SASU_TEST_LIKES_POSTGRES") == "1" else None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setitem(main.app.dependency_overrides, get_db, lambda: None)
    with_client = TestClient(main.app)
    try:
        yield with_client
    finally:
        with_client.close()


def _snapshot(engine):
    with engine.connect() as connection:
        names = connection.scalars(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'sasu' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
        ).all()
        return {
            name: connection.scalar(
                text(
                    "SELECT md5(COALESCE(jsonb_agg(to_jsonb(rows) "
                    "ORDER BY to_jsonb(rows)::text)::text, '[]')) "
                    f"FROM sasu.{engine.dialect.identifier_preparer.quote(name)} rows"
                )
            )
            for name in names
        }


@pytest.fixture(scope="module")
def postgres_engine():
    if POSTGRES_URL is None:
        pytest.skip("기존 Docker DB 검증에는 SASU_TEST_LIKES_POSTGRES=1 필요")
    engine = create_engine(POSTGRES_URL)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('sasu.content_metrics')"))
    baseline = _snapshot(engine)
    try:
        yield engine
    finally:
        try:
            assert _snapshot(engine) == baseline, "좋아요 테스트가 기존 DB 기록을 변경했습니다."
        finally:
            engine.dispose()


def _create_records(connection):
    prefix = f"like_{uuid4().hex[:12]}"
    ids = {}
    for name, role in (
        ("admin", "ADMIN"),
        ("learner", "LEARNER"),
        ("other", "LEARNER"),
        ("no_settings", "LEARNER"),
    ):
        ids[name] = connection.scalar(
            text(
                """
                INSERT INTO sasu.app_users (username, display_name, role)
                VALUES (:username, :name, :role) RETURNING user_id
                """
            ),
            {"username": f"{prefix}_{name}", "name": name, "role": role},
        )
    for name in ("learner", "other"):
        connection.execute(
            text("INSERT INTO sasu.user_settings (user_id) VALUES (:user_id)"),
            {"user_id": ids[name]},
        )
    for table, key in (("categories", "category_id"), ("tags", "tag_id")):
        ids[key] = connection.scalar(
            text(f"INSERT INTO sasu.{table} (name) VALUES (:name) RETURNING {key}"),
            {"name": prefix},
        )
    ids["asset"] = uuid4()
    connection.execute(
        text(
            """
            INSERT INTO sasu.video_assets
                (video_asset_id, storage_path, original_name, mime_type,
                 size_bytes, duration_seconds)
            VALUES (:asset, :path, 'like-test.mp4', 'video/mp4', 1, 5)
            """
        ),
        {"asset": ids["asset"], "path": f"{ids['asset'].hex}.mp4"},
    )
    for name in ("published", "draft"):
        ids[name] = connection.scalar(
            text(
                """
                INSERT INTO sasu.contents
                    (title, category_id, created_by_user_id, video_asset_id,
                     core_content, source, reviewed_on)
                VALUES (:title, :category, :admin, :asset, '좋아요 검증', 'test', CURRENT_DATE)
                RETURNING content_id
                """
            ),
            {
                "title": f"{prefix}_{name}",
                "category": ids["category_id"],
                "admin": ids["admin"],
                "asset": ids["asset"] if name == "published" else None,
            },
        )
        connection.execute(
            text("INSERT INTO sasu.content_tags (content_id, tag_id) VALUES (:content, :tag)"),
            {"content": ids[name], "tag": ids["tag_id"]},
        )
    connection.execute(
        text(
            "UPDATE sasu.contents SET status = 'PUBLISHED', published_at = now() "
            "WHERE content_id = :content"
        ),
        {"content": ids["published"]},
    )
    connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    return ids


def _client_context(monkeypatch, engine, ids, connection=None):
    def provide_session():
        with Session(
            bind=connection if connection is not None else engine,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    return SimpleNamespace(
        client=TestClient(main.app, raise_server_exceptions=False),
        engine=engine,
        connection=connection,
        ids=ids,
        path=f"/api/users/{ids['learner']}/contents/{ids['published']}/like",
        headers={"X-Actor-Id": str(ids["learner"]), "X-Record-Generation": "0"},
    )


@pytest.fixture
def context(postgres_engine, monkeypatch):
    # 요청의 커밋은 savepoint에 한정하고, 이 테스트가 만든 행은 마지막에 롤백한다.
    with postgres_engine.connect() as connection, connection.begin() as transaction:
        ids = _create_records(connection)
        ctx = _client_context(monkeypatch, postgres_engine, ids, connection)
        try:
            yield ctx
        finally:
            ctx.client.close()
            transaction.rollback()


@pytest.fixture
def committed_context(postgres_engine, monkeypatch):
    # 두 DB 연결의 실제 잠금 경합에는 서로 볼 수 있는 검증 행이 필요하다.
    # 별도 DB를 만들지 않고 UUID로 구분한 새 행만 커밋한 뒤 정확히 그 행을 정리한다.
    with postgres_engine.begin() as connection:
        ids = _create_records(connection)
    ctx = _client_context(monkeypatch, postgres_engine, ids)
    try:
        yield ctx
    finally:
        ctx.client.close()
        user_ids = [ids[name] for name in ("admin", "learner", "other", "no_settings")]
        content_ids = [ids["published"], ids["draft"]]
        with postgres_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM sasu.content_likes WHERE user_id = ANY(:ids)"),
                {"ids": user_ids},
            )
            connection.execute(
                text("DELETE FROM sasu.user_settings WHERE user_id = ANY(:ids)"),
                {"ids": user_ids},
            )
            connection.execute(
                text("DELETE FROM sasu.content_tags WHERE content_id = ANY(:ids)"),
                {"ids": content_ids},
            )
            connection.execute(
                text("DELETE FROM sasu.contents WHERE content_id = ANY(:ids)"),
                {"ids": content_ids},
            )
            connection.execute(
                text("DELETE FROM sasu.video_assets WHERE video_asset_id = :id"),
                {"id": ids["asset"]},
            )
            connection.execute(
                text("DELETE FROM sasu.tags WHERE tag_id = :id"), {"id": ids["tag_id"]}
            )
            connection.execute(
                text("DELETE FROM sasu.categories WHERE category_id = :id"),
                {"id": ids["category_id"]},
            )
            connection.execute(
                text("DELETE FROM sasu.app_users WHERE user_id = ANY(:ids)"),
                {"ids": user_ids},
            )
