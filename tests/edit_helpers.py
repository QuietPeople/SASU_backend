def content_edit_body(client, path, headers, body):
    response = client.get(path + "?view=editor", headers=headers)
    assert response.status_code == 200, response.text
    return {"expected_updated_at": response.json()["updated_at"], **body}


def course_edit_body(client, path, headers, body):
    response = client.get(path.removesuffix("/steps") + "?view=editor", headers=headers)
    assert response.status_code == 200, response.text
    return {"expected_updated_at": response.json()["summary"]["updated_at"], **body}
