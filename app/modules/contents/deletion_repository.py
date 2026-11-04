"""콘텐츠 한 건에 소유된 데이터만 삭제한다. 공유 분류·태그·시리즈는 보존한다."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.contents.models import Content
from app.modules.curricula.repository import replace_steps


def lock_target(session: Session, content_id: int) -> Content | None:
    return session.scalar(
        select(Content).where(Content.content_id == content_id).with_for_update(nowait=True)
    )


def lock_dependents(session: Session, content_id: int) -> list[int]:
    # 학습 쓰기는 설정 → 콘텐츠, 시리즈 편성은 시리즈 → 콘텐츠 순서다.
    # 역순으로 기다리지 않고 충돌 시 전체 트랜잭션을 취소해 재시도하게 한다.
    session.execute(
        text("""
        SELECT s.user_id FROM sasu.user_settings s
        WHERE s.last_content_id = :id OR s.user_id IN (
            SELECT user_id FROM sasu.watch_records WHERE content_id = :id
            UNION SELECT user_id FROM sasu.watch_visits WHERE content_id = :id
            UNION SELECT user_id FROM sasu.content_likes WHERE content_id = :id
            UNION SELECT user_id FROM sasu.saved_contents WHERE content_id = :id
            UNION SELECT a.user_id FROM sasu.quiz_attempts a
                JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id = :id
            UNION SELECT w.user_id FROM sasu.wrong_answers w
                JOIN sasu.quiz_versions v USING(quiz_version_id)
                JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id = :id
            UNION SELECT e.user_id FROM sasu.learning_events e
                LEFT JOIN sasu.quiz_versions v USING(quiz_version_id)
                LEFT JOIN sasu.quizzes q USING(quiz_id)
                WHERE e.content_id = :id OR q.content_id = :id
        ) ORDER BY s.user_id FOR UPDATE OF s NOWAIT
    """),
        {"id": content_id},
    ).all()
    curricula = list(
        session.scalars(
            text("""
        SELECT c.curriculum_id FROM sasu.curricula c
        WHERE EXISTS (SELECT 1 FROM sasu.curriculum_items i
                      WHERE i.curriculum_id = c.curriculum_id AND i.content_id = :id)
        ORDER BY c.curriculum_id FOR UPDATE OF c NOWAIT
    """),
            {"id": content_id},
        )
    )
    session.execute(
        text("""
        SELECT quiz_id FROM sasu.quizzes WHERE content_id = :id FOR UPDATE NOWAIT
    """),
        {"id": content_id},
    ).all()
    return curricula


def video_asset_ids(session: Session, content: Content) -> list:
    ids = set(
        session.scalars(
            text("SELECT video_asset_id FROM sasu.watch_visits WHERE content_id = :id"),
            {"id": content.content_id},
        )
    )
    if content.video_asset_id:
        ids.add(content.video_asset_id)
    return sorted(ids, key=str)


def delete_records(session: Session, content_id: int, curriculum_ids: list[int]) -> None:
    versions = """SELECT v.quiz_version_id FROM sasu.quiz_versions v
        JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id = :id"""
    attempts = """SELECT a.attempt_id FROM sasu.quiz_attempts a
        JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id = :id"""
    statements = [
        f"""DELETE FROM sasu.learning_events WHERE content_id = :id
            OR quiz_version_id IN ({versions}) OR attempt_id IN ({attempts})""",
        f"DELETE FROM sasu.wrong_answers WHERE quiz_version_id IN ({versions})",
        f"DELETE FROM sasu.quiz_responses WHERE attempt_id IN ({attempts})",
        f"DELETE FROM sasu.quiz_attempts WHERE attempt_id IN ({attempts})",
        "DELETE FROM sasu.watch_visits WHERE content_id = :id",
        "DELETE FROM sasu.watch_records WHERE content_id = :id",
        "DELETE FROM sasu.content_likes WHERE content_id = :id",
        "DELETE FROM sasu.saved_contents WHERE content_id = :id",
        "DELETE FROM sasu.content_tags WHERE content_id = :id",
        "DELETE FROM sasu.curriculum_items WHERE content_id = :id",
        """UPDATE sasu.user_settings SET last_content_id = NULL, updated_at = now()
            WHERE last_content_id = :id""",
    ]
    for statement in statements:
        session.execute(text(statement), {"id": content_id})
    for curriculum_id in curriculum_ids:
        remaining = list(
            session.scalars(
                text("""
            SELECT content_id FROM sasu.curriculum_items
            WHERE curriculum_id = :id ORDER BY position
        """),
                {"id": curriculum_id},
            )
        )
        replace_steps(session, curriculum_id, remaining)


def delete_assets(session: Session, videos: list, thumbnail) -> list[int]:
    jobs = []
    for asset_id in videos:
        path = session.scalar(
            text("""
            DELETE FROM sasu.video_assets v WHERE v.video_asset_id = :id
            AND NOT EXISTS (SELECT 1 FROM sasu.contents c WHERE c.video_asset_id = v.video_asset_id)
            AND NOT EXISTS (SELECT 1 FROM sasu.watch_visits w
                            WHERE w.video_asset_id = v.video_asset_id)
            RETURNING storage_path
        """),
            {"id": asset_id},
        )
        if path:
            jobs.append(_enqueue(session, "video", path))
    if thumbnail:
        path = session.scalar(
            text("""
            DELETE FROM sasu.image_assets a WHERE a.image_asset_id = :id
            AND NOT EXISTS (SELECT 1 FROM sasu.contents c
                            WHERE c.thumbnail_image_id = a.image_asset_id)
            AND NOT EXISTS (SELECT 1 FROM sasu.curricula c
                            WHERE c.thumbnail_image_id = a.image_asset_id)
            RETURNING storage_path
        """),
            {"id": thumbnail},
        )
        if path:
            jobs.append(_enqueue(session, "image", path))
    return jobs


def _enqueue(session: Session, kind: str, path: str) -> int:
    return session.scalar(
        text("""
        INSERT INTO sasu.asset_cleanup_jobs (asset_kind, storage_path) VALUES (:kind, :path)
        ON CONFLICT (asset_kind, storage_path) DO UPDATE SET storage_path = EXCLUDED.storage_path
        RETURNING job_id
    """),
        {"kind": kind, "path": path},
    )
