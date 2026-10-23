import pytest
from sqlalchemy import text


def headers(uid, generation=None):
    result = {"X-Actor-Id": str(uid)}
    if generation is not None:
        result["X-Record-Generation"] = str(generation)
    return result


def test_settings_contract_and_no_read_side_effect(client, seed, database):
    uid = seed["learner_id"]
    result = client.get(f"/api/users/{uid}/settings", headers=headers(uid))
    assert result.status_code == 200
    assert result.json() == {
        "user_id": uid,
        "interest_category_ids": [],
        "interest_guide_completed": False,
        "review_interval": 5,
        "record_generation": 0,
    }
    assert (
        database.scalar(
            text("SELECT onboarding_status FROM sasu.user_settings WHERE user_id=:u"), {"u": uid}
        )
        == "PENDING"
    )


def test_settings_patch_needs_no_generation_and_completes_guide(client, seed):
    uid = seed["learner_id"]
    categories = seed["cat_ids"][:2]
    result = client.patch(
        f"/api/users/{uid}/settings",
        headers=headers(uid),
        json={
            "interest_category_ids": categories * 2,
            "review_interval": 7,
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["interest_category_ids"] == categories
    assert result.json()["interest_guide_completed"] is True
    assert result.json()["review_interval"] == 7
    replay = client.patch(
        f"/api/users/{uid}/settings", headers=headers(uid), json={"interest_category_ids": []}
    )
    assert replay.status_code == 200
    assert replay.json()["interest_category_ids"] == []
    assert replay.json()["interest_guide_completed"] is True


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"review_interval": None},
        {"interest_category_ids": None},
        {"interest_guide_completed": None},
        {"review_interval": 0},
        {"review_interval": 21},
        {"review_interval": True},
        {"review_interval": "5"},
        {"onboarding_status": "DONE"},
        {"interest_category_ids": [], "interest_guide_completed": False},
    ],
)
def test_invalid_settings_body(client, seed, body):
    uid = seed["learner_id"]
    result = client.patch(f"/api/users/{uid}/settings", headers=headers(uid), json=body)
    assert result.status_code == 422, result.text


def test_completed_guide_cannot_be_undone(client, seed):
    uid = seed["learner_id"]
    url = f"/api/users/{uid}/settings"
    assert (
        client.patch(url, headers=headers(uid), json={"interest_guide_completed": True}).status_code
        == 200
    )
    assert (
        client.patch(
            url, headers=headers(uid), json={"interest_guide_completed": False}
        ).status_code
        == 422
    )


def test_unknown_category_rolls_back_other_changes(client, seed):
    uid = seed["learner_id"]
    url = f"/api/users/{uid}/settings"
    result = client.patch(
        url, headers=headers(uid), json={"interest_category_ids": [9999999], "review_interval": 8}
    )
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "CATEGORY_NOT_FOUND"
    assert client.get(url, headers=headers(uid)).json()["review_interval"] == 5


def test_feed_state_contract_and_preserves_unavailable_id(
    client, seed, published_content, database
):
    uid = seed["learner_id"]
    url = f"/api/users/{uid}/feed-state"
    assert client.get(url, headers=headers(uid)).json() == {
        "user_id": uid,
        "last_content_id": None,
        "resume_available": False,
        "record_generation": 0,
    }
    result = client.patch(url, headers=headers(uid, 0), json={"last_content_id": published_content})
    assert result.status_code == 200, result.text
    assert result.json()["resume_available"] is True
    assert result.json()["last_content_id"] == published_content
    database.execute(
        text("UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:id"),
        {"id": published_content},
    )
    result = client.get(url, headers=headers(uid))
    assert result.json()["last_content_id"] == published_content
    assert result.json()["resume_available"] is False
    assert database.scalar(text("SELECT count(*) FROM sasu.watch_records")) == 0


def test_feed_state_missing_file_is_unavailable_without_erasing_position(
    client, seed, published_content
):
    from app.core.config import get_settings

    uid = seed["learner_id"]
    url = f"/api/users/{uid}/feed-state"
    assert (
        client.patch(
            url, headers=headers(uid, 0), json={"last_content_id": published_content}
        ).status_code
        == 200
    )
    (get_settings().video_storage_root / "videos/test.mp4").unlink()
    result = client.get(url, headers=headers(uid))
    assert result.json()["last_content_id"] == published_content
    assert result.json()["resume_available"] is False


@pytest.mark.parametrize("generation,status", [(None, 422), (5, 409), (-1, 422)])
def test_feed_state_generation(client, seed, published_content, generation, status):
    uid = seed["learner_id"]
    result = client.patch(
        f"/api/users/{uid}/feed-state",
        headers=headers(uid, generation),
        json={"last_content_id": published_content},
    )
    assert result.status_code == status


def test_feed_rejects_private_content(client, seed, published_content, database):
    uid = seed["learner_id"]
    database.execute(
        text("UPDATE sasu.contents SET status='DRAFT' WHERE content_id=:id"),
        {"id": published_content},
    )
    result = client.patch(
        f"/api/users/{uid}/feed-state",
        headers=headers(uid, 0),
        json={"last_content_id": published_content},
    )
    assert result.status_code == 404


@pytest.mark.parametrize("suffix", ["settings", "feed-state"])
def test_user_state_access(client, seed, suffix):
    uid = seed["learner_id"]
    assert client.get(f"/api/users/{uid}/{suffix}").status_code == 422
    assert client.get(f"/api/users/{uid}/{suffix}", headers=headers(9999999)).status_code == 404
    assert (
        client.get(f"/api/users/{uid}/{suffix}", headers=headers(seed["admin_id"])).status_code
        == 200
    )


@pytest.mark.parametrize("suffix", ["settings", "feed-state"])
def test_state_read_permissions_do_not_grant_write_access(client, seed, database, suffix):
    uid, admin = seed["learner_id"], seed["admin_id"]
    other = database.scalar(
        text(
            "INSERT INTO sasu.app_users (username, display_name, role) "
            "VALUES ('other_reader', '다른 학습자', 'LEARNER') RETURNING user_id"
        )
    )
    assert client.get(f"/api/users/{uid}/{suffix}", headers=headers(other)).status_code == 404
    assert client.get(f"/api/users/{admin}/{suffix}", headers=headers(admin)).status_code == 404
    payload = {"review_interval": 3} if suffix == "settings" else {"last_content_id": 1}
    result = client.patch(f"/api/users/{uid}/{suffix}", headers=headers(admin, 0), json=payload)
    assert result.status_code == 403
