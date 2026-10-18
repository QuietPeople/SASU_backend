def build_video_url(
    content_id: int, media_revision: str, *, preview_actor_id: int | None = None
) -> str:
    url = f"/api/contents/{content_id}/video?revision={media_revision}"
    if preview_actor_id is not None:
        url += f"&preview=true&actor_id={preview_actor_id}"
    return url
