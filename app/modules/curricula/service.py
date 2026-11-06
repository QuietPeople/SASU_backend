"""커리큘럼 편성과 공통 조회. PRIVATE 편성은 보존하고 학습자 조회에서 제외한다."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.api.schemas import Page, page_offset
from app.core.exceptions import ApiError, check_edit_version
from app.core.security import Actor
from app.modules.contents.presentation import build_summary
from app.modules.contents.urls import build_thumbnail_url
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
from app.modules.videos.availability import is_video_row_available


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


def make_step(row, user_id: int | None, view: str, actor_id: int) -> CurriculumStep:
    available = row["status"] == "PUBLISHED" and is_video_row_available(row)
    watched = row["watched"] if user_id is not None else None
    correct = row["correct"] if user_id is not None else None
    content = None
    if view == "editor" or available:
        content = build_summary(
            {
                **row,
                "watch_completed": watched,
                "liked": row["liked"] if user_id is not None else None,
                "saved": row["saved"] if user_id is not None else None,
            },
            actor_id,
            preview=view == "editor",
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


def make_summary(
    curriculum,
    steps: list[CurriculumStep],
    user_id: int | None,
    *,
    preview_actor_id: int | None = None,
) -> CurriculumSummary:
    completed = sum(bool(step.completed) for step in steps) if user_id is not None else None
    percent = (
        float(round(Decimal(completed) * 100 / len(steps), 2))
        if steps and completed is not None
        else None
    )
    return summary_from_counts(
        curriculum,
        len(steps),
        sum(step.available for step in steps),
        completed,
        percent,
        preview_actor_id=preview_actor_id,
    )


def summary_from_counts(curriculum, count, available, completed, percent, *, preview_actor_id=None):
    thumbnail_url = build_thumbnail_url(
        "curriculums",
        curriculum["curriculum_id"],
        curriculum[
            "resolved_thumbnail_image_id"
            if preview_actor_id is not None
            else "public_thumbnail_image_id"
        ],
        preview_actor_id=preview_actor_id,
    )
    return CurriculumSummary(
        curriculum_id=curriculum["curriculum_id"],
        title=curriculum["title"],
        description=curriculum["description"],
        total_steps=count,
        available_steps=available,
        completed_steps=completed,
        progress_percent=percent,
        thumbnail_url=thumbnail_url,
        updated_at=curriculum.get("updated_at"),
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
        if query.view == "editor" or row["status"] != "PRIVATE"
    ]
    if query.view == "learner":
        for index, step in enumerate(steps, 1):
            step.step_order = index
    summary = make_summary(
        curriculum,
        steps,
        user_id,
        preview_actor_id=actor.user_id if query.view == "editor" else None,
    )
    if query.view == "learner" and summary.available_steps == 0:
        raise ApiError(404, "CURRICULUM_NOT_FOUND", "이용 가능한 커리큘럼을 찾을 수 없습니다.")
    return CurriculumDetail(summary=summary, steps=steps)


def get_list(session: Session, query: CurriculumListQuery, actor: Actor) -> Page[CurriculumSummary]:
    user_id = target_user(session, query, actor)
    start = page_offset(query.page, query.size)
    if query.view == "editor":
        total = repository.count_curricula(session, query.q)
        curricula = repository.list_curricula(session, query.q, offset=start, limit=query.size)
    else:
        curricula = repository.list_curricula(session, query.q)
    counts = defaultdict(lambda: [0, 0, 0])
    for row in repository.list_step_states(
        session, [c["curriculum_id"] for c in curricula], user_id
    ):
        if query.view == "learner" and row["status"] == "PRIVATE":
            continue
        state = counts[row["curriculum_id"]]
        state[0] += 1
        state[1] += row["status"] == "PUBLISHED" and is_video_row_available(row)
        state[2] += int(row["completed"])
    if query.view == "learner":
        curricula = [c for c in curricula if counts[c["curriculum_id"]][1]]
        total = len(curricula)
        curricula = curricula[start : start + query.size]
    summaries = []
    for curriculum in curricula:
        step_count, available, completed = counts[curriculum["curriculum_id"]]
        percent = (
            float(round(Decimal(completed) * 100 / step_count, 2))
            if step_count and user_id
            else None
        )
        summaries.append(
            summary_from_counts(
                curriculum,
                step_count,
                available,
                completed if user_id else None,
                percent,
                preview_actor_id=actor.user_id if query.view == "editor" else None,
            )
        )
    return Page[CurriculumSummary](
        items=summaries,
        page=query.page,
        size=query.size,
        total=total,
        has_next=start + query.size < total,
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
        check_edit_version(request.expected_updated_at, current["updated_at"])
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
        current = repository.find_curriculum(session, curriculum_id, lock=True)
        if current is None:
            raise ApiError(404, "CURRICULUM_NOT_FOUND", "커리큘럼을 찾을 수 없습니다.")
        check_edit_version(request.expected_updated_at, current["updated_at"])
        if len(repository.lock_contents(session, request.content_ids)) != len(request.content_ids):
            raise ApiError(404, "CONTENT_NOT_FOUND", "편성할 콘텐츠를 찾을 수 없습니다.")
        repository.replace_steps(session, curriculum_id, request.content_ids)
        result = get_detail(session, curriculum_id, CurriculumQuery(view="editor"), actor)
        session.commit()
        return CurriculumSteps(
            updated_at=result.summary.updated_at, items=result.steps, total_steps=len(result.steps)
        )
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
        if row["status"] != "PRIVATE"
    ]
    for index, step in enumerate(steps, 1):
        step.step_order = index
    summary = make_summary(curriculum, steps, user_id)
    return CurriculumProgress(
        user_id=user_id,
        curriculum_id=curriculum_id,
        total_steps=len(steps),
        completed_steps=summary.completed_steps,
        progress_percent=summary.progress_percent,
        steps=[ProgressStep.model_validate(step.model_dump()) for step in steps],
    )
