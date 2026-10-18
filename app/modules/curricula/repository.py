"""sasu.curricula/curriculum_items의 자연 키와 기존 학습 기록을 사용한다."""

from sqlalchemy import text
from sqlalchemy.orm import Session


def learner_exists(session: Session, user_id: int) -> bool:
    return bool(
        session.scalar(
            text("""SELECT EXISTS (SELECT 1 FROM sasu.app_users u
                JOIN sasu.user_settings s USING (user_id)
                WHERE u.user_id = :id AND u.role = 'LEARNER')"""),
            {"id": user_id},
        )
    )


def find_curriculum(session: Session, curriculum_id: int, lock: bool = False):
    statement = "SELECT * FROM sasu.curricula WHERE curriculum_id = :id"
    if lock:
        statement += " FOR UPDATE"
    return session.execute(text(statement), {"id": curriculum_id}).mappings().one_or_none()


def list_curricula(session: Session):
    return (
        session.execute(
            text("SELECT * FROM sasu.curricula ORDER BY created_at DESC, curriculum_id")
        )
        .mappings()
        .all()
    )


def create_curriculum(session: Session, title: str, description: str | None) -> int:
    return session.scalar(
        text("""INSERT INTO sasu.curricula (title, description)
                VALUES (:title, :description) RETURNING curriculum_id"""),
        {"title": title, "description": description},
    )


def update_curriculum(session: Session, curriculum_id: int, title: str, description: str | None):
    session.execute(
        text("""UPDATE sasu.curricula SET title = :title, description = :description,
                updated_at = clock_timestamp() WHERE curriculum_id = :id"""),
        {"id": curriculum_id, "title": title, "description": description},
    )


def load_steps(session: Session, curriculum_ids: list[int], user_id: int | None):
    if not curriculum_ids:
        return []
    return (
        session.execute(
            text(
                """
            SELECT i.curriculum_id, i.position, c.content_id, c.title, c.status,
                   c.category_id, category.name AS category_name,
                   asset.video_asset_id, asset.storage_path, asset.duration_seconds,
                   metrics.view_count, metrics.like_count,
                   COALESCE((SELECT jsonb_agg(jsonb_build_object('tag_id', t.tag_id, 'name', t.name)
                                             ORDER BY t.tag_id)
                             FROM sasu.content_tags ct JOIN sasu.tags t USING (tag_id)
                             WHERE ct.content_id = c.content_id), '[]'::jsonb) AS tags,
                   EXISTS(SELECT 1 FROM sasu.quizzes q WHERE q.content_id = c.content_id
                          AND q.current_version_id IS NOT NULL) AS has_quiz,
                   (w.completed_at IS NOT NULL) AS watched,
                   EXISTS(SELECT 1 FROM sasu.content_likes l WHERE l.user_id = :user
                          AND l.content_id = c.content_id) AS liked,
                   EXISTS(SELECT 1 FROM sasu.saved_contents s WHERE s.user_id = :user
                          AND s.content_id = c.content_id) AS saved,
                   EXISTS(SELECT 1 FROM sasu.quizzes q JOIN sasu.quiz_attempts a USING (quiz_id)
                          JOIN sasu.quiz_responses r USING (attempt_id)
                          WHERE q.content_id = c.content_id AND a.user_id = :user
                          AND r.result = 'CORRECT') AS correct
            FROM sasu.curriculum_items i JOIN sasu.contents c USING (content_id)
            JOIN sasu.content_metrics metrics USING (content_id)
            LEFT JOIN sasu.categories category ON category.category_id = c.category_id
            LEFT JOIN sasu.video_assets asset USING (video_asset_id)
            LEFT JOIN sasu.watch_records w ON w.content_id = c.content_id AND w.user_id = :user
            WHERE i.curriculum_id = ANY(CAST(:ids AS bigint[]))
            ORDER BY i.curriculum_id, i.position
            """
            ),
            {"ids": curriculum_ids, "user": user_id},
        )
        .mappings()
        .all()
    )


def lock_contents(session: Session, content_ids: list[int]) -> list[int]:
    return list(
        session.scalars(
            text("""SELECT content_id FROM sasu.contents
                WHERE content_id = ANY(CAST(:ids AS bigint[]))
                ORDER BY content_id FOR KEY SHARE"""),
            {"ids": content_ids},
        )
    )


def replace_steps(session: Session, curriculum_id: int, content_ids: list[int]) -> None:
    maximum = session.scalar(
        text(
            "SELECT coalesce(max(position), 0) FROM sasu.curriculum_items WHERE curriculum_id = :id"
        ),
        {"id": curriculum_id},
    )
    # 최종 순번보다 큰 임시 순번으로 먼저 이동해 UNIQUE 충돌 없이 교환한다.
    offset = max(maximum, len(content_ids)) + 1
    session.execute(
        text("""UPDATE sasu.curriculum_items SET position = position + :offset
                WHERE curriculum_id = :id"""),
        {"offset": offset, "id": curriculum_id},
    )
    session.execute(
        text("""DELETE FROM sasu.curriculum_items WHERE curriculum_id = :id
                AND NOT (content_id = ANY(CAST(:ids AS bigint[])))"""),
        {"id": curriculum_id, "ids": content_ids},
    )
    if content_ids:
        session.execute(
            text("""INSERT INTO sasu.curriculum_items (curriculum_id, content_id, position)
                    VALUES (:curriculum, :content, :position)
                    ON CONFLICT (curriculum_id, content_id)
                    DO UPDATE SET position = EXCLUDED.position"""),
            [
                {"curriculum": curriculum_id, "content": content_id, "position": index}
                for index, content_id in enumerate(content_ids, start=1)
            ],
        )
    session.execute(
        text("UPDATE sasu.curricula SET updated_at = clock_timestamp() WHERE curriculum_id = :id"),
        {"id": curriculum_id},
    )
