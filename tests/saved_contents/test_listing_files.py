import pytest

from app.integrations.storage import LocalVideoStorage
from app.modules.contents import repository as contents_repository
from app.modules.contents.models import Content, VideoAsset
from app.modules.videos import availability


@pytest.mark.parametrize("file_state", ["missing", "size_mismatch"])
def test_unavailable_file_stays_in_list_but_playback_returns_404(api_context, file_state):
    ctx = api_context
    assert ctx.client.put(ctx.path, headers=ctx.headers).status_code == 200
    video_path = f"/api/contents/{ctx.contents[0]}/video"
    assert ctx.client.get(video_path).status_code == 200
    with ctx.session.begin():
        content = ctx.session.get(Content, ctx.contents[0])
        asset = ctx.session.get(VideoAsset, content.video_asset_id)
        path = ctx.storage.resolve_path(asset.storage_path)
        if file_state == "missing":
            path.unlink()
        else:
            path.write_bytes(b"short")

    response = ctx.client.get(ctx.list_path, params={"size": 10}, headers=ctx.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["page"], data["size"], data["total"], data["has_next"]) == (1, 10, 1, False)
    assert [item["content"]["content_id"] for item in data["items"]] == [ctx.contents[0]]
    assert data["items"][0]["content"]["saved"] is True
    playback = ctx.client.get(video_path)
    assert playback.status_code == 404
    assert playback.json()["detail"]["code"] == "VIDEO_NOT_FOUND"
    assert ctx.client.get(ctx.list_path, headers=ctx.headers).json()["total"] == 1


def test_listing_never_checks_storage_and_enriches_only_requested_page(api_context, monkeypatch):
    ctx = api_context
    for content_id in ctx.contents:
        response = ctx.client.put(
            f"/api/users/{ctx.learner}/contents/{content_id}/saved", headers=ctx.headers
        )
        assert response.status_code == 200

    def unexpected_file_check(*args, **kwargs):
        pytest.fail("저장 목록 조회에서 영상 파일 상태를 확인했습니다.")

    monkeypatch.setattr(availability, "is_video_available", unexpected_file_check)
    monkeypatch.setattr(LocalVideoStorage, "resolve_path", unexpected_file_check)
    original = contents_repository.load_presentations
    loaded_ids = []

    def load_page(session, contents, user_id):
        loaded_ids.extend(content.content_id for content in contents)
        return original(session, contents, user_id)

    monkeypatch.setattr(contents_repository, "load_presentations", load_page)
    response = ctx.client.get(ctx.list_path, params={"page": 2, "size": 1}, headers=ctx.headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["page"], data["size"], data["total"], data["has_next"]) == (2, 1, 3, True)
    assert loaded_ids == [item["content"]["content_id"] for item in data["items"]]
    assert len(loaded_ids) == 1
