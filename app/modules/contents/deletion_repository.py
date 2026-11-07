"""콘텐츠 전체 삭제의 참조 순서와 기존 기록·편성 잠금 경계를 한곳에서 관리한다."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.curricula.repository import replace_steps


def lock_dependencies(session: Session, content_id: int) -> None:
    # 호출자가 대상 콘텐츠를 먼저 잠가 새 학습 기록·편성 연결을 막는다.
    # 기존 요청은 설정/시리즈 -> 콘텐츠 순서이므로 관련 행은 NOWAIT로 잠근다.
    # 충돌하면 삭제 트랜잭션 전체를 되돌려 상대 요청이 진행되게 한다.
    params = {"id": content_id}
    session.execute(
        text("""SELECT quiz_id FROM sasu.quizzes WHERE content_id=:id
            ORDER BY quiz_id FOR UPDATE NOWAIT"""),
        params,
    ).all()
    session.execute(
        text("""WITH versions AS (
                SELECT v.quiz_version_id FROM sasu.quiz_versions v
                JOIN sasu.quizzes q USING (quiz_id) WHERE q.content_id=:id
            ), attempts AS (
                SELECT a.attempt_id, a.user_id FROM sasu.quiz_attempts a
                JOIN sasu.quizzes q USING (quiz_id) WHERE q.content_id=:id
            ), affected_users AS (
                SELECT user_id FROM sasu.user_settings WHERE last_content_id=:id
                UNION SELECT user_id FROM sasu.watch_visits WHERE content_id=:id
                UNION SELECT user_id FROM sasu.watch_records WHERE content_id=:id
                UNION SELECT user_id FROM sasu.content_likes WHERE content_id=:id
                UNION SELECT user_id FROM sasu.saved_contents WHERE content_id=:id
                UNION SELECT user_id FROM attempts
                UNION SELECT user_id FROM sasu.wrong_answers
                    WHERE quiz_version_id IN (SELECT quiz_version_id FROM versions)
                UNION SELECT user_id FROM sasu.learning_events WHERE content_id=:id
                    OR quiz_version_id IN (SELECT quiz_version_id FROM versions)
                    OR attempt_id IN (SELECT attempt_id FROM attempts)
            )
            SELECT s.user_id FROM sasu.user_settings s
            WHERE s.user_id IN (SELECT user_id FROM affected_users)
            ORDER BY s.user_id FOR UPDATE OF s NOWAIT"""),
        params,
    ).all()
    session.execute(
        text("""SELECT c.curriculum_id FROM sasu.curricula c
            WHERE EXISTS (SELECT 1 FROM sasu.curriculum_items i
                WHERE i.curriculum_id=c.curriculum_id AND i.content_id=:id)
            ORDER BY c.curriculum_id FOR UPDATE OF c NOWAIT"""),
        params,
    ).all()


def delete_owned_rows(session: Session, content) -> list[tuple[str, str]]:
    params = {"id": content.content_id}
    quiz_ids = "SELECT quiz_id FROM sasu.quizzes WHERE content_id=:id"
    versions = f"SELECT quiz_version_id FROM sasu.quiz_versions WHERE quiz_id IN ({quiz_ids})"
    attempts = f"SELECT attempt_id FROM sasu.quiz_attempts WHERE quiz_id IN ({quiz_ids})"
    video_ids = list(
        session.scalars(
            text("""SELECT video_asset_id FROM sasu.contents WHERE content_id=:id
                UNION SELECT video_asset_id FROM sasu.watch_visits WHERE content_id=:id"""),
            params,
        )
    )
    curricula = list(
        session.scalars(
            text("""SELECT curriculum_id FROM sasu.curriculum_items
                WHERE content_id=:id ORDER BY curriculum_id"""),
            params,
        )
    )
    session.execute(
        text("UPDATE sasu.user_settings SET last_content_id=NULL WHERE last_content_id=:id"),
        params,
    )
    # 이벤트 재시도 키는 learning_events 외래키의 CASCADE로 함께 제거된다.
    statements = [
        f"DELETE FROM sasu.learning_events WHERE content_id=:id "
        f"OR quiz_version_id IN ({versions}) OR attempt_id IN ({attempts})",
        f"DELETE FROM sasu.wrong_answers WHERE quiz_version_id IN ({versions})",
        f"DELETE FROM sasu.quiz_responses WHERE attempt_id IN ({attempts})",
        f"DELETE FROM sasu.quiz_attempts WHERE quiz_id IN ({quiz_ids})",
        "DELETE FROM sasu.watch_visits WHERE content_id=:id",
        "DELETE FROM sasu.watch_records WHERE content_id=:id",
        "DELETE FROM sasu.content_likes WHERE content_id=:id",
        "DELETE FROM sasu.saved_contents WHERE content_id=:id",
        "DELETE FROM sasu.content_tags WHERE content_id=:id",
    ]
    for statement in statements:
        session.execute(text(statement), params)
    for curriculum_id in curricula:
        remaining = list(
            session.scalars(
                text("""SELECT content_id FROM sasu.curriculum_items
                    WHERE curriculum_id=:curriculum AND content_id<>:id ORDER BY position"""),
                {**params, "curriculum": curriculum_id},
            )
        )
        replace_steps(session, curriculum_id, remaining)
    # 콘텐츠 부모 삭제에서만 퀴즈 -> 버전 -> 보기 CASCADE를 허용한다.
    session.execute(text("DELETE FROM sasu.contents WHERE content_id=:id"), params)
    # 다른 콘텐츠/시리즈가 참조하는 이미지는 보존한다. 교체 전 영상도 참조가 없을 때만 제거한다.
    files = []
    for video_id in filter(None, video_ids):
        path = session.scalar(
            text("""DELETE FROM sasu.video_assets a WHERE video_asset_id=:asset
                AND NOT EXISTS (SELECT 1 FROM sasu.contents c
                                WHERE c.video_asset_id=a.video_asset_id)
                AND NOT EXISTS (SELECT 1 FROM sasu.watch_visits v
                                WHERE v.video_asset_id=a.video_asset_id)
                RETURNING storage_path"""),
            {"asset": video_id},
        )
        if path:
            files.append(("video", path))
    if content.thumbnail_image_id is not None:
        path = session.scalar(
            text("""DELETE FROM sasu.image_assets a WHERE image_asset_id=:asset
                AND NOT EXISTS (SELECT 1 FROM sasu.contents c
                                WHERE c.thumbnail_image_id=a.image_asset_id)
                AND NOT EXISTS (SELECT 1 FROM sasu.curricula c
                                WHERE c.thumbnail_image_id=a.image_asset_id)
                RETURNING storage_path"""),
            {"asset": content.thumbnail_image_id},
        )
        if path:
            files.append(("image", path))
    return files
