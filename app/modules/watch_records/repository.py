import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_settings(session: Session, user_id: int) -> int | None:
    return session.scalar(
        text("SELECT learning_epoch FROM sasu.user_settings WHERE user_id = :uid FOR UPDATE"),
        {"uid": user_id},
    )


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


def upsert_visit(
    session: Session,
    *,
    visit_id: UUID,
    user_id: int,
    learning_epoch: int,
    content_id: int,
    video_asset_id: UUID,
    context: str,
    elapsed_seconds: float,
    watched_ranges: list[list[float]],
    sequence: int,
) -> tuple[bool, Decimal, list, int]:
    """Upsert watch_visits row.

    Returns (was_updated, elapsed_seconds, watched_ranges, last_sequence).
    was_updated=False when the given sequence is stale (≤ stored last_sequence).
    """
    row = (
        session.execute(
            text(
                """
                INSERT INTO sasu.watch_visits
                  (visit_id, user_id, learning_epoch, content_id, video_asset_id,
                   context, elapsed_seconds, watched_ranges, last_sequence)
                VALUES
                  (:vid, :uid, :epoch, :cid, CAST(:asset AS uuid),
                   :ctx, :elapsed, CAST(:ranges AS jsonb), :seq)
                ON CONFLICT (visit_id) DO UPDATE SET
                  elapsed_seconds = EXCLUDED.elapsed_seconds,
                  watched_ranges  = EXCLUDED.watched_ranges,
                  last_sequence   = EXCLUDED.last_sequence
                WHERE sasu.watch_visits.last_sequence < EXCLUDED.last_sequence
                RETURNING elapsed_seconds, watched_ranges, last_sequence
                """
            ),
            {
                "vid": str(visit_id),
                "uid": user_id,
                "epoch": learning_epoch,
                "cid": content_id,
                "asset": str(video_asset_id),
                "ctx": context,
                "elapsed": elapsed_seconds,
                "ranges": json.dumps(watched_ranges),
                "seq": sequence,
            },
        )
        .mappings()
        .one_or_none()
    )

    if row is not None:
        ranges = row["watched_ranges"]
        if isinstance(ranges, str):
            ranges = json.loads(ranges)
        return True, row["elapsed_seconds"], ranges, row["last_sequence"]

    # Stale sequence — read current state
    current = (
        session.execute(
            text(
                "SELECT elapsed_seconds, watched_ranges, last_sequence"
                " FROM sasu.watch_visits WHERE visit_id = :vid"
            ),
            {"vid": str(visit_id)},
        )
        .mappings()
        .one_or_none()
    )
    if current is None:
        return False, Decimal(0), [], 0
    ranges = current["watched_ranges"]
    if isinstance(ranges, str):
        ranges = json.loads(ranges)
    return False, current["elapsed_seconds"], ranges, current["last_sequence"]


def get_watch_record(session: Session, user_id: int, content_id: int):
    return (
        session.execute(
            text(
                "SELECT view_counted_at, completed_at"
                " FROM sasu.watch_records"
                " WHERE user_id = :uid AND content_id = :cid"
            ),
            {"uid": user_id, "cid": content_id},
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
              last_watched_at   = now(),
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
