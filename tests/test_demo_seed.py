# 임시 개발·데모 seed 전용 검증. demo_seeds/seed.sql을 제거할 때 함께 제거한다.
import json
import os
from contextlib import contextmanager
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.core.config import PROJECT_ROOT, get_settings

demo_injection = pytest.importorskip(
    "demo_seeds.demo_injection",
    reason="데모 전용 검증에는 demo_seeds 폴더를 /app/demo_seeds에 마운트해야 합니다.",
)

POSTGRES_URL = get_settings().database_url if os.getenv("SASU_TEST_SEED_POSTGRES") == "1" else None


@pytest.fixture
def seed_sql():
    return (PROJECT_ROOT / "demo_seeds/seed.sql").read_text()


def snapshot(connection):
    names = connection.scalars(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'sasu' ORDER BY tablename")
    ).all()
    quote = connection.dialect.identifier_preparer.quote
    result = {
        name: connection.scalar(
            text(
                "SELECT md5(COALESCE(jsonb_agg(to_jsonb(r) ORDER BY "
                f"to_jsonb(r)::text)::text, '[]')) FROM sasu.{quote(name)} r"
            )
        )
        for name in names
    }
    result["revision"] = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return result


@pytest.fixture
def database():
    if POSTGRES_URL is None:
        pytest.skip("기존 Docker DB 검증에는 SASU_TEST_SEED_POSTGRES=1 필요")
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as connection:
            before = snapshot(connection)
            connection.rollback()
            transaction = connection.begin()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(2026102901)"))
                quote = connection.dialect.identifier_preparer.quote
                tables = [f"sasu.{quote(name)}" for name in before if name != "revision"]
                connection.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY"))
                yield connection
            finally:
                transaction.rollback()
            assert snapshot(connection) == before, "seed 검증이 기존 DB 기록을 변경했습니다."
    finally:
        engine.dispose()


def apply_seed(connection, sql):
    connection.exec_driver_sql(sql, execution_options={"no_parameters": True})
    connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.fixture
def seed_engine(database):
    class TransactionEngine:
        @contextmanager
        def begin(self):
            with database.begin_nested():
                yield database

    return TransactionEngine()


def test_schema_migration_does_not_insert_demo_data(database):
    database.execute(text("DROP SCHEMA sasu CASCADE"))
    database.execute(text("DELETE FROM alembic_version"))
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["connection"] = database
    command.upgrade(config, "head")
    assert database.scalar(text("SELECT version_num FROM alembic_version")) == "0001_initial_schema"
    names = database.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='sasu'")).all()
    assert len(names) == 21
    for name in names:
        assert database.scalar(text(f"SELECT count(*) FROM sasu.{name}")) == 0


def test_empty_tables_receive_complete_demo_without_changing_schema_revision(database, seed_sql):
    revision = database.scalar(text("SELECT version_num FROM alembic_version"))
    apply_seed(database, seed_sql)
    expected = {
        "app_users": 3,
        "user_settings": 2,
        "categories": 16,
        "tags": 43,
        "contents": 25,
        "video_assets": 25,
        "content_tags": 75,
        "quizzes": 25,
        "quiz_versions": 28,
        "quiz_options": 84,
        "curricula": 6,
        "curriculum_items": 25,
        "user_interests": 2,
        "watch_visits": 18,
        "watch_records": 18,
        "content_likes": 8,
        "saved_contents": 8,
        "quiz_attempts": 22,
        "quiz_responses": 21,
        "wrong_answers": 7,
        "learning_events": 42,
    }
    for name in snapshot(database):
        if name != "revision":
            assert database.scalar(text(f"SELECT count(*) FROM sasu.{name}")) == expected.get(
                name, 0
            )
    assert database.scalar(text("SELECT version_num FROM alembic_version")) == revision
    assert (
        database.scalar(text("SELECT count(*) FROM sasu.contents WHERE status = 'PUBLISHED'")) == 25
    )
    assert (
        database.scalar(text("SELECT count(*) FROM sasu.contents WHERE source LIKE '%가상 출처%'"))
        == 10
    )
    assert database.execute(
        text(
            "SELECT u.username, s.onboarding_status, s.review_interval, s.learning_epoch "
            "FROM sasu.user_settings s JOIN sasu.app_users u USING (user_id) "
            "WHERE u.username = 'user1'"
        )
    ).one() == ("user1", "PENDING", 5, 1)


