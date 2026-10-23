from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.users.settings_tables import user_interests, user_settings

_ALLOWED_SETTINGS_FIELDS = frozenset({"onboarding_status", "review_interval"})


def lock_settings(session: Session, user_id: int, *, write: bool = True) -> int | None:
    """학습자 상태를 잠근다. 읽기는 SHARE, 변경·초기화는 UPDATE이며 commit하지 않는다."""
    lock = "UPDATE" if write else "SHARE"
    return session.scalar(
        text(
            "SELECT s.learning_epoch FROM sasu.user_settings s "
            "JOIN sasu.app_users u ON u.user_id = s.user_id "
            f"WHERE s.user_id = :uid AND u.role = 'LEARNER' FOR {lock} OF s"
        ),
        {"uid": user_id},
    )


def get_settings(session: Session, user_id: int):
    return (
        session.execute(
            text(
                """
                SELECT s.onboarding_status, s.review_interval, s.learning_epoch,
                       COALESCE(
                           json_agg(
                               json_build_object('category_id', c.category_id, 'name', c.name)
                               ORDER BY c.category_id
                           ) FILTER (WHERE c.category_id IS NOT NULL),
                           '[]'::json
                       ) AS interests
                FROM sasu.user_settings s
                LEFT JOIN sasu.user_interests ui ON ui.user_id = s.user_id
                LEFT JOIN sasu.categories c ON c.category_id = ui.category_id
                WHERE s.user_id = :uid
                GROUP BY s.onboarding_status, s.review_interval, s.learning_epoch
                """
            ),
            {"uid": user_id},
        )
        .mappings()
        .one_or_none()
    )


def update_settings(session: Session, user_id: int, **fields: object) -> None:
    safe = {k: v for k, v in fields.items() if k in _ALLOWED_SETTINGS_FIELDS}
    if not safe:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in safe)
    session.execute(
        text(
            f"UPDATE sasu.user_settings SET {set_clause}, updated_at = now() "
            "WHERE user_id = :uid"
        ),
        {"uid": user_id, **safe},
    )


def check_missing_category_ids(session: Session, category_ids: list[int]) -> list[int]:
    if not category_ids:
        return []
    found = set(
        session.scalars(
            text("SELECT category_id FROM sasu.categories WHERE category_id = ANY(:ids)"),
            {"ids": category_ids},
        ).all()
    )
    return [cid for cid in category_ids if cid not in found]


def replace_interests(session: Session, user_id: int, category_ids: list[int]) -> None:
    session.execute(delete(user_interests).where(user_interests.c.user_id == user_id))
    if category_ids:
        session.execute(
            insert(user_interests)
            .values([{"user_id": user_id, "category_id": cid} for cid in category_ids])
            .on_conflict_do_nothing()
        )


def get_feed_position(session: Session, user_id: int):
    return (
        session.execute(
            text(
                """
                SELECT s.last_content_id,
                       CASE
                           WHEN s.last_content_id IS NULL THEN false
                           WHEN c.content_id IS NULL
                                OR c.status <> 'PUBLISHED'
                                OR c.video_asset_id IS NULL THEN true
                           ELSE false
                       END AS resume_unavailable
                FROM sasu.user_settings s
                LEFT JOIN sasu.contents c ON c.content_id = s.last_content_id
                WHERE s.user_id = :uid
                """
            ),
            {"uid": user_id},
        )
        .mappings()
        .one_or_none()
    )


def update_last_content(session: Session, user_id: int, content_id: int) -> None:
    session.execute(
        text(
            "UPDATE sasu.user_settings SET last_content_id = :cid, updated_at = now() "
            "WHERE user_id = :uid"
        ),
        {"uid": user_id, "cid": content_id},
    )


def lock_content_status(session: Session, content_id: int) -> str | None:
    return session.scalar(
        text("SELECT status FROM sasu.contents WHERE content_id = :cid FOR UPDATE"),
        {"cid": content_id},
    )
