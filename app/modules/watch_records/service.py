from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.modules.users.service import require_learner
from app.modules.users.settings_service import current_epoch
from app.modules.watch_records import repository as repo
from app.modules.watch_records.schemas import WatchVisitBody, WatchVisitResult


def _merge_ranges(ranges: list[list[float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _compute_coverage(ranges: list[list[float]], duration: float) -> float:
    return sum(end - start for start, end in _merge_ranges(ranges)) / duration


def report_watch_visit(
    session: Session,
    actor_id: int,
    user_id: int,
    content_id: int,
    record_generation: int,
    body: WatchVisitBody,
) -> WatchVisitResult:
    with session.begin_nested() if session.in_transaction() else session.begin():
        require_learner(session, actor_id, user_id)
        epoch = current_epoch(session, user_id, record_generation)
        content = repo.lock_content(session, content_id)
        if content is None or content["status"] != "PUBLISHED" or content["video_asset_id"] is None:
            raise ApiError(404, "CONTENT_NOT_FOUND", "접근 가능한 콘텐츠가 없습니다.")
        if str(content["video_asset_id"]) != body.media_revision:
            raise ApiError(
                409, "VIDEO_CHANGED", "영상이 교체되었습니다. 콘텐츠를 다시 조회해 주세요."
            )
        duration = float(content["duration_seconds"])
        segments = _merge_ranges(body.watched_segments)
        covered = sum(end - start for start, end in segments)
        if (
            any(end > duration for _, end in segments)
            or covered > body.actual_played_seconds + 0.001
        ):
            raise ApiError(
                422, "INVALID_WATCH_REPORT", "시청 구간과 실제 재생 시간이 일치하지 않습니다."
            )
        ratio = covered / duration
        context = "SAVED" if body.context == "LIBRARY" else body.context

        # 같은 방문 ID를 다른 사용자·콘텐츠에 재사용하지 못하도록 최초 등록도 직렬화한다.
        repo.lock_visit_id(session, body.visit_id)
        visit = repo.get_visit(session, body.visit_id)
        if visit is not None and (
            visit["user_id"] != user_id
            or visit["learning_epoch"] != epoch
            or visit["content_id"] != content_id
            or str(visit["video_asset_id"]) != body.media_revision
            or visit["context"] != context
        ):
            raise ApiError(422, "INVALID_WATCH_REPORT", "다른 방문에 사용한 visit_id입니다.")

        before = repo.get_watch_record(session, user_id, content_id)
        effective_elapsed = max(
            float(visit["elapsed_seconds"]) if visit else 0, body.actual_played_seconds
        )
        previous_segments = visit["watched_ranges"] if visit else []
        previous_ratio = _compute_coverage(previous_segments, duration)
        effective_segments = segments if ratio >= previous_ratio else previous_segments
        repo.save_visit(
            session,
            body.visit_id,
            user_id,
            epoch,
            content_id,
            content["video_asset_id"],
            context,
            effective_elapsed,
            effective_segments,
        )
        repo.upsert_watch_record(
            session,
            user_id=user_id,
            learning_epoch=epoch,
            content_id=content_id,
            elapsed_seconds=effective_elapsed,
            coverage=max(ratio, previous_ratio),
        )
        after = repo.get_watch_record(session, user_id, content_id)
        counted = after["view_counted_at"] is not None
        return WatchVisitResult(
            user_id=user_id,
            content_id=content_id,
            visit_id=body.visit_id,
            view_counted=counted,
            newly_view_counted=counted and (before is None or before["view_counted_at"] is None),
            watch_completed=after["completed_at"] is not None,
            visit_watch_percent=round(ratio * 100, 2),
            max_watch_percent=round(float(after["max_coverage_ratio"]) * 100, 2),
            feed_completion_eligible=body.context == "FEED" and ratio >= 0.9,
            view_count=repo.view_count(session, content_id),
            first_played_at=after["first_played_at"],
            last_watched_at=after["last_watched_at"],
            completed_at=after["completed_at"],
            record_generation=epoch - 1,
        )