@pytest.mark.parametrize("has_settings", [False, True])
def test_existing_identity_names_and_settings_are_reused(database, seed_sql, has_settings):
    database.execute(
        text(
            "INSERT INTO sasu.app_users (user_id, username, display_name, role) "
            "OVERRIDING SYSTEM VALUE VALUES (42, 'user1', '기존 이름', 'LEARNER')"
        )
    )
    database.execute(
        text(
            "INSERT INTO sasu.categories (category_id, name, group_name, sort_order) "
            "OVERRIDING SYSTEM VALUE VALUES (42, '문서·OA', '기존 그룹', 99)"
        )
    )
    if has_settings:
        database.execute(
            text(
                "INSERT INTO sasu.user_settings (user_id, review_interval, learning_epoch) "
                "VALUES (42, 12, 7)"
            )
        )
    before = database.execute(text("SELECT * FROM sasu.categories WHERE category_id = 42")).one()
    apply_seed(database, seed_sql)
    assert (
        database.execute(text("SELECT * FROM sasu.categories WHERE category_id = 42")).one()
        == before
    )
    assert (
        database.scalar(text("SELECT display_name FROM sasu.app_users WHERE user_id = 42"))
        == "기존 이름"
    )
    assert database.execute(
        text("SELECT review_interval, learning_epoch FROM sasu.user_settings WHERE user_id = 42")
    ).one() == ((12, 7) if has_settings else (5, 1))
    assert database.scalar(text("SELECT count(*) FROM sasu.contents WHERE category_id = 42")) == 5


def test_repeat_preserves_modified_content_category_and_settings(database, seed_sql):
    apply_seed(database, seed_sql)
    database.execute(
        text("UPDATE sasu.contents SET title = '사용자가 수정한 제목' WHERE content_id = 1")
    )
    database.execute(text("UPDATE sasu.categories SET name = '수정한 분야' WHERE name = '문서·OA'"))
    database.execute(text("UPDATE sasu.user_settings SET review_interval = 9, learning_epoch = 3"))
    database.execute(
        text("UPDATE sasu.curricula SET title = '사용자가 수정한 시리즈' WHERE curriculum_id = 1")
    )
    before = snapshot(database)
    apply_seed(database, seed_sql)
    apply_seed(database, seed_sql)
    assert snapshot(database) == before


def content_only_sql(sql):
    parts = sql.split("$sasu_demo_data$")
    data = json.loads(parts[1])
    for key in ("quizzes", "curricula", "learning_demo"):
        data.pop(key, None)
    parts[1] = json.dumps(data, ensure_ascii=False)
    return "$sasu_demo_data$".join(parts)


def test_existing_content_demo_can_be_enriched_without_overwriting_base(database, seed_sql):
    apply_seed(database, content_only_sql(seed_sql))
    database.execute(text("UPDATE sasu.user_settings SET review_interval = 11 WHERE user_id = 2"))
    database.execute(
        text("UPDATE sasu.categories SET name = '분야 이름 변경' WHERE name = '문서·OA'")
    )
    before = snapshot(database)
    apply_seed(database, seed_sql)
    after = snapshot(database)
    for table in ("contents", "video_assets", "categories", "tags", "content_tags"):
        assert after[table] == before[table]
    assert (
        database.scalar(text("SELECT review_interval FROM sasu.user_settings WHERE user_id = 2"))
        == 11
    )
    assert database.scalar(text("SELECT count(*) FROM sasu.quizzes")) == 25
    assert database.scalar(text("SELECT count(*) FROM sasu.curricula")) == 6


