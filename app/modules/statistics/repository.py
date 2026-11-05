"""집계 전 원본별로 분리하여 다대다 조인에 의한 중복 카운트를 막는다."""

from sqlalchemy import text

from app.api.schemas import page_offset

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
SELECT c.content_id, c.title, m.view_count, m.like_count, m.saved_count,
 (SELECT count(*) FROM sasu.watch_records WHERE content_id=:id) AS played_count,
 (SELECT count(*) FROM sasu.watch_records WHERE content_id=:id
   AND completed_at IS NOT NULL) AS completed_count,
 COALESCE((SELECT jsonb_agg(to_jsonb(x)) FROM contexts x),'[]'::jsonb) AS contexts,
 (SELECT count(*) FROM first_answers) AS first_answered,
 (SELECT count(*) FROM first_answers WHERE result='CORRECT') AS first_correct,
(SELECT count(*) FROM sasu.wrong_answers w JOIN sasu.quizzes q ON
q.current_version_id=w.quiz_version_id WHERE q.content_id=:id AND w.status='UNRESOLVED')
 AS current_unresolved_count,
 (SELECT count(*) FROM sasu.wrong_answers w JOIN sasu.quiz_versions v USING(quiz_version_id)
JOIN sasu.quizzes q USING(quiz_id) WHERE q.content_id=:id AND
q.current_version_id=w.quiz_version_id AND w.status='RESOLVED')
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


def content_stats(session, content_id):
    return session.execute(text(CONTENT_SQL), {"id": content_id}).mappings().one_or_none()


def overview(session):
    return (
        session.execute(
            text("""
        WITH contexts AS (
            SELECT a.context, count(d.event_id) AS displayed_count,
              count(*) FILTER (WHERE r.result IN ('CORRECT','WRONG')) AS answered_count,
              count(*) FILTER (WHERE r.result='CORRECT') AS correct_count,
              count(*) FILTER (WHERE r.result='SKIPPED') AS skipped_count
            FROM sasu.quiz_attempts a LEFT JOIN sasu.quiz_responses r USING(attempt_id)
            JOIN sasu.quizzes q ON q.quiz_id=a.quiz_id
            LEFT JOIN sasu.learning_events d ON d.attempt_id=a.attempt_id
              AND d.event_type='QUIZ_DISPLAYED' AND d.content_id=q.content_id GROUP BY a.context
        )
        SELECT * FROM
          (SELECT count(*) AS content_count, count(*) FILTER (WHERE c.status='PUBLISHED')
           AS published_content_count FROM sasu.contents c) contents
        CROSS JOIN (SELECT count(*) AS played_count, count(completed_at) AS completed_count,
                           count(view_counted_at) AS view_count FROM sasu.watch_records) watches
        CROSS JOIN (SELECT count(*) AS like_count FROM sasu.content_likes) likes
        CROSS JOIN (SELECT count(*) AS saved_count FROM sasu.saved_contents) saves
        CROSS JOIN (SELECT count(*) AS first_answered, count(*) FILTER (WHERE result='CORRECT')
                    AS first_correct FROM sasu.first_video_responses) firsts
        CROSS JOIN (SELECT count(*) FILTER (WHERE w.status='UNRESOLVED')
                    AS current_unresolved_count,
                    count(*) FILTER (WHERE w.status='RESOLVED') AS resolved_version_count
                    FROM sasu.wrong_answers w JOIN sasu.quizzes q
                    ON q.current_version_id=w.quiz_version_id) wrongs
        CROSS JOIN (SELECT count(*) FILTER (WHERE event_type='CARD_OPENED') AS opened_count,
                    count(*) FILTER (WHERE event_type='CARD_REVEALED') AS revealed_count
                    FROM sasu.learning_events WHERE content_id IS NOT NULL) cards
        CROSS JOIN (SELECT coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) AS contexts
                    FROM contexts x) grouped
    """)
        )
        .mappings()
        .one()
    )


def content_list(session, query):
    filtered = (
        "(CAST(:category AS bigint) IS NULL OR c.category_id=:category) "
        "AND (:status='ALL' OR c.status=:status)"
    )
    sql = (
        """WITH selected AS (
       SELECT c.* FROM sasu.contents c WHERE """
        + filtered
        + """
       ORDER BY published_at DESC NULLS LAST, content_id ASC LIMIT :size OFFSET :offset
    ), calculated AS (
       SELECT target.published_at, stats.* FROM selected target CROSS JOIN LATERAL (
    """
        + CONTENT_SQL.replace(":id", "target.content_id")
        + """
       ) stats
    ) SELECT (SELECT count(*) FROM sasu.contents c WHERE """
        + filtered
        + """) AS total,
      COALESCE((SELECT jsonb_agg(to_jsonb(x) ORDER BY published_at DESC NULLS LAST, content_id ASC)
      FROM calculated x),'[]'::jsonb) AS items"""
    )
    return (
        session.execute(
            text(sql),
            {
                "category": query.category_id,
                "status": query.status,
                "size": query.size,
                "offset": page_offset(query.page, query.size),
            },
        )
        .mappings()
        .one()
    )


def responses(session, query):
    conditions = []
    params = {"limit": query.size, "offset": page_offset(query.page, query.size)}
    mapping = {
        "user_id": "a.user_id",
        "content_id": "q.content_id",
        "question_id": "a.quiz_id",
        "question_version_id": "r.quiz_version_id",
        "response_path": "a.context",
        "result": "r.result",
    }
    for name, column in mapping.items():
        value = getattr(query, name)
        if value is not None:
            if name == "response_path":
                value = {
                    "VIDEO_QUIZ": "VIDEO_END",
                    "FEED_REVIEW": "FEED_REVIEW",
                    "WRONG_NOTE": "WRONG_REVIEW",
                }[value]
            if name == "result" and value == "SKIP":
                value = "SKIPPED"
            conditions.append(f"{column}=:{name}")
            params[name] = value
    where = " AND ".join(conditions) or "TRUE"
    sql = (
        """WITH filtered AS (
      SELECT r.response_id,r.submitted_at FROM sasu.quiz_responses r
      JOIN sasu.quiz_attempts a USING(attempt_id) JOIN sasu.quizzes q USING(quiz_id)
      WHERE """
        + where
        + """), page AS (
SELECT * FROM filtered ORDER BY submitted_at DESC,response_id DESC LIMIT :limit OFFSET
:offset)
      SELECT (SELECT count(*) FROM filtered) AS total,
      COALESCE((SELECT jsonb_agg(response_id ORDER BY submitted_at DESC,response_id DESC)
      FROM page),'[]'::jsonb) AS ids"""
    )
    return session.execute(text(sql), params).mappings().one()
