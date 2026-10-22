"""각 응답의 세대와 집계값을 한 SQL 스냅샷에서 읽는다."""

from sqlalchemy import text
from sqlalchemy.orm import Session

DASHBOARD_SQL = """
SELECT s.user_id,s.learning_epoch - 1 AS record_generation,
 (SELECT count(*) FROM sasu.watch_records WHERE user_id=:id) AS watched_count,
 (SELECT count(*) FROM sasu.watch_records WHERE user_id=:id
  AND completed_at IS NOT NULL) AS watch_completed_count,
 (SELECT count(*) FROM sasu.content_likes WHERE user_id=:id) AS liked_count,
 (SELECT count(*) FROM sasu.saved_contents WHERE user_id=:id) AS saved_count,
 (SELECT count(*) FROM sasu.quiz_responses r JOIN sasu.quiz_attempts a USING(attempt_id)
  WHERE a.user_id=:id AND r.result IN ('CORRECT','WRONG')) AS answered_count,
 (SELECT count(*) FROM sasu.quiz_responses r JOIN sasu.quiz_attempts a USING(attempt_id)
  WHERE a.user_id=:id AND r.result='SKIPPED') AS skipped_count,
 (SELECT count(*) FROM sasu.current_wrong_answers WHERE user_id=:id) AS current_wrong_count,
 (SELECT count(*) FROM sasu.first_video_responses WHERE user_id=:id) AS first_answered,
 (SELECT count(*) FROM sasu.first_video_responses WHERE user_id=:id AND result='CORRECT')
   AS first_correct,
 COALESCE((SELECT jsonb_agg(jsonb_build_object(
    'curriculum_id',p.curriculum_id,'title',c.title,'total_steps',p.total_steps,
    'completed_steps',p.completed_steps,'progress_percent',round(p.progress_ratio*100,2))
    ORDER BY p.curriculum_id)
  FROM sasu.curriculum_progress p JOIN sasu.curricula c USING(curriculum_id)
  WHERE p.user_id=:id AND p.total_steps>0 AND p.completed_steps<p.total_steps
   AND p.available_steps>0 AND EXISTS (
    SELECT 1 FROM sasu.curriculum_items i JOIN sasu.watch_records w USING(content_id)
    WHERE i.curriculum_id=p.curriculum_id AND w.user_id=:id)), '[]'::jsonb)
   AS in_progress_curriculums
FROM sasu.user_settings s JOIN sasu.app_users u USING(user_id)
WHERE s.user_id=:id AND u.role='LEARNER'
"""

CATEGORIES_SQL = """
WITH counts AS (
 SELECT c.category_id,c.name,c.sort_order,
  (SELECT count(*) FROM sasu.contents x WHERE x.category_id=c.category_id
   AND x.status='PUBLISHED') AS published_content_count,
  (SELECT count(*) FROM sasu.watch_records w JOIN sasu.contents x USING(content_id)
   WHERE w.user_id=:id AND x.category_id=c.category_id AND x.status='PUBLISHED') AS watched_count,
  (SELECT count(*) FROM sasu.watch_records w JOIN sasu.contents x USING(content_id)
   WHERE w.user_id=:id AND x.category_id=c.category_id AND x.status='PUBLISHED'
   AND w.completed_at IS NOT NULL) AS completed_count,
  (SELECT count(DISTINCT x.content_id) FROM sasu.quiz_attempts a
   JOIN sasu.quiz_responses r USING(attempt_id) JOIN sasu.quizzes q USING(quiz_id)
   JOIN sasu.contents x USING(content_id)
   WHERE a.user_id=:id AND x.category_id=c.category_id AND x.status='PUBLISHED'
   AND r.result IN ('CORRECT','WRONG')) AS answered_content_count,
  (SELECT count(*) FROM sasu.current_wrong_answers w JOIN sasu.contents x USING(content_id)
   WHERE w.user_id=:id AND x.category_id=c.category_id) AS current_wrong_count
 FROM sasu.categories c
)
SELECT s.user_id,s.learning_epoch-1 AS record_generation,
 COALESCE((SELECT jsonb_agg(to_jsonb(c) - 'sort_order' ORDER BY sort_order,category_id)
 FROM counts c),'[]'::jsonb) AS items
FROM sasu.user_settings s JOIN sasu.app_users u USING(user_id)
WHERE s.user_id=:id AND u.role='LEARNER'
"""


def summary(session: Session, user_id: int):
    return session.execute(text(DASHBOARD_SQL), {"id": user_id}).mappings().one_or_none()


def categories(session: Session, user_id: int):
    return session.execute(text(CATEGORIES_SQL), {"id": user_id}).mappings().one_or_none()