def test_seed_preserves_existing_question_and_series_during_enrichment(database, seed_sql):
    apply_seed(database, content_only_sql(seed_sql))
    database.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    quiz = database.scalar(text("INSERT INTO sasu.quizzes(content_id) VALUES(1) RETURNING quiz_id"))
    version = database.scalar(
        text(
            "INSERT INTO sasu.quiz_versions(quiz_id, version_no, question_type, "
            "question_text, explanation) VALUES(:quiz, 1, 'OX', "
            "'기존 관리자가 작성한 문항', '기존 해설') RETURNING quiz_version_id"
        ),
        {"quiz": quiz},
    )
    database.execute(
        text(
            "INSERT INTO sasu.quiz_options(quiz_version_id, position, option_text, is_correct) "
            "VALUES(:version, 1, 'O', true), (:version, 2, 'X', false)"
        ),
        {"version": version},
    )
    database.execute(
        text("UPDATE sasu.quizzes SET current_version_id=:version WHERE quiz_id=:quiz"),
        {"version": version, "quiz": quiz},
    )
    title = json.loads(seed_sql.split("$sasu_demo_data$")[1])["curricula"][0]["title"]
    series = database.scalar(
        text(
            "INSERT INTO sasu.curricula(title, description) "
            "VALUES(:title, '기존 설명') RETURNING curriculum_id"
        ),
        {"title": title},
    )
    apply_seed(database, seed_sql)
    assert (
        database.scalar(
            text("SELECT current_version_id FROM sasu.quizzes WHERE quiz_id=:quiz"), {"quiz": quiz}
        )
        == version
    )
    assert (
        database.scalar(
            text("SELECT count(*) FROM sasu.quiz_versions WHERE quiz_id=:quiz"), {"quiz": quiz}
        )
        == 1
    )
    assert (
        database.scalar(
            text("SELECT description FROM sasu.curricula WHERE curriculum_id=:series"),
            {"series": series},
        )
        == "기존 설명"
    )
    assert (
        database.scalar(
            text("SELECT count(*) FROM sasu.curriculum_items WHERE curriculum_id=:series"),
            {"series": series},
        )
        == 0
    )


def test_demo_reset_is_not_undone_by_seed_rerun(database, seed_sql):
    apply_seed(database, seed_sql)
    user_id = database.scalar(
        text("SELECT user_id FROM sasu.app_users WHERE username='demo_dozone'")
    )
    database.execute(text("SELECT sasu.reset_learning(:user_id, 1)"), {"user_id": user_id})
    before = snapshot(database)
    apply_seed(database, seed_sql)
    assert snapshot(database) == before
    assert database.scalar(text("SELECT count(*) FROM sasu.quiz_responses")) == 0


def test_enrichment_failure_rolls_back_profile_questions_and_records(database, seed_sql):
    apply_seed(database, content_only_sql(seed_sql))
    parts = seed_sql.split("$sasu_demo_data$")
    data = json.loads(parts[1])
    data["quizzes"][-1]["versions"][0]["options"][0]["correct"] = False
    parts[1] = json.dumps(data, ensure_ascii=False)
    before = snapshot(database)
    with pytest.raises(DBAPIError), database.begin_nested():
        apply_seed(database, "$sasu_demo_data$".join(parts))
    assert snapshot(database) == before


def test_learning_examples_have_consistent_results_progress_and_event_counts(database, seed_sql):
    apply_seed(database, seed_sql)
    assert dict(
        database.execute(
            text("SELECT result, count(*) FROM sasu.quiz_responses GROUP BY result")
        ).all()
    ) == {"CORRECT": 9, "WRONG": 8, "SKIPPED": 4}
    assert dict(
        database.execute(
            text("SELECT status, count(*) FROM sasu.wrong_answers GROUP BY status")
        ).all()
    ) == {"UNRESOLVED": 6, "RESOLVED": 1}
    assert database.scalar(text("SELECT max(wrong_count) FROM sasu.wrong_answers")) == 2
    assert (
        database.scalar(
            text("SELECT count(*) FROM sasu.watch_records WHERE completed_at IS NOT NULL")
        )
        == 13
    )
    assert dict(
        database.execute(
            text("SELECT event_type, count(*) FROM sasu.learning_events GROUP BY event_type")
        ).all()
    ) == {"QUIZ_DISPLAYED": 22, "CARD_OPENED": 12, "CARD_REVEALED": 8}
    assert (
        database.scalar(
            text(
                "SELECT count(*) FROM sasu.watch_records w JOIN sasu.app_users u USING(user_id) "
                "WHERE u.username='user1'"
            )
        )
        == 0
    )


@pytest.mark.parametrize("conflict", ["role", "category", "tag"])
def test_conflict_rolls_back_entire_insert(database, seed_sql, conflict):
    if conflict == "role":
        database.execute(
            text(
                "INSERT INTO sasu.app_users (username, display_name, role) "
                "VALUES ('user1', '기존 관리자', 'ADMIN')"
            )
        )
    else:
        table, name = ("categories", "엑셀") if conflict == "category" else ("tags", "엑셀")
        database.execute(
            text(f"INSERT INTO sasu.{table} (name) VALUES (:name), (:name)"), {"name": name}
        )
    before = snapshot(database)
    with pytest.raises(DBAPIError) as error, database.begin_nested():
        apply_seed(database, seed_sql)
    assert "데모 seed 중단" in str(error.value.orig)
    assert snapshot(database) == before


