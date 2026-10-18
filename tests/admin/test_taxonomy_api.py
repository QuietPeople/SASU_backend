"""공통 분류 API의 계약·연결 보존·동시 이름 생성 정책을 PostgreSQL에서 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.modules.categories import repository as categories_repository
from app.modules.tags import repository as tags_repository


@pytest.fixture
def records(database):
    users = {}
    for role in ("ADMIN", "LEARNER"):
        users[role.lower()] = database.scalar(
            text(
                """INSERT INTO sasu.app_users (username, display_name, role)
                   VALUES (:role, :role, :role) RETURNING user_id"""
            ),
            {"role": role},
        )
    categories = [
        database.scalar(
            text("INSERT INTO sasu.categories (name) VALUES (:name) RETURNING category_id"),
            {"name": name},
        )
        for name in ("엑셀", "보고서 작성")
    ]
    content_id = database.scalar(
        text(
            """INSERT INTO sasu.contents (created_by_user_id, category_id)
               VALUES (:admin, :category) RETURNING content_id"""
        ),
        {"admin": users["admin"], "category": categories[0]},
    )
    database.execute(
        text("INSERT INTO sasu.user_interests (user_id, category_id) VALUES (:user, :category)"),
        {"user": users["learner"], "category": categories[0]},
    )
    database.commit()
    return {**users, "categories": categories, "content_id": content_id}


def headers(records):
    return {"X-Actor-Id": str(records["admin"])}


def test_empty_catalogs_are_public(client):
    assert client.get("/api/categories").json() == {"items": []}
    assert client.get("/api/tags").json() == {
        "items": [],
        "page": 1,
        "size": 20,
        "total": 0,
        "has_next": False,
    }


def test_categories_are_complete_and_ordered_by_id(client, records):
    response = client.get("/api/categories")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"category_id": records["categories"][0], "name": "엑셀"},
            {"category_id": records["categories"][1], "name": "보고서 작성"},
        ]
    }


@pytest.mark.parametrize(("path", "key"), [("categories", "category_id"), ("tags", "tag_id")])
def test_name_creation_trims_whitespace_and_reuses_same_case(client, records, path, key):
    response = client.post(f"/api/{path}", headers=headers(records), json={"name": "  Excel  "})
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "Excel"
    repeat = client.post(f"/api/{path}", headers=headers(records), json={"name": "Excel"})
    assert repeat.status_code == 200
    assert repeat.json() == created
    other_case = client.post(f"/api/{path}", headers=headers(records), json={"name": "excel"})
    assert other_case.status_code == 201
    assert other_case.json()[key] != created[key]


def test_category_rename_preserves_links_and_idempotent_timestamp(client, records, database):
    category_id = records["categories"][0]
    response = client.patch(
        f"/api/categories/{category_id}",
        headers=headers(records),
        json={"name": "  스프레드시트  "},
    )
    assert response.status_code == 200
    assert response.json() == {"category_id": category_id, "name": "스프레드시트"}
    content_category = database.scalar(
        text("SELECT category_id FROM sasu.contents WHERE content_id = :content"),
        {"content": records["content_id"]},
    )
    interest_category = database.scalar(text("SELECT category_id FROM sasu.user_interests"))
    assert content_category == interest_category == category_id
    timestamp = database.scalar(
        text("SELECT updated_at FROM sasu.categories WHERE category_id = :id"), {"id": category_id}
    )
    assert (
        client.patch(
            f"/api/categories/{category_id}",
            headers=headers(records),
            json={"name": "스프레드시트"},
        ).status_code
        == 200
    )
    assert (
        database.scalar(
            text("SELECT updated_at FROM sasu.categories WHERE category_id = :id"),
            {"id": category_id},
        )
        == timestamp
    )


def test_rename_conflict_does_not_change_existing_category(client, records):
    response = client.patch(
        f"/api/categories/{records['categories'][0]}",
        headers=headers(records),
        json={"name": "보고서 작성"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CATEGORY_NAME_CONFLICT"
    assert client.get("/api/categories").json()["items"][0]["name"] == "엑셀"


def test_rename_missing_or_invalid_id(client, records):
    for target, status in ((9999999, 404), (0, 422), (-1, 422), (2**63, 422)):
        response = client.patch(
            f"/api/categories/{target}",
            headers=headers(records),
            json={"name": "이름"},
        )
        assert response.status_code == status


@pytest.mark.parametrize("path", ["categories", "tags"])
@pytest.mark.parametrize(
    "payload",
    [
        {"name": " "},
        {"name": "가" * 31},
        {"name": None},
        {"name": 1},
        {"name": "정상", "extra": True},
        {},
    ],
)
def test_invalid_names_are_rejected(client, records, path, payload):
    response = client.post(f"/api/{path}", headers=headers(records), json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("path", ["categories", "tags"])
def test_maximum_length_is_measured_after_trimming(client, records, path):
    response = client.post(
        f"/api/{path}",
        headers=headers(records),
        json={"name": "  " + "가" * 30 + "  "},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "가" * 30


@pytest.mark.parametrize("endpoint", ["category_create", "category_rename", "tag_create"])
def test_all_catalog_writes_require_admin(client, records, endpoint):
    path = "/api/tags" if endpoint == "tag_create" else "/api/categories"
    method = client.post
    if endpoint == "category_rename":
        path += f"/{records['categories'][0]}"
        method = client.patch
    for actor_headers, status, code in (
        ({}, 422, "VALIDATION_ERROR"),
        ({"X-Actor-Id": str(records["learner"])}, 403, "ROLE_NOT_ALLOWED"),
        ({"X-Actor-Id": "9999999"}, 404, "USER_NOT_FOUND"),
    ):
        response = method(path, headers=actor_headers, json={"name": "관리자 이름"})
        assert response.status_code == status
        assert response.json()["detail"]["code"] == code


def test_tag_search_pagination_and_literal_characters(client, records):
    names = ["Excel 함수", "excel 표", "문서", "100% 실무", "a_b", "acb", "역\\슬래시"]
    tag_ids = [
        client.post("/api/tags", headers=headers(records), json={"name": name}).json()["tag_id"]
        for name in names
    ]
    first = client.get("/api/tags", params={"q": " EXCEL ", "size": 1}).json()
    assert first == {
        "items": [{"tag_id": tag_ids[0], "name": names[0]}],
        "page": 1,
        "size": 1,
        "total": 2,
        "has_next": True,
    }
    second = client.get("/api/tags", params={"q": "excel", "size": 1, "page": 2}).json()
    assert second["items"] == [{"tag_id": tag_ids[1], "name": names[1]}]
    assert second["has_next"] is False
    for query, expected in (("%", names[3]), ("_", names[4]), ("\\", names[6])):
        result = client.get("/api/tags", params={"q": query}).json()
        assert [item["name"] for item in result["items"]] == [expected]
    for params in ({"q": "결과 없음"}, {"q": "excel", "page": 10}, {"page": 10**30}):
        response = client.get("/api/tags", params=params)
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["has_next"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page": "one"},
        {"size": 0},
        {"size": 101},
        {"unknown": 1},
    ],
)
def test_invalid_tag_filters(client, params):
    response = client.get("/api/tags", params=params)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_other_endpoints_reject_unexpected_query(client, records):
    assert client.get("/api/categories?page=1").status_code == 422
    for path in ("categories", "tags"):
        response = client.post(
            f"/api/{path}?unknown=1",
            headers=headers(records),
            json={"name": "이름"},
        )
        assert response.status_code == 422


def test_tag_registration_does_not_attach_to_content(client, records, database):
    assert (
        client.post("/api/tags", headers=headers(records), json={"name": "함수"}).status_code == 201
    )
    assert database.scalar(text("SELECT count(*) FROM sasu.content_tags")) == 0


def test_tag_failure_rolls_back_new_row(client, records, database, monkeypatch):
    create_tag = tags_repository.insert_tag

    def fail_after_insert(session, name):
        create_tag(session, name)
        raise OperationalError("private SQL", {}, Exception("private connection"))

    monkeypatch.setattr(tags_repository, "insert_tag", fail_after_insert)
    response = client.post("/api/tags", headers=headers(records), json={"name": "실패한 태그"})
    assert response.status_code == 500
    assert "private" not in response.text
    assert database.scalar(text("SELECT count(*) FROM sasu.tags")) == 0


@pytest.mark.parametrize("kind", ["categories", "tags"])
def test_concurrent_create_waits_and_reuses_committed_name(postgres_engine, monkeypatch, kind):
    repository = categories_repository if kind == "categories" else tags_repository
    create = repository.insert_category if kind == "categories" else repository.insert_tag
    key = "category_id" if kind == "categories" else "tag_id"
    unique_name = "동시" + uuid4().hex[:20]
    with postgres_engine.begin() as connection:
        admin = connection.scalar(
            text(
                """INSERT INTO sasu.app_users (username, display_name, role)
                   VALUES (:name, :name, 'ADMIN') RETURNING user_id"""
            ),
            {"name": unique_name},
        )
    entered = Event()
    original_lock = repository.lock_creation

    def observe_lock(session):
        entered.set()
        original_lock(session)

    def concurrent_session():
        with Session(postgres_engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '5s'"))
            yield session

    monkeypatch.setattr(repository, "lock_creation", observe_lock)
    app.dependency_overrides[get_db] = concurrent_session
    try:
        with Session(postgres_engine) as first, TestClient(app) as http:
            original_lock(first)
            original_id = getattr(create(first, unique_name), key)
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(
                    http.post,
                    f"/api/{kind}",
                    headers={"X-Actor-Id": str(admin)},
                    json={"name": unique_name},
                )
                try:
                    assert entered.wait(timeout=5)
                    assert not pending.done()
                    first.commit()
                    response = pending.result(timeout=5)
                finally:
                    first.rollback()
            assert response.status_code == 200, response.text
            assert response.json()[key] == original_id
            assert (
                first.scalar(
                    text(f"SELECT count(*) FROM sasu.{kind} WHERE name = :name"),
                    {"name": unique_name},
                )
                == 1
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        # UUID 이름으로 이 테스트가 생성한 행만 별도 테스트 DB에서 정리한다.
        with postgres_engine.begin() as connection:
            connection.execute(
                text(f"DELETE FROM sasu.{kind} WHERE name = :name"),
                {"name": unique_name},
            )
            connection.execute(
                text("DELETE FROM sasu.app_users WHERE user_id = :user"),
                {"user": admin},
            )
