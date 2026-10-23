import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.watch_records.tables import watch_records


def lock_content(session: Session, content_id: int):
    """Lock contents row; return status, video_asset_id, duration_seconds or None."""
    return (
        session.execute(
            text(
                """
                SELECT c.status, c.video_asset_id, va.duration_seconds
                FROM sasu.contents c
                LEFT JOIN sasu.video_assets va ON va.video_asset_id = c.video_asset_id
                WHERE c.content_id = :cid
                FOR UPDATE OF c
                """
            ),
            {"cid": content_id},
        )
        .mappings()
        .one_or_none()
    )


def get_watch_record(session: Session, user_id: int, content_id: int):
    return (
        session.execute(
            select(watch_records).where(
                watch_records.c.user_id == user_id, watch_records.c.content_id == content_id
            )
        )
        .mappings()
        .one_or_none()
    )


def upsert_watch_record(
    session: Session,
    *,
    user_id: int,
    learning_epoch: int,
    content_id: int,
    elapsed_seconds: float,
    coverage: float,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO sasu.watch_records
              (user_id, learning_epoch, content_id,
               first_played_at, last_watched_at,
               view_counted_at, completed_at, max_coverage_ratio)
            VALUES
              (:uid, :epoch, :cid,
               now(), now(),
               CASE WHEN :elapsed >= 3 THEN now() ELSE NULL END,
               CASE WHEN :coverage >= 0.9 THEN now() ELSE NULL END,
               :coverage)
            ON CONFLICT (user_id, content_id) DO UPDATE SET
              learning_epoch    = EXCLUDED.learning_epoch,
              last_watched_at   = clock_timestamp(),
              view_counted_at   = COALESCE(
                                    sasu.watch_records.view_counted_at,
                                    EXCLUDED.view_counted_at),
              completed_at      = COALESCE(
                                    sasu.watch_records.completed_at,
                                    EXCLUDED.completed_at),
              max_coverage_ratio = GREATEST(
                                    sasu.watch_records.max_coverage_ratio,
                                    EXCLUDED.max_coverage_ratio)
            """
        ),
        {
            "uid": user_id,
            "epoch": learning_epoch,
            "cid": content_id,
            "elapsed": float(elapsed_seconds),
            "coverage": float(coverage),
        },
    )


def lock_visit_id(session: Session, visit_id: UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"watch:{visit_id}"},
    )


def get_visit(session: Session, visit_id: UUID):
    return (
        session.execute(
            text("SELECT * FROM sasu.watch_visits WHERE visit_id = :id FOR UPDATE"),
            {"id": visit_id},
        )
        .mappings()
        .one_or_none()
    )


def save_visit(session, visit_id, user_id, epoch, content_id, asset_id, context, elapsed, ranges):
    session.execute(
        text("""INSERT INTO sasu.watch_visits
            (visit_id, user_id, learning_epoch, content_id, video_asset_id,
             context, elapsed_seconds, watched_ranges, last_sequence)
            VALUES (:id, :user, :epoch, :content, :asset, :context, :elapsed,
                    CAST(:ranges AS jsonb), 0)
            ON CONFLICT (visit_id) DO UPDATE SET
              elapsed_seconds = EXCLUDED.elapsed_seconds,
              watched_ranges = EXCLUDED.watched_ranges,
              last_sequence = sasu.watch_visits.last_sequence + 1"""),
        {
            "id": visit_id,
            "user": user_id,
            "epoch": epoch,
            "content": content_id,
            "asset": asset_id,
            "context": context,
            "elapsed": elapsed,
            "ranges": json.dumps(ranges),
        },
    )


def view_count(session: Session, content_id: int) -> int:
    return (
        session.scalar(
            text("SELECT view_count FROM sasu.content_metrics WHERE content_id = :id"),
            {"id": content_id},
        )
        or 0
    )
