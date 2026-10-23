"""기존 콘텐츠·문항·학습 기록 읽기. 목록 수와 페이지는 같은 SQL에서 계산한다."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.types import MAX_BIGINT

CURRENT_QUESTION = """
    FROM sasu.contents c
    JOIN sasu.quizzes q ON q.content_id = c.content_id
    JOIN sasu.quiz_versions v ON v.quiz_version_id = q.current_version_id
    JOIN sasu.categories category ON category.category_id = c.category_id
"""
CARD_COLUMNS = """
    q.quiz_id AS question_id, v.quiz_version_id AS question_version_id,
    c.content_id, c.title AS content_title, c.category_id, category.name AS category_name,
    v.question_text, c.published_at
"""
CATEGORY_FILTER = """
    c.status = 'PUBLISHED'
    AND (CAST(:category AS bigint) IS NULL OR c.category_id = CAST(:category AS bigint))
"""


def category_exists(session: Session, category_id: int) -> bool:
    return session.scalar(
        text("SELECT EXISTS (SELECT 1 FROM sasu.categories WHERE category_id = :id)"),
        {"id": category_id},
    )


def _page(session, source, order, params, page, size, *, columns="", joins=""):
    # source/order/columns/joins는 이 모듈의 고정 SQL만 받는다. 요청 값은 모두 바인딩한다.
    result = (
        session.execute(
            text(
                f"""WITH matches AS ({source})
                SELECT totals.total, item.* {columns}
                FROM (SELECT count(*) AS total FROM matches) totals
                LEFT JOIN (
                    SELECT * FROM matches item ORDER BY {order} LIMIT :limit OFFSET :offset
                ) item ON true
                {joins}
                ORDER BY {order}"""
            ),
            {**params, "limit": size, "offset": min((page - 1) * size, MAX_BIGINT)},
        )
        .mappings()
        .all()
    )
    return [row for row in result if row["question_version_id"] is not None], result[0]["total"]


def list_wrong_answers(session: Session, user_id: int, epoch: int, status: str, query):
    source = f"""SELECT {CARD_COLUMNS}, v.question_type, w.status, w.wrong_count,
                        w.first_wrong_at, w.last_wrong_at, w.resolved_at, c.video_asset_id
                 {CURRENT_QUESTION}
                 JOIN sasu.wrong_answers w ON w.quiz_version_id = v.quiz_version_id
                 WHERE {CATEGORY_FILTER}
                   AND w.user_id = :user AND w.learning_epoch = :epoch AND w.status = :status"""
    columns = """,
        asset.duration_seconds, metrics.view_count, metrics.like_count,
        COALESCE((SELECT jsonb_agg(jsonb_build_object(
            'option_id', o.option_id, 'option_order', o.position, 'option_text', o.option_text)
            ORDER BY o.position) FROM sasu.quiz_options o
            WHERE o.quiz_version_id = item.question_version_id), '[]'::jsonb) AS options,
        COALESCE((SELECT jsonb_agg(jsonb_build_object('tag_id', t.tag_id, 'name', t.name)
            ORDER BY t.tag_id) FROM sasu.content_tags ct JOIN sasu.tags t USING (tag_id)
            WHERE ct.content_id = item.content_id), '[]'::jsonb) AS tags,
        EXISTS(SELECT 1 FROM sasu.content_likes l WHERE l.user_id = :user
            AND l.learning_epoch = :epoch AND l.content_id = item.content_id) AS liked,
        EXISTS(SELECT 1 FROM sasu.saved_contents s WHERE s.user_id = :user
            AND s.learning_epoch = :epoch AND s.content_id = item.content_id) AS saved,
        EXISTS(SELECT 1 FROM sasu.watch_records w WHERE w.user_id = :user
            AND w.learning_epoch = :epoch AND w.content_id = item.content_id
            AND w.completed_at IS NOT NULL) AS watch_completed
    """
    joins = """LEFT JOIN sasu.video_assets asset ON asset.video_asset_id = item.video_asset_id
               LEFT JOIN sasu.content_metrics metrics ON metrics.content_id = item.content_id"""
    return _page(
        session,
        source,
        "item.last_wrong_at DESC, item.question_version_id ASC",
        {"category": query.category_id, "user": user_id, "epoch": epoch, "status": status},
        query.page,
        query.size,
        columns=columns,
        joins=joins,
    )


def list_flashcards(session: Session, query):
    source = f"SELECT {CARD_COLUMNS} {CURRENT_QUESTION} WHERE {CATEGORY_FILTER}"
    return _page(
        session,
        source,
        "item.published_at DESC, item.content_id ASC",
        {"category": query.category_id},
        query.page,
        query.size,
    )


def find_flashcard(session: Session, version_id: int):
    # 앞면을 본 뒤 버전이 바뀌어도 요청한 버전을 그대로 제공한다.
    return (
        session.execute(
            text(f"""SELECT {CARD_COLUMNS}, v.explanation,
                        (SELECT option_text FROM sasu.quiz_options o
                         WHERE o.quiz_version_id = v.quiz_version_id AND o.is_correct) AS back
                 FROM sasu.quiz_versions v JOIN sasu.quizzes q USING (quiz_id)
                 JOIN sasu.contents c ON c.content_id = q.content_id
                 JOIN sasu.categories category ON category.category_id = c.category_id
                 WHERE v.quiz_version_id = :version AND c.status = 'PUBLISHED'"""),
            {"version": version_id},
        )
        .mappings()
        .one_or_none()
    )


def retry_versions(session: Session, user_id: int, epoch: int, version_ids: list[int]) -> set[int]:
    if not version_ids:
        return set()
    return set(
        session.scalars(
            text("""SELECT DISTINCT r.quiz_version_id FROM sasu.quiz_responses r
                JOIN sasu.quiz_attempts a ON a.attempt_id = r.attempt_id
                WHERE a.user_id = :user AND a.learning_epoch = :epoch
                  AND a.context = 'FEED_REVIEW' AND r.result = 'WRONG'
                  AND r.quiz_version_id = ANY(CAST(:versions AS bigint[]))"""),
            {"user": user_id, "epoch": epoch, "versions": version_ids},
        )
    )


def feed_candidates(session: Session, user_id: int, epoch: int, shown: list[int], retry: list[int]):
    return session.execute(
        text(f"""SELECT q.quiz_id, v.quiz_version_id, asset.storage_path,
                        asset.size_bytes, asset.mime_type, asset.duration_seconds
                 {CURRENT_QUESTION}
                 JOIN sasu.video_assets asset ON asset.video_asset_id = c.video_asset_id
                 JOIN sasu.watch_records watch ON watch.content_id = c.content_id
                    AND watch.user_id = :user AND watch.learning_epoch = :epoch
                 LEFT JOIN sasu.wrong_answers wrong ON wrong.quiz_version_id = v.quiz_version_id
                    AND wrong.user_id = :user AND wrong.learning_epoch = :epoch
                 WHERE c.status = 'PUBLISHED' AND watch.completed_at IS NOT NULL
                   AND (NOT (v.quiz_version_id = ANY(CAST(:shown AS bigint[])))
                        OR v.quiz_version_id = ANY(CAST(:retry AS bigint[])))
                 ORDER BY COALESCE(wrong.status = 'UNRESOLVED', false) DESC,
                          watch.last_watched_at ASC, c.content_id ASC"""),
        {"user": user_id, "epoch": epoch, "shown": shown, "retry": retry},
    ).mappings()
