from datetime import UTC, datetime, timedelta
from itertools import permutations, product

import pytest

from app.modules.feeds.contracts import FeedCandidate, FeedRankingInput
from app.modules.feeds.ranking import rank_feed
from app.modules.feeds.service import get_feed_ranker


def candidate(cid, *, interest=False, related=False, watched=False, day=1):
    return FeedCandidate(
        cid,
        1 if interest else 2,
        frozenset({7} if related else {8}),
        datetime(2026, 10, day, tzinfo=UTC),
        watched,
    )


def context(items=(), *, interests=(1,), tags=(7,), resume=None):
    return FeedRankingInput(tuple(items), frozenset(interests), frozenset(tags), resume)


def test_empty_and_real_dependency():
    assert get_feed_ranker() is rank_feed
    assert get_feed_ranker()(context()) == ()


def test_lexicographic_priorities_not_additive_scores():
    # Every combination: even watched interest-only outranks related+unwatched.
    items = [
        candidate(i, interest=a, related=b, watched=not c)
        for i, (a, b, c) in enumerate(product([False, True], repeat=3), 1)
    ]
    result = rank_feed(context(items))
    assert [x.content_id for x in result] == [8, 7, 6, 5, 4, 3, 2, 1]
    assert [x.recommendation_reason for x in result] == [
        "INTEREST_CATEGORY",
        "INTEREST_CATEGORY",
        "INTEREST_CATEGORY",
        "INTEREST_CATEGORY",
        "RELATED_TAG",
        "RELATED_TAG",
        "UNWATCHED",
        "LATEST",
    ]
    assert all(x.recommendation_label for x in result)


@pytest.mark.parametrize("resume", [1, 2, 3, None, 999])
def test_resume_once_and_input_unchanged(resume):
    source = context(
        [candidate(1, watched=True), candidate(2, interest=True), candidate(3, related=True)],
        resume=resume,
    )
    original = source.candidates
    result = rank_feed(source)
    expected = (
        [2, 3, 1]
        if resume not in (1, 2, 3)
        else [resume] + [cid for cid in [2, 3, 1] if cid != resume]
    )
    assert [x.content_id for x in result] == expected
    assert sum(x.recommendation_reason == "LAST_CONTENT" for x in result) == (resume in (1, 2, 3))
    assert source.candidates == original


def test_cold_start_latest_then_id_independent_of_input_order():
    items = [candidate(3, day=2), candidate(1, day=2), candidate(2, day=1)]
    for order in permutations(items):
        result = rank_feed(context(order, interests=(), tags=()))
        assert [x.content_id for x in result] == [1, 3, 2]
        assert {x.recommendation_reason for x in result} == {"LATEST"}


def test_watched_not_completed_and_unwatched_priority():
    result = rank_feed(
        context([candidate(1, watched=True, day=3), candidate(2)], interests=(), tags=())
    )
    assert [(x.content_id, x.recommendation_reason) for x in result] == [
        (2, "UNWATCHED"),
        (1, "LATEST"),
    ]


def test_recent_tags_are_used_not_resume_tags():
    result = rank_feed(
        context(
            [candidate(1), candidate(2, related=True), candidate(3, watched=True)],
            interests=(),
            resume=1,
        )
    )
    assert [(x.content_id, x.recommendation_reason) for x in result] == [
        (1, "LAST_CONTENT"),
        (2, "RELATED_TAG"),
        (3, "LATEST"),
    ]


def test_exact_time_ties_and_timezone_offsets():
    first = candidate(1)
    same_instant = first.published_at.astimezone(
        __import__("datetime").timezone(timedelta(hours=9))
    )
    second = FeedCandidate(2, 2, frozenset(), same_instant, False)
    newer = FeedCandidate(3, 2, frozenset(), first.published_at + timedelta(microseconds=1), False)
    result = rank_feed(context([second, newer, first], interests=(), tags=()))
    assert [x.content_id for x in result] == [3, 1, 2]


def test_duplicate_candidate_ids_rejected():
    with pytest.raises(ValueError, match="unique"):
        rank_feed(context([candidate(1), candidate(1, interest=True)], resume=1))


def test_large_feed_no_truncation_and_deterministic():
    source = context([candidate(i) for i in range(1000, 0, -1)], resume=500)
    result = rank_feed(source)
    assert [x.content_id for x in result] == [500] + [i for i in range(1, 1001) if i != 500]
    assert rank_feed(source) == result
