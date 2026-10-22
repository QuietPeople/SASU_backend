"""집계 전 원본별로 분리하여 다대다 조인에 의한 중복 카운트를 막는다."""

from sqlalchemy import text
from sqlalchemy.orm import Session

CONTENT_SQL = """
WITH attempts AS (
 SELECT a.*, r.response_id, r.result FROM sasu.quiz_attempts a
 JOIN sasu.quizzes q USING (quiz_id)
 LEFT JOIN sasu.quiz_responses r USING (attempt_id)
 WHERE q.content_id = :id
), displayed AS (
 SELECT DISTINCT attempt_id FROM sasu.learning_events
 WHERE content_id = :id AND event_type = 'QUIZ_DISPLAYED'
), contexts AS (
 SELECT context,
 count(*) FILTER (WHERE d.attempt_id IS NOT NULL) AS displayed_count,
 count(*) FILTER (WHERE result IN ('CORRECT','WRONG')) AS answered_count,
 count(*) FILTER (WHERE result = 'CORRECT') AS correct_count,
 count(*) FILTER (WHERE result = 'WRONG') AS wrong_count,
 count(*) FILTER (WHERE result = 'SKIPPED') AS skipped_count,
 count(*) FILTER (WHERE d.attempt_id IS NOT NULL AND response_id IS NULL)
     AS unanswered_display_count,
 count(*) FILTER (WHERE d.attempt_id IS NULL AND response_id IS NOT NULL)
     AS response_without_display_count,
 count(*) FILTER (WHERE d.attempt_id IS NOT NULL AND result IN ('CORRECT','WRONG'))
     AS displayed_answered_count
 FROM attempts a LEFT JOIN displayed d USING (attempt_id) GROUP BY context
), first_answers AS (
 SELECT f.result FROM sasu.first_video_responses f JOIN sasu.quizzes q USING (quiz_id)
 WHERE q.content_id = :id
)
SELECT c.content_id, m.view_count, m.like_count, m.saved_count,
 (SELECT count(*) FROM sasu.watch_records WHERE content_id=:id) AS played_count,
 (SELECT count(*) FROM sasu.watch_records WHERE content_id=:id
   AND completed_at IS NOT NULL) AS completed_count,
 COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM contexts x),'[]'::jsonb) AS contexts,
 (SELECT count(*) FROM first_answers) AS first_answered,
 (SELECT count(*) FROM first_answers WHERE result='CORRECT') AS first_correct,
 (SELECT count(*) FROM sasu.current_wrong_answers w WHERE w.content_id=:id)
 AS current_unresolved_count,
 (SELECT count(*) FROM sasu.wrong_answers w JOIN sasu.quiz_versions v USING(quiz_version_id)
   JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id=:id AND w.status='RESOLVED')
   AS resolved_version_count,
 (SELECT count(*) FROM sasu.learning_events WHERE content_id=:id
   AND event_type='CARD_OPENED') AS opened_count,
 (SELECT count(*) FROM sasu.learning_events WHERE content_id=:id
   AND event_type='CARD_REVEALED') AS revealed_count,
 (SELECT count(DISTINCT user_id) FROM sasu.learning_events WHERE content_id=:id
   AND event_type='CARD_OPENED') AS opened_users,
 (SELECT count(DISTINCT user_id) FROM sasu.learning_events WHERE content_id=:id
   AND event_type='CARD_REVEALED') AS revealed_users
FROM sasu.contents c JOIN sasu.content_metrics m USING(content_id) WHERE c.content_id=:id
"""

OVERVIEW_SQL = """
SELECT
 (SELECT count(*) FROM sasu.app_users WHERE role='LEARNER') AS learner_count,
 (SELECT count(*) FROM sasu.contents) AS content_count,
 (SELECT count(*) FROM sasu.contents WHERE status='PUBLISHED') AS published_content_count,
 (SELECT count(*) FROM sasu.curricula) AS curriculum_count,
 (SELECT coalesce(sum(view_count),0) FROM sasu.content_metrics) AS view_count,
 (SELECT coalesce(sum(like_count),0) FROM sasu.content_metrics) AS like_count,
 (SELECT coalesce(sum(saved_count),0) FROM sasu.content_metrics) AS saved_count,
 (SELECT count(*) FROM sasu.watch_records) AS played_count,
 (SELECT count(*) FROM sasu.watch_records WHERE completed_at IS NOT NULL) AS completed_count,
 (SELECT count(*) FROM sasu.first_video_responses) AS first_answered,
 (SELECT count(*) FROM sasu.first_video_responses WHERE result='CORRECT') AS first_correct
"""


def content_stats(session: Session, content_id: int):
    return session.execute(text(CONTENT_SQL), {"id": content_id}).mappings().one_or_none()


def overview(session: Session):
    return session.execute(text(OVERVIEW_SQL)).mappings().one()


def responses(session: Session, query):
    conditions = []
    params = {"limit": query.size, "offset": (query.page - 1) * query.size}
    # Column names are fixed server constants. Values are always bound parameters.
    for name, column in [
        ("user_id", "a.user_id"),
        ("content_id", "q.content_id"),
        ("quiz_version_id", "r.quiz_version_id"),
        ("context", "a.context"),
        ("result", "r.result"),
    ]:
        value = getattr(query, name)
        if value is not None:
            conditions.append(f"{column} = :{name}")
            params[name] = value
    for name, op in [("submitted_from", ">="), ("submitted_to", "<")]:
        value = getattr(query, name)
        if value is not None:
            conditions.append(f"r.submitted_at {op} :{name}")
            params[name] = value
    where = " AND ".join(conditions) or "TRUE"
    sql = f"""WITH filtered AS (
      SELECT r.response_id, r.attempt_id, a.user_id, q.content_id, a.quiz_id,
       r.quiz_version_id, r.selected_option_id, a.context, r.result, r.submitted_at
      FROM sasu.quiz_responses r JOIN sasu.quiz_attempts a USING(attempt_id)
      JOIN sasu.quizzes q USING(quiz_id) WHERE {where}
    ), page AS (SELECT * FROM filtered ORDER BY submitted_at DESC,response_id DESC
               LIMIT :limit OFFSET :offset)
    SELECT (SELECT count(*) FROM filtered) AS total,
     COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY submitted_at DESC,response_id DESC)
               FROM page p),'[]'::jsonb) AS items"""
    return session.execute(text(sql), params).mappings().one()


def content_list(session: Session, page: int, size: int):
    return (
        session.execute(
            text("""
    WITH selected AS (
      SELECT c.content_id,c.title,c.status,m.view_count,m.like_count,m.saved_count
      FROM sasu.contents c JOIN sasu.content_metrics m USING(content_id)
      ORDER BY c.content_id DESC LIMIT :size OFFSET :offset
    ) SELECT (SELECT count(*) FROM sasu.contents) AS total,
    COALESCE((SELECT jsonb_agg(to_jsonb(s) ORDER BY content_id DESC) FROM selected s),
             '[]'::jsonb) AS items
    """),
            {"size": size, "offset": (page - 1) * size},
        )
        .mappings()
        .one()
    )
