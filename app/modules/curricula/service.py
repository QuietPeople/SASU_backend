"""커리큘럼 편성과 공통 조회. 비공개 단계도 편성과 진행률 분모에 보존한다."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.schemas import Page
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.security import Actor
from app.integrations.storage import LocalVideoStorage
from app.modules.contents.schemas import ContentSummary
from app.modules.contents.urls import build_video_url
from app.modules.curricula import repository
from app.modules.curricula.schemas import (
    CurriculumDetail,
    CurriculumInput,
    CurriculumListQuery,
    CurriculumPatch,
    CurriculumProgress,
    CurriculumQuery,
    CurriculumStep,
    CurriculumSteps,
    CurriculumSummary,
    ProgressStep,
    StepsInput,
)


def target_user(session: Session, query: CurriculumQuery, actor: Actor) -> int | None:
    if query.view == "editor" and actor.role != "ADMIN":
        raise ApiError(403, "EDITOR_VIEW_REQUIRED", "관리자 편집 조회가 필요합니다.")
    target = query.user_id
    if target is None and query.view == "learner" and actor.role == "LEARNER":
        target = actor.user_id
    if target is not None:
        if (
            actor.role != "ADMIN"
            and target != actor.user_id
            or not repository.learner_exists(session, target)
        ):
            raise ApiError(404, "USER_NOT_FOUND", "대상 학습자를 찾을 수 없습니다.")
    return target


def media_available(relative_path: str | None) -> bool:
    if not relative_path:
        return False
    try:
        storage = LocalVideoStorage(get_settings().video_storage_root)
        return storage.resolve_path(relative_path).is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def make_step(row, user_id: int | None, view: str, actor_id: int) -> CurriculumStep:
    available = row["status"] == "PUBLISHED" and media_available(row["storage_path"])
    watched = row["watched"] if user_id is not None else None
    correct = row["correct"] if user_id is not None else None
    content = None
    if view == "editor" or available:
        revision = str(row["video_asset_id"]) if row["video_asset_id"] else None
        video_url = None
        if revision:
            video_url = build_video_url(
                row["content_id"],
                revision,
                preview_actor_id=actor_id if view == "editor" else None,
            )
        content = ContentSummary(
            content_id=row["content_id"],
            title=row["title"],
            category={"category_id": row["category_id"], "name": row["category_name"]}
            if row["category_id"]
            else None,
            tags=row["tags"],
            video_duration=row["duration_seconds"],
            video_url=video_url,
            media_revision=revision,
            view_count=row["view_count"],
            like_count=row["like_count"],
            liked=row["liked"] if user_id is not None else None,
            saved=row["saved"] if user_id is not None else None,
            watch_completed=watched,
            has_quiz=row["has_quiz"],
            status=row["status"],
        )
    return CurriculumStep(
        curriculum_content_id=row["content_id"],
        content_id=row["content_id"],
        step_order=row["position"],
        content=content,
        available=available,
        watch_completed=watched,
        question_correct=correct,
        completed=bool(watched and correct) if user_id is not None else None,
    )


def make_summary(curriculum, steps: list[CurriculumStep], user_id: int | None) -> CurriculumSummary:
    completed = sum(bool(step.completed) for step in steps) if user_id is not None else None
    percent = (
        float(round(Decimal(completed) * 100 / len(steps), 2))
        if steps and completed is not None
        else None
    )
    return CurriculumSummary(
        curriculum_id=curriculum["curriculum_id"],
        title=curriculum["title"],
        description=curriculum["description"],
        total_steps=len(steps),
        available_steps=sum(step.available for step in steps),
        completed_steps=completed,
        progress_percent=percent,
    )


def get_detail(
    session: Session, curriculum_id: int, query: CurriculumQuery, actor: Actor
) -> CurriculumDetail:
    user_id = target_user(session, query, actor)
    curriculum = repository.find_curriculum(session, curriculum_id)
    if curriculum is None:
        raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼을 찾을 수 없습니다.")
    steps = [
        make_step(row, user_id, query.view, actor.user_id)
        for row in repository.load_steps(session, [curriculum_id], user_id)
    ]
    summary = make_summary(curriculum, steps, user_id)
    if query.view == "learner" and summary.available_steps == 0:
        raise ApiError(404, "CURRICULUM_NOT_FOUND", "이용 가능한 커리큘럼을 찾을 수 없습니다.")
    return CurriculumDetail(summary=summary, steps=steps)


def get_list(session: Session, query: CurriculumListQuery, actor: Actor) -> Page[CurriculumSummary]:
    user_id = target_user(session, query, actor)
    curricula = repository.list_curricula(session)
    grouped = defaultdict(list)
    for row in repository.load_steps(session, [c["curriculum_id"] for c in curricula], user_id):
        grouped[row["curriculum_id"]].append(make_step(row, user_id, query.view, actor.user_id))
    summaries = [make_summary(c, grouped[c["curriculum_id"]], user_id) for c in curricula]
    if query.view == "learner":
        summaries = [summary for summary in summaries if summary.available_steps > 0]
    start = (query.page - 1) * query.size
    return Page[CurriculumSummary](
        items=summaries[start : start + query.size],
        page=query.page,
        size=query.size,
        total=len(summaries),
        has_next=query.page * query.size < len(summaries),
    )


def create_curriculum(session: Session, request: CurriculumInput, actor: Actor) -> CurriculumDetail:
    try:
        curriculum_id = repository.create_curriculum(session, request.title, request.description)
        result = get_detail(session, curriculum_id, CurriculumQuery(view="editor"), actor)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def patch_curriculum(session: Session, curriculum_id: int, request: CurriculumPatch, actor: Actor):
    try:
        current = repository.find_curriculum(session, curriculum_id, lock=True)
        if current is None:
            raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼을 찾을 수 없습니다.")
        title = request.title if "title" in request.model_fields_set else current["title"]
        description = (
            request.description
            if "description" in request.model_fields_set
            else current["description"]
        )
        repository.update_curriculum(session, curriculum_id, title, description)
        result = get_detail(session, curriculum_id, CurriculumQuery(view="editor"), actor).summary
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def save_steps(
    session: Session, curriculum_id: int, request: StepsInput, actor: Actor
) -> CurriculumSteps:
    try:
        if len(set(request.content_ids)) != len(request.content_ids):
            raise ApiError(422, "DUPLICATE_CONTENT", "같은 영상을 중복 편성할 수 없습니다.")
        if repository.find_curriculum(session, curriculum_id, lock=True) is None:
            raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼을 찾을 수 없습니다.")
        if len(repository.lock_contents(session, request.content_ids)) != len(request.content_ids):
            raise ApiError(404, "CONTENT_NOT_FOUND", "편성할 콘텐츠를 찾을 수 없습니다.")
        repository.replace_steps(session, curriculum_id, request.content_ids)
        result = get_detail(session, curriculum_id, CurriculumQuery(view="editor"), actor)
        session.commit()
        return CurriculumSteps(items=result.steps, total_steps=len(result.steps))
    except Exception:
        session.rollback()
        raise


def get_progress(
    session: Session, curriculum_id: int, user_id: int, actor: Actor
) -> CurriculumProgress:
    user_id = target_user(session, CurriculumQuery(user_id=user_id), actor)
    curriculum = repository.find_curriculum(session, curriculum_id)
    if curriculum is None:
        raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼을 찾을 수 없습니다.")
    steps = [
        make_step(row, user_id, "learner", actor.user_id)
        for row in repository.load_steps(session, [curriculum_id], user_id)
    ]
    summary = make_summary(curriculum, steps, user_id)
    return CurriculumProgress(
        user_id=user_id,
        curriculum_id=curriculum_id,
        total_steps=len(steps),
        completed_steps=summary.completed_steps,
        progress_percent=summary.progress_percent,
        steps=[ProgressStep.model_validate(step.model_dump()) for step in steps],
    )
