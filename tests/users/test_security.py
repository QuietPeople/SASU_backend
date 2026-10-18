from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import ApiError, register_exception_handlers
from app.core.security import Actor, require_actor, require_admin
from app.db.session import get_db
from app.modules.users import service
from app.modules.users.models import User, UserRole


@pytest.fixture
def actors():
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {"sasu": None}},
    )
    User.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        admin = User(username="admin", display_name="관리자", role=UserRole.ADMIN)
        learner = User(username="learner", display_name="학습자", role=UserRole.LEARNER)
        session.add_all([admin, learner])
        session.flush()
        ids = {"admin": admin.user_id, "learner": learner.user_id, "missing": 999}
    try:
        yield factory, ids
    finally:
        engine.dispose()


@pytest.fixture
def client(actors):
    factory, _ = actors
    application = FastAPI()
    register_exception_handlers(application)

    def provide_session():
        with factory() as session:
            yield session

    application.dependency_overrides[get_db] = provide_session

    @application.get("/actor")
    def actor_endpoint(actor: Annotated[Actor, Depends(require_actor)]):
        return {"user_id": actor.user_id, "role": actor.role}

    @application.get("/admin")
    def admin_endpoint(user_id: Annotated[int, Depends(require_admin)]):
        return {"user_id": user_id}

    with TestClient(application) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/actor", "/admin"])
@pytest.mark.parametrize("value", [None, "0", "-1", str(2**63), "invalid"])
def test_actor_header_validation_is_preserved(client, path, value):
    headers = {} if value is None else {"X-Actor-Id": value}
    response = client.get(path, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("role", ["admin", "learner"])
def test_actor_dependency_accepts_both_roles_without_learner_settings(client, actors, role):
    _, ids = actors
    response = client.get("/actor", headers={"X-Actor-Id": str(ids[role])})
    assert response.status_code == 200
    assert response.json() == {"user_id": ids[role], "role": role.upper()}


@pytest.mark.parametrize("path", ["/actor", "/admin"])
def test_missing_actor_keeps_dependency_error_contract(client, actors, path):
    _, ids = actors
    response = client.get(path, headers={"X-Actor-Id": str(ids["missing"])})
    assert response.status_code == 404
    assert response.json() == {
        "detail": {"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
    }


def test_admin_dependency_keeps_role_restriction(client, actors):
    _, ids = actors
    response = client.get("/admin", headers={"X-Actor-Id": str(ids["learner"])})
    assert response.status_code == 403
    assert response.json() == {
        "detail": {"code": "ROLE_NOT_ALLOWED", "message": "관리자만 이용할 수 있습니다."}
    }
    response = client.get("/admin", headers={"X-Actor-Id": str(ids["admin"])})
    assert response.status_code == 200
    assert response.json() == {"user_id": ids["admin"]}


def test_service_admin_check_preserves_orm_identity_and_caller_transaction(actors):
    factory, ids = actors
    with factory() as session:
        with session.begin():
            user = session.get(User, ids["admin"])
            assert service.require_admin(session, user.user_id) is user
            assert session.in_transaction()
        assert not session.in_transaction()


@pytest.mark.parametrize(
    "role,status,code,message",
    [
        ("learner", 403, "ROLE_NOT_ALLOWED", "관리자만 수행할 수 있습니다."),
        ("missing", 404, "USER_NOT_FOUND", "행위자 사용자가 없습니다."),
    ],
)
def test_service_admin_failure_preserves_error_and_transaction(actors, role, status, code, message):
    factory, ids = actors
    with factory() as session:
        with pytest.raises(ApiError) as caught:
            with session.begin():
                service.require_admin(session, ids[role])
        assert not session.in_transaction()
    assert (caught.value.status_code, caught.value.code, caught.value.message) == (
        status,
        code,
        message,
    )