def test_partial_dataset_is_rejected_without_repair_or_overwrite(database, seed_sql):
    item = json.loads(seed_sql.split("$sasu_demo_data$")[1])["contents"][0]
    database.execute(
        text(
            "INSERT INTO sasu.video_assets "
            "(video_asset_id, storage_path, original_name, mime_type, "
            "size_bytes, duration_seconds) "
            "VALUES (:video_asset_id, :storage_path, :original_name, 'video/mp4', "
            ":size_bytes, :duration_seconds)"
        ),
        item,
    )
    before = snapshot(database)
    with pytest.raises(DBAPIError) as error, database.begin_nested():
        apply_seed(database, seed_sql)
    assert "1/25개만" in str(error.value.orig)
    assert snapshot(database) == before


def test_original_video_bundle_is_copied_and_connected_atomically(
    database, seed_sql, tmp_path, seed_engine
):
    bundle = PROJECT_ROOT / "demo_seeds"
    if not list((bundle / "videos").glob("*.mp4")):
        pytest.skip("원본 영상 묶음을 준비한 경우에만 복사·DB 연결을 검증")

    server = tmp_path / "server-videos"
    assert demo_injection.apply_demo_seed(seed_engine, bundle, server) == 25
    database.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    assert database.scalar(text("SELECT count(*) FROM sasu.contents")) == 25
    assert demo_injection.apply_demo_seed(seed_engine, bundle, server) == 0
    for item in json.loads(seed_sql.split("$sasu_demo_data$")[1])["contents"]:
        path = server / item["storage_path"]
        assert path.stat().st_size == item["size_bytes"]
        assert demo_injection.file_digest(path) == item["sha256"]


def stored_video_files(database, server):
    rows = database.execute(
        text("SELECT storage_path, size_bytes FROM sasu.video_assets ORDER BY storage_path")
    ).mappings().all()
    for row in rows:
        path = server / row["storage_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.truncate(row["size_bytes"])
    return rows


@pytest.mark.parametrize("state", ["missing", "wrong_size"])
def test_invalid_current_video_rolls_back_learning_enrichment(
    database, seed_sql, tmp_path, seed_engine, state
):
    apply_seed(database, content_only_sql(seed_sql))
    server = tmp_path / "server"
    rows = stored_video_files(database, server)
    broken = server / rows[0]["storage_path"]
    broken.unlink()
    if state == "wrong_size":
        broken.write_bytes(b"truncated")
    before = snapshot(database)
    with pytest.raises(RuntimeError, match="서버 영상 확인 실패"):
        demo_injection.apply_demo_seed(seed_engine, PROJECT_ROOT / "demo_seeds", server)
    assert snapshot(database) == before
    assert database.scalar(text("SELECT count(*) FROM sasu.quizzes")) == 0
    if state == "missing":
        assert not broken.exists()
    else:
        assert broken.read_bytes() == b"truncated"


def test_replaced_video_uses_current_database_metadata_and_ignores_old_asset(
    database, seed_sql, tmp_path, seed_engine
):
    apply_seed(database, seed_sql)
    server = tmp_path / "server"
    stored_video_files(database, server)
    old = database.execute(
        text(
            "SELECT c.content_id, a.* FROM sasu.contents c "
            "JOIN sasu.video_assets a USING(video_asset_id) ORDER BY c.content_id LIMIT 1"
        )
    ).mappings().one()
    replacement_id = uuid4()
    new_path = server / "replacement.mp4"
    new_path.write_bytes(b"new media")
    database.execute(
        text(
            "INSERT INTO sasu.video_assets "
            "(video_asset_id, storage_path, original_name, mime_type, "
            "size_bytes, duration_seconds) "
            "VALUES (:id, 'replacement.mp4', 'new.mp4', 'video/mp4', 9, 5)"
        ),
        {"id": replacement_id},
    )
    database.execute(
        text("UPDATE sasu.contents SET video_asset_id=:asset WHERE content_id=:content"),
        {"asset": replacement_id, "content": old["content_id"]},
    )
    old_path = server / old["storage_path"]
    old_path.unlink()
    before = snapshot(database)
    assert demo_injection.apply_demo_seed(seed_engine, PROJECT_ROOT / "demo_seeds", server) == 0
    assert snapshot(database) == before
    assert new_path.read_bytes() == b"new media"
    assert not old_path.exists()
