from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.users.models import UserRole
from app.modules.users.service import get_actor
from app.modules.watch_records import repository as repo
from app.modules.watch_records.schemas import WatchVisitBody, WatchVisitResult


def _check_epoch(learning_epoch: int, record_generation: int) -> None:
    if learning_epoch != record_generation + 1:
        raise ApiError(409, "RECORD_GENERATION_MISMATCH", "현재 기록 세대를 다시 확인해 주세요.")


def _clip_ranges(
    ranges: list[list[float]], duration: float
) -> list[list[float]]:
    """Clip each range to [0, duration] and drop zero-length or invalid ranges."""
    clipped = []
    for start, end in ranges:
        s = max(0.0, start)
        e = min(duration, end)
        if e > s:
            clipped.append([s, e])
    return clipped


def _compute_coverage(ranges: list[list[float]], duration: float) -> float:
    """Merge overlapping ranges and compute covered / duration (0~1)."""
    if not ranges or duration <= 0:
        return 0.0
    sorted_r = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_r[0][:]]
    for s, e in sorted_r[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    total = sum(e - s for s, e in merged)
    return min(total / duration, 1.0)


def report_watch_visit(
    session: Session,
    actor_id: int,
    content_id: int,
    visit_id: UUID,
    record_generation: int,
    body: WatchVisitBody,
) -> WatchVisitResult:
    ctx = session.begin_nested() if session.in_transaction() else session.begin()
    with ctx:
        actor = get_actor(session, actor_id)
        if actor.role != UserRole.LEARNER:
            raise ApiError(403, "ROLE_NOT_ALLOWED", "학습자만 시청 기록을 보고할 수 있습니다.")

        # Lock order: user_settings → contents → watch_visits → watch_records
        learning_epoch = repo.lock_settings(session, actor.user_id)
        if learning_epoch is None:
            raise ApiError(404, "USER_NOT_FOUND", "사용자 설정을 찾을 수 없습니다.")
        _check_epoch(learning_epoch, record_generation)

        content = repo.lock_content(session, content_id)
        if content is None or content["status"] != "PUBLISHED":
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
        if content["video_asset_id"] is None or content["duration_seconds"] is None:
            raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠에 영상 자산이 없습니다.")

        current_asset_id = str(content["video_asset_id"])
        video_changed = current_asset_id != str(body.video_asset_id)
        duration = float(content["duration_seconds"])

        clipped = _clip_ranges(body.watched_ranges, duration)

        _, elapsed, stored_ranges, _ = repo.upsert_visit(
            session,
            visit_id=visit_id,
            user_id=actor.user_id,
            learning_epoch=learning_epoch,
            content_id=content_id,
            video_asset_id=body.video_asset_id,
            context=body.context,
            elapsed_seconds=body.elapsed_seconds,
            watched_ranges=clipped,
            sequence=body.sequence,
        )

        effective_elapsed = float(elapsed)
        effective_ranges = stored_ranges if isinstance(stored_ranges, list) else []
        coverage = _compute_coverage(effective_ranges, duration)

        if video_changed:
            existing = repo.get_watch_record(session, actor.user_id, content_id)
            return WatchVisitResult(
                view_counted=False,
                completed=existing["completed_at"] is not None if existing else False,
                coverage=coverage,
                video_changed=True,
            )

        # Snapshot before upsert to determine what changed
        before = repo.get_watch_record(session, actor.user_id, content_id)
        was_view_counted = before["view_counted_at"] is not None if before else False

        repo.upsert_watch_record(
            session,
            user_id=actor.user_id,
            learning_epoch=learning_epoch,
            content_id=content_id,
            elapsed_seconds=effective_elapsed,
            coverage=coverage,
        )

        after = repo.get_watch_record(session, actor.user_id, content_id)
        is_view_counted = after["view_counted_at"] is not None if after else False
        is_completed = after["completed_at"] is not None if after else False

    return WatchVisitResult(
        view_counted=not was_view_counted and is_view_counted,
        completed=is_completed,
        coverage=coverage,
        video_changed=False,
    )
