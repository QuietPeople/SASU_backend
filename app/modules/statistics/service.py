from decimal import Decimal

from sqlalchemy import text

from app.api.schemas import Page
from app.core.exceptions import ApiError
from app.modules.admin.schemas import Rate, ReactionStats
from app.modules.responses.schemas import ResponseDetail
from app.modules.responses.service import get_response
from app.modules.statistics import repository
from app.modules.statistics.schemas import (
    ContentStatistics,
    FeedReviewStats,
    FlashcardStats,
    Overview,
    VideoQuizStats,
    WrongReviewStats,
)


def rate(numerator, denominator):
    return Rate(
        numerator=numerator,
        denominator=denominator,
        percent=float(round(Decimal(numerator) * 100 / denominator, 2)) if denominator else None,
    )


def metrics(row):
    def context(name):
        return next((x for x in row.get("contexts", []) if x["context"] == name), {})

    def basic(x):
        return dict(
            shown_count=x.get("displayed_count", 0),
            answered_count=x.get("answered_count", 0),
            skipped_count=x.get("skipped_count", 0),
        )

    video, feed, wrong = (context(x) for x in ["VIDEO_END", "FEED_REVIEW", "WRONG_REVIEW"])
    return dict(
        reactions=ReactionStats(
            view_count=row.get("view_count", 0),
            like_count=row.get("like_count", 0),
            saved_count=row.get("saved_count", 0),
            watch_completion=rate(row.get("completed_count", 0), row.get("played_count", 0)),
        ),
        quiz=VideoQuizStats(
            **basic(video),
            participation=rate(video.get("answered_count", 0), video.get("displayed_count", 0)),
            first_accuracy=rate(row.get("first_correct", 0), row.get("first_answered", 0)),
        ),
        feed_review=FeedReviewStats(
            **basic(feed),
            response_rate=rate(feed.get("answered_count", 0), feed.get("displayed_count", 0)),
            accuracy=rate(feed.get("correct_count", 0), feed.get("answered_count", 0)),
        ),
        wrong_review=WrongReviewStats(
            answered_count=wrong.get("answered_count", 0),
            accuracy=rate(wrong.get("correct_count", 0), wrong.get("answered_count", 0)),
            pending_count=row.get("current_unresolved_count", 0),
            resolved_count=row.get("resolved_version_count", 0),
        ),
        flashcards=FlashcardStats(
            viewed_count=row.get("opened_count", 0), flipped_count=row.get("revealed_count", 0)
        ),
    )


def as_content(row):
    return ContentStatistics(content_id=row["content_id"], title=row["title"], **metrics(row))


def content_stats(session, content_id):
    row = repository.content_stats(session, content_id)
    if row is None:
        raise ApiError(404, "CONTENT_NOT_FOUND", "콘텐츠를 찾을 수 없습니다.")
    return as_content(row)


def overview(session):
    rows = repository.all_stats(session)
    total = {}
    contexts = {}
    for row in rows:
        for key in (
            "view_count",
            "like_count",
            "saved_count",
            "completed_count",
            "played_count",
            "first_correct",
            "first_answered",
            "current_unresolved_count",
            "resolved_version_count",
            "opened_count",
            "revealed_count",
        ):
            total[key] = total.get(key, 0) + row[key]
        for item in row["contexts"]:
            target = contexts.setdefault(item["context"], {"context": item["context"]})
            for key, value in item.items():
                if key != "context":
                    target[key] = target.get(key, 0) + value
    total["contexts"] = list(contexts.values())
    return Overview(
        content_count=len(rows),
        published_content_count=sum(r["status"] == "PUBLISHED" for r in rows),
        **metrics(total),
    )


def exists(session, table, column, value, code):
    if (
        value is not None
        and session.scalar(text(f"SELECT 1 FROM sasu.{table} WHERE {column}=:id"), {"id": value})
        is None
    ):
        raise ApiError(404, code, "지정한 필터 대상을 찾을 수 없습니다.")


def content_list(session, query):
    exists(session, "categories", "category_id", query.category_id, "CATEGORY_NOT_FOUND")
    row = repository.content_list(session, query)
    return Page[ContentStatistics](
        items=[as_content(x) for x in row["items"]],
        total=row["total"],
        page=query.page,
        size=query.size,
        has_next=query.page * query.size < row["total"],
    )


def responses(session, query, actor):
    for table, column, value, code in [
        ("contents", "content_id", query.content_id, "CONTENT_NOT_FOUND"),
        ("app_users", "user_id", query.user_id, "USER_NOT_FOUND"),
        ("quizzes", "quiz_id", query.question_id, "QUESTION_VERSION_NOT_FOUND"),
        (
            "quiz_versions",
            "quiz_version_id",
            query.question_version_id,
            "QUESTION_VERSION_NOT_FOUND",
        ),
    ]:
        exists(session, table, column, value, code)
    if query.question_id is not None or query.question_version_id is not None:
        found = session.scalar(
            text("""SELECT 1 FROM sasu.quizzes q JOIN sasu.quiz_versions v USING(quiz_id)
          WHERE (CAST(:q AS bigint) IS NULL OR q.quiz_id=:q)
          AND (CAST(:v AS bigint) IS NULL OR v.quiz_version_id=:v)
          AND (CAST(:c AS bigint) IS NULL OR q.content_id=:c) LIMIT 1"""),
            {"q": query.question_id, "v": query.question_version_id, "c": query.content_id},
        )
        if found is None:
            raise ApiError(422, "FILTER_RELATION_MISMATCH", "콘텐츠·문항·버전의 소속이 다릅니다.")
    row = repository.responses(session, query)
    return Page[ResponseDetail](
        items=[get_response(session, id, actor) for id in row["ids"]],
        total=row["total"],
        page=query.page,
        size=query.size,
        has_next=query.page * query.size < row["total"],
    )
