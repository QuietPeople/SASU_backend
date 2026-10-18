import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.db.base import Base
from app.db.models import load_models
from app.db.session import get_db
from app.modules.categories.models import Category
from app.modules.contents.models import Content, ContentTag
from app.modules.tags.models import Tag
from app.modules.users.models import User, UserRole

RESOURCES = [("categories", Category, "category_id"), ("tags", Tag, "tag_id")]


@pytest.fixture
def reference_context(monkeypatch):
    load_models()
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"sasu": None}},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        admin = User(username="admin", display_name="관리자", role=UserRole.ADMIN)
        learner = User(username="learner", display_name="학습자", role=UserRole.LEARNER)
        session.add_all([admin, learner])
        session.flush()
        ids = {"admin": admin.user_id, "learner": learner.user_id}

    def provide_session():
        with factory() as session:
            yield session

    monkeypatch.setitem(main.app.dependency_overrides, get_db, provide_session)
    client = TestClient(main.app)
    try:
        yield client, factory, ids
    finally:
        client.close()
        engine.dispose()


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
def test_create_trims_name_and_reuses_existing_id(reference_context, resource, model, id_field):
    client, factory, ids = reference_context
    headers = {"X-Actor-Id": str(ids["admin"])}
    first = client.post(f"/api/{resource}", json={"name": "  엑셀  "}, headers=headers)
    assert first.status_code == 201, first.text
    second = client.post(f"/api/{resource}", json={"name": "엑셀"}, headers=headers)
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["name"] == "엑셀"
    assert first.json()[id_field] > 0
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
def test_name_matching_preserves_case_and_final_db_length(
    reference_context, resource, model, id_field
):
    client, factory, ids = reference_context
    headers = {"X-Actor-Id": str(ids["admin"])}
    names = ["SQL", "sql", "이" * 80]
    for name in names:
        response = client.post(f"/api/{resource}", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        assert response.json()["name"] == name
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == len(names)


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
def test_public_list_and_empty_results(reference_context, resource, model, id_field):
    client, factory, ids = reference_context
    empty = client.get(f"/api/{resource}")
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    with factory() as session, session.begin():
        session.add_all([model(name="Z"), model(name="A")])
    response = client.get(f"/api/{resource}")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["Z", "A"]
    assert all(set(item) == {id_field, "name"} for item in response.json()["items"])


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
@pytest.mark.parametrize("actor,status", [("learner", 403), ("missing", 404), ("none", 422)])
def test_registration_requires_existing_admin(
    reference_context, resource, model, id_field, actor, status
):
    client, factory, ids = reference_context
    headers = {} if actor == "none" else {"X-Actor-Id": str(ids.get(actor, 999))}
    response = client.post(f"/api/{resource}", json={"name": "새 이름"}, headers=headers)
    assert response.status_code == status
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": "  "},
        {"name": None},
        {"name": 123},
        {"name": "이" * 81},
        {"name": "이름", "extra": True},
    ],
)
def test_invalid_registration_leaves_no_rows(reference_context, resource, model, id_field, body):
    client, factory, ids = reference_context
    response = client.post(f"/api/{resource}", json=body, headers={"X-Actor-Id": str(ids["admin"])})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
def test_existing_duplicate_rows_reuse_lowest_id(reference_context, resource, model, id_field):
    client, factory, ids = reference_context
    with factory() as session, session.begin():
        rows = [model(name="동일 이름"), model(name="동일 이름")]
        session.add_all(rows)
        session.flush()
        first_id = min(getattr(row, id_field) for row in rows)
    response = client.post(
        f"/api/{resource}",
        json={"name": "동일 이름"},
        headers={"X-Actor-Id": str(ids["admin"])},
    )
    assert response.status_code == 200
    assert response.json()[id_field] == first_id
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == 2


def test_tag_search_pagination_and_literal_wildcards(reference_context):
    client, factory, ids = reference_context
    names = ["SQL", "sql", "SQL%", "SQL_", "SQL\\", "엑셀"]
    with factory() as session, session.begin():
        session.add_all(Tag(name=name) for name in names)
    response = client.get("/api/tags", params={"q": "  sql  ", "page": 1, "size": 2})
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["items"]] == names[:2]
    assert (body["page"], body["size"], body["total"], body["has_next"]) == (1, 2, 5, True)
    for query in ["%", "_", "\\"]:
        result = client.get("/api/tags", params={"q": query}).json()
        assert [item["name"] for item in result["items"]] == ["SQL" + query]
        assert result["total"] == 1
    final = client.get("/api/tags", params={"q": "sql", "page": 3, "size": 2}).json()
    assert len(final["items"]) == 1 and final["has_next"] is False
    beyond = client.get("/api/tags", params={"q": "sql", "page": 4, "size": 2}).json()
    assert beyond["items"] == [] and beyond["total"] == 5 and beyond["has_next"] is False
    assert client.get("/api/tags", params={"q": "없는 이름"}).json()["total"] == 0


@pytest.mark.parametrize(
    "path",
    ["/api/categories?page=1", "/api/tags?page=0", "/api/tags?size=101", "/api/tags?unknown=value"],
)
def test_query_contract_rejects_invalid_fields(reference_context, path):
    client, factory, ids = reference_context
    response = client.get(path)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("resource,model,id_field", RESOURCES)
@pytest.mark.parametrize("event_name", ["after_flush", "before_commit"])
def test_write_failure_rolls_back_without_exposing_database_error(
    reference_context, resource, model, id_field, event_name
):
    client, factory, ids = reference_context

    def fail(*args, **kwargs):
        raise SQLAlchemyError("private database detail")

    event.listen(Session, event_name, fail)
    try:
        response = client.post(
            f"/api/{resource}",
            json={"name": "저장 실패"},
            headers={"X-Actor-Id": str(ids["admin"])},
        )
    finally:
        event.remove(Session, event_name, fail)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_ERROR"
    assert "private database detail" not in response.text
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_registered_category_and_tag_connect_to_content(reference_context):
    client, factory, ids = reference_context
    headers = {"X-Actor-Id": str(ids["admin"])}
    category = client.post("/api/categories", json={"name": "업로드 분류"}, headers=headers).json()
    tag = client.post("/api/tags", json={"name": "업로드 태그"}, headers=headers).json()
    response = client.post(
        "/api/contents",
        json={
            "title": "새 콘텐츠",
            "category_id": category["category_id"],
            "tag_ids": [tag["tag_id"]],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    content = response.json()["detail"]["content"]
    assert content["category"] == category and content["tags"] == [tag]
    with factory() as session:
        assert session.get(Content, content["content_id"]).category_id == category["category_id"]
        assert session.get(ContentTag, (content["content_id"], tag["tag_id"])) is not None


def test_reference_apis_are_registered_in_openapi(reference_context):
    client, factory, ids = reference_context
    paths = client.get("/openapi.json").json()["paths"]
    for resource, suffix in [("categories", "CAT"), ("tags", "TAG")]:
        assert paths[f"/api/{resource}"]["get"]["operationId"] == f"API-{suffix}-01"
        post = paths[f"/api/{resource}"]["post"]
        assert post["operationId"] == f"API-{suffix}-02"
        assert {"200", "201"}.issubset(post["responses"])
