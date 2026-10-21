import pytest

PATH = "/api/users/2/contents/1/like"
HEADERS = {"X-Actor-Id": "2", "X-Record-Generation": "0"}


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize(
    "name,value",
    [
        ("X-Actor-Id", None),
        ("X-Actor-Id", "0"),
        ("X-Actor-Id", "-1"),
        ("X-Actor-Id", str(2**63)),
        ("X-Actor-Id", "invalid"),
        ("X-Record-Generation", None),
        ("X-Record-Generation", "-1"),
        ("X-Record-Generation", "0.5"),
        ("X-Record-Generation", str(2**31 - 1)),
        ("X-Record-Generation", "invalid"),
    ],
)
def test_invalid_headers_have_structured_errors(client, method, name, value):
    headers = HEADERS.copy()
    if value is None:
        headers.pop(name)
    else:
        headers[name] = value
    response = client.request(method, PATH, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert any(
        field["field"].lower() == f"header.{name}".lower()
        for field in response.json()["detail"]["fields"]
    )


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("parameter", ["user_id", "content_id"])
@pytest.mark.parametrize("value", ["0", "-1", str(2**63), "invalid"])
def test_invalid_path_ids_have_structured_errors(client, method, parameter, value):
    path = "/api/users/{user_id}/contents/{content_id}/like".format(
        user_id=value if parameter == "user_id" else "2",
        content_id=value if parameter == "content_id" else "1",
    )
    response = client.request(method, path, headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_unsupported_query_is_rejected(client, method):
    response = client.request(method, PATH + "?liked=true", headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == [
        {"field": "query.liked", "reason": "extra_forbidden"}
    ]


def test_openapi_registers_both_operations_and_required_headers(client):
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/api/users/{user_id}/contents/{content_id}/like"]
    for method, operation_id in (("put", "API-LIK-01"), ("delete", "API-LIK-02")):
        operation = path[method]
        assert operation["operationId"] == operation_id
        assert "requestBody" not in operation
        headers = {
            parameter["name"]: parameter
            for parameter in operation["parameters"]
            if parameter["in"] == "header"
        }
        assert headers["X-Actor-Id"]["required"]
        assert headers["X-Record-Generation"]["required"]
        assert headers["X-Record-Generation"]["schema"]["minimum"] == 0
        assert headers["X-Record-Generation"]["schema"]["maximum"] == 2**31 - 2
        assert {"200", "403", "404", "409", "422", "500"} <= set(operation["responses"])
    operation_ids = [
        operation["operationId"]
        for operations in schema["paths"].values()
        for method, operation in operations.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(operation_ids) == len(set(operation_ids))
