import pytest

PATH = "/api/users/2/contents/1/saved"
HEADERS = {"X-Actor-Id": "2", "X-Record-Generation": "0"}


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize(
    "changes",
    [{"X-Actor-Id": "0"}, {"X-Record-Generation": "-1"}, {"X-Record-Generation": str(2**31 - 1)}],
)
def test_invalid_write_headers(client, method, changes):
    response = client.request(method, PATH, headers={**HEADERS, **changes})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_missing_generation_and_unknown_query(client, method):
    assert client.request(method, PATH, headers={"X-Actor-Id": "2"}).status_code == 422
    response = client.request(method, PATH + "?saved=true", headers=HEADERS)
    assert response.status_code == 422
    assert response.json()["detail"]["fields"] == [
        {"field": "query.saved", "reason": "extra_forbidden"}
    ]


@pytest.mark.parametrize(
    "query", ["page=0", "size=101", "category_id=0", "category_id=9223372036854775808", "unknown=1"]
)
def test_invalid_list_query(client, query):
    response = client.get(f"/api/users/2/saved-contents?{query}", headers={"X-Actor-Id": "2"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", "/api/users/0/contents/1/saved"),
        ("DELETE", "/api/users/2/contents/9223372036854775808/saved"),
        ("GET", "/api/users/0/saved-contents"),
    ],
)
def test_invalid_path(client, method, path):
    assert client.request(method, path, headers=HEADERS).status_code == 422


def test_openapi_documents_operations_and_temporary_integrations(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for method, operation_id in (("put", "API-SAV-01"), ("delete", "API-SAV-02")):
        operation = paths["/api/users/{user_id}/contents/{content_id}/saved"][method]
        assert operation["operationId"] == operation_id
        assert "requestBody" not in operation
        headers = {p["name"]: p for p in operation["parameters"] if p["in"] == "header"}
        assert headers["X-Actor-Id"]["required"]
        assert headers["X-Record-Generation"]["required"]
        assert operation["x-temporary-integrations"] == ["SAV-T01", "SAV-T05"]
    listing = paths["/api/users/{user_id}/saved-contents"]["get"]
    assert listing["operationId"] == "API-SAV-03"
    assert {p["name"] for p in listing["parameters"] if p["in"] == "query"} == {
        "category_id",
        "page",
        "size",
    }
    assert {p["name"] for p in listing["parameters"] if p["in"] == "header"} == {"X-Actor-Id"}
    assert listing["x-temporary-integrations"] == ["SAV-T01", "SAV-T02", "SAV-T03", "SAV-T04"]
    ids = [
        operation["operationId"]
        for methods in paths.values()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(ids) == len(set(ids))
