"""영상 처리 오류. 공통 ApiError라 {"detail": {code, message, fields}} 형식으로 응답한다.

파일 입력·검사 실패와 서버 변환·도구 오류를 코드와 HTTP 상태로 구분한다.
fields는 업로드 폼 필드 이름(file)을 가리켜 화면이 입력란 옆에 메시지를 표시할 수 있게 한다.
"""

from app.core.exceptions import ApiError


class VideoError(ApiError):
    status = 422
    error_code = "INVALID_VIDEO"
    reason = "invalid_video"

    def __init__(self, message: str, *, detail: dict | None = None) -> None:
        super().__init__(
            self.status,
            self.error_code,
            message,
            fields=[{"field": "file", "reason": self.reason}],
        )
        # 응답에는 넣지 않고 로그·테스트에서 참고하는 값(현재 길이, 허용 범위 등)
        self.detail = detail or {}


class EmptyFile(VideoError):
    status, error_code, reason = 422, "EMPTY_UPLOAD", "empty"


class FileTooLarge(VideoError):
    status, error_code, reason = 413, "FILE_TOO_LARGE", "too_large"


class UnsupportedMedia(VideoError):
    """영상이 아니거나 브라우저 공통 재생이 안 되는 형식."""

    status, error_code, reason = 415, "UNSUPPORTED_MEDIA_TYPE", "unsupported_media"


class DurationOutOfRange(VideoError):
    status, error_code, reason = 422, "VIDEO_DURATION_OUT_OF_RANGE", "duration_out_of_range"


class ProbeFailed(VideoError):
    """ffprobe가 파일을 해석하지 못함(손상·잘린 파일 등)."""

    status, error_code, reason = 422, "INVALID_VIDEO", "invalid_video"


class ProbeTimeout(ProbeFailed):
    status, error_code, reason = 422, "VIDEO_INSPECTION_TIMEOUT", "inspection_timeout"


class ProcessingFailed(VideoError):
    """ffmpeg 정규화 실패. 서버 측 문제일 수 있어 500으로 구분한다."""

    status, error_code, reason = 500, "VIDEO_PROCESSING_FAILED", "processing_failed"


class MediaToolMissing(VideoError):
    status, error_code, reason = 503, "VIDEO_PROCESSING_UNAVAILABLE", "tool_unavailable"
