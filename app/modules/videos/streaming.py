"""HTTP Range 영상 응답(공통기준 35: FastAPI가 로컬 영상 파일을 전달, 206 지원).

관리자 미리보기와 학습자 재생이 함께 쓴다. 공개 여부 확인은 호출하는 라우터 책임이다.
parse_range·iter_file은 순수 함수, video_response만 Starlette 응답을 만든다.
"""

from collections.abc import Iterator
from pathlib import Path

from .errors import RangeNotSatisfiable

READ_CHUNK = 256 * 1024


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Range 헤더 → (start, end) 포함 범위. 없거나 해석할 수 없으면 None(200 전체 응답).

    bytes=0- / bytes=100-199 / bytes=-500(마지막 500바이트)을 지원한다.
    여러 구간(쉼표)은 영상 재생에서 쓰지 않으므로 무시하고, 시작이 파일 크기 이상이면 416.
    """
    if not header:
        return None
    unit, _, spec = header.strip().partition("=")
    if unit.strip().lower() != "bytes" or not spec or "," in spec:
        return None
    first, sep, last = spec.strip().partition("-")
    if not sep:
        return None
    first, last = first.strip(), last.strip()
    try:
        if first == "":
            if not last:
                return None
            suffix = int(last)
            if suffix <= 0:
                raise RangeNotSatisfiable(size)
            start, end = max(size - suffix, 0), size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
            if last and end < start:
                return None
            end = min(end, size - 1)
    except ValueError:
        return None
    if size == 0 or start >= size:
        raise RangeNotSatisfiable(size)
    return start, end


def iter_file(path: Path, start: int, end: int, chunk: int = READ_CHUNK) -> Iterator[bytes]:
    remaining = end - start + 1
    with open(path, "rb") as file:
        file.seek(start)
        while remaining > 0:
            data = file.read(min(chunk, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def video_response(
    path: Path,
    mime_type: str,
    range_header: str | None,
    *,
    cache_control: str = "private, max-age=0, must-revalidate",
):
    from starlette.responses import Response, StreamingResponse

    stat = path.stat()
    size = stat.st_size
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime_type,
        "ETag": f'"{stat.st_mtime_ns:x}-{size:x}"',
        "Cache-Control": cache_control,
        "X-Content-Type-Options": "nosniff",
    }
    try:
        byte_range = parse_range(range_header, size)
    except RangeNotSatisfiable:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})

    if byte_range is None:
        return StreamingResponse(
            iter_file(path, 0, size - 1),
            status_code=200,
            headers={**headers, "Content-Length": str(size)},
        )
    start, end = byte_range
    return StreamingResponse(
        iter_file(path, start, end),
        status_code=206,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )
