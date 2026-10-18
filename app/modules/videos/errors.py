"""영상 처리 오류. 모두 AppError라 공통 핸들러가 {"error": ...}로 응답한다.

영상 오류는 fields=["video"]를 붙여 화면이 영상 입력란 옆에 메시지를 표시할 수 있게 한다.
"""

from app.core.exceptions import AppError


class VideoError(AppError):
    status = 400
    error_code = "INVALID_REQUEST"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(self.status, self.error_code, message, fields=["video"], detail=detail)


class EmptyFile(VideoError):
    status, error_code = 400, "EMPTY_FILE"


class FileTooLarge(VideoError):
    status, error_code = 413, "FILE_TOO_LARGE"


class UnsupportedMedia(VideoError):
    """영상이 아니거나 브라우저 공통 재생이 안 되는 형식."""

    status, error_code = 415, "UNSUPPORTED_MEDIA"


class DurationOutOfRange(VideoError):
    status, error_code = 422, "VIDEO_DURATION_OUT_OF_RANGE"


class ProbeFailed(VideoError):
    """ffprobe가 파일을 해석하지 못함(손상·잘린 파일 등)."""

    status, error_code = 422, "VIDEO_PROBE_FAILED"


class ProcessingFailed(VideoError):
    """ffmpeg 정규화 실패. 서버 측 문제일 수 있어 500으로 구분한다."""

    status, error_code = 500, "VIDEO_PROCESSING_FAILED"


class MediaToolMissing(VideoError):
    status, error_code = 503, "MEDIA_TOOL_UNAVAILABLE"


class RangeNotSatisfiable(VideoError):
    status, error_code = 416, "RANGE_NOT_SATISFIABLE"

    def __init__(self, size: int) -> None:
        super().__init__("요청한 영상 범위가 파일 크기를 벗어났습니다.", detail={"size": size})
        self.size = size
