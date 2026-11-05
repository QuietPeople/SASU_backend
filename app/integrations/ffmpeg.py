"""ffprobe·ffmpeg 실행. 업로드 영상의 분석·정규화와 해상도 축소를 담당한다.

브라우저가 보낸 Content-Type과 확장자는 믿지 않는다.
1) 파일 앞부분 바이트로 컨테이너 계열을 먼저 거르고(텍스트·이미지·재생목록 차단)
2) ffprobe로 실제 스트림·코덱·길이를 읽는다.
"""

import json
import logging
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.modules.videos.errors import (
    MediaToolMissing,
    ProbeFailed,
    ProbeTimeout,
    ProcessingFailed,
    UnsupportedMedia,
)

# ISO BMFF(MP4/MOV) 첫 박스. 'ftyp'가 표준이고 오래된 QuickTime은 다른 박스로 시작하기도 한다.
_ISO_BMFF_FIRST_BOXES = {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"  # Matroska/WebM

logger = logging.getLogger(__name__)


def sniff_container(head: bytes) -> str:
    """파일 앞 바이트로 'isobmff' 또는 'ebml'을 돌려준다. 둘 다 아니면 UnsupportedMedia."""
    if len(head) >= 8 and head[4:8] in _ISO_BMFF_FIRST_BOXES:
        return "isobmff"
    if head.startswith(_EBML_MAGIC):
        return "ebml"
    raise UnsupportedMedia("영상 파일이 아닙니다. MP4 또는 WebM 파일을 올려 주세요.")


@dataclass(frozen=True)
class ProbeResult:
    duration_sec: float
    video_codec: str
    width: int
    height: int
    rotation: int  # 0/90/180/270. 휴대폰 세로 촬영 판별용
    audio_codec: str | None
    frame_rate: float | None
    video_stream_index: int = 0
    audio_stream_index: int | None = None
    pixel_format: str | None = None
    profile: str | None = None

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height

    @property
    def is_vertical(self) -> bool:
        return self.display_height > self.display_width


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffprobe") and shutil.which("ffmpeg"))


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MediaToolMissing(f"서버에 {name}가 설치되어 있지 않습니다.")
    return path


def _parse_rate(value: str | None) -> float | None:
    if not value or value in ("0/0", "0"):
        return None
    try:
        num, _, den = value.partition("/")
        rate = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 3) if rate > 0 else None


def _rotation(stream: dict) -> int:
    rotation = 0
    tags = stream.get("tags") or {}
    if "rotate" in tags:  # ffmpeg 5 이하
        try:
            rotation = int(tags["rotate"])
        except ValueError:
            rotation = 0
    for side_data in stream.get("side_data_list") or []:  # ffmpeg 6 이상
        if "rotation" in side_data:
            try:
                rotation = int(float(side_data["rotation"]))
            except ValueError:
                pass
    return abs(rotation) % 360


def probe(path: Path, *, timeout: float = 20.0) -> ProbeResult:
    cmd = [
        _binary("ffprobe"),
        "-v",
        "error",
        # 로컬 파일만 읽는다. MOV 외부 참조·네트워크 주소를 따라가지 않는다.
        "-protocol_whitelist",
        "file",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeTimeout("영상 검사 제한 시간을 초과했습니다.") from exc
    if proc.returncode != 0:
        raise ProbeFailed("영상 파일을 읽을 수 없습니다. 파일이 손상되었는지 확인해 주세요.")
    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeFailed("영상 분석 결과를 해석할 수 없습니다.") from exc

    streams = info.get("streams") or []
    fmt = info.get("format") or {}
    # 표지 이미지(attached_pic) 트랙은 영상 트랙으로 보지 않는다.
    videos = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos:
        raise UnsupportedMedia("영상 트랙이 없는 파일입니다.")
    video = videos[0]

    duration = None
    for candidate in (fmt.get("duration"), video.get("duration")):
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            duration = value
            break
    if duration is None:
        raise ProbeFailed("영상 길이를 측정할 수 없습니다.")

    return ProbeResult(
        duration_sec=duration,
        video_codec=(video.get("codec_name") or "").lower(),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        rotation=_rotation(video),
        audio_codec=(audios[0].get("codec_name") or "").lower() if audios else None,
        frame_rate=(
            _parse_rate(video.get("avg_frame_rate")) or _parse_rate(video.get("r_frame_rate"))
        ),
        video_stream_index=int(video["index"]),
        audio_stream_index=int(audios[0]["index"]) if audios else None,
        pixel_format=video.get("pix_fmt"),
        profile=video.get("profile"),
    )


def _stream_mapping(streams: ProbeResult) -> list[str]:
    # ffprobe에서 검사한 절대 스트림 번호를 사용한다. 표지 이미지 등은 선택하지 않는다.
    mapping = ["-map", f"0:{streams.video_stream_index}"]
    if streams.audio_stream_index is not None:
        mapping += ["-map", f"0:{streams.audio_stream_index}"]
    return mapping


def scale_and_remux(
    src: Path,
    dst: Path,
    *,
    output_format: str,
    transcode_audio: bool,
    long_edge: int,
    timeout: float,
    streams: ProbeResult,
) -> None:
    """고해상도 영상을 long_edge px 이하로 축소하며 컨테이너를 다시 쓴다.
    비율·회전 메타데이터를 유지하고 짝수 픽셀로 보정한다."""
    scale_filter = (
        f"scale='min({long_edge},iw)':'min({long_edge},ih)':"
        f"force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )
    cmd = [
        _binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-protocol_whitelist",
        "file",
        "-xerror",
        "-err_detect",
        "explode",
        "-i",
        str(src),
        *_stream_mapping(streams),
        "-map_metadata",
        "-1",
        "-vf",
        scale_filter,
    ]
    if output_format == "mp4":
        cmd += ["-c:v", "libx264", "-crf", "23", "-preset", "medium"]
        cmd += ["-c:a", "aac", "-b:a", "128k"] if transcode_audio else ["-c:a", "copy"]
        cmd += ["-movflags", "+faststart", "-f", "mp4"]
    else:
        cmd += [
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "30",
            "-b:v",
            "0",
            "-deadline",
            "good",
            "-cpu-used",
            "4",
        ]
        cmd += ["-c:a", "libopus"] if transcode_audio else ["-c:a", "copy"]
        cmd += ["-f", "webm"]
    cmd.append(str(dst))
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        dst.unlink(missing_ok=True)
        raise ProcessingFailed("영상 축소 처리 시간이 초과되었습니다.") from exc
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        logger.error("ffmpeg scale failed: %s", proc.stderr.decode(errors="replace")[-500:])
        raise ProcessingFailed("영상 해상도 축소 처리에 실패했습니다.")


def remux(
    src: Path,
    dst: Path,
    *,
    output_format: str,
    transcode_audio: bool,
    timeout: float,
    streams: ProbeResult,
) -> None:
    """영상은 복사만 하고 컨테이너를 다시 쓴다. output_format은 'mp4' 또는 'webm'."""
    cmd = [
        _binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-protocol_whitelist",
        "file",
        "-xerror",
        "-err_detect",
        "explode",
        "-i",
        str(src),
        *_stream_mapping(streams),
        # 촬영 위치(GPS)·기기 정보 등 전역 메타데이터 제거. 회전 정보는 영상 스트림에 남는다.
        "-map_metadata",
        "-1",
        "-c:v",
        "copy",
    ]
    cmd += ["-c:a", "aac", "-b:a", "128k"] if transcode_audio else ["-c:a", "copy"]
    if output_format == "mp4":
        # moov(목차)를 앞으로: 전체를 받기 전에 재생·탐색 가능(Range 스트리밍 전제)
        cmd += ["-movflags", "+faststart", "-f", "mp4"]
    else:
        cmd += ["-f", "webm"]
    cmd.append(str(dst))
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        dst.unlink(missing_ok=True)
        raise ProcessingFailed("영상 처리 시간이 초과되었습니다.") from exc
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        # 서버 경로가 담길 수 있어 응답에는 넣지 않고 로그로만 남긴다.
        logger.error("ffmpeg remux failed: %s", proc.stderr.decode(errors="replace")[-500:])
        raise ProcessingFailed("영상을 저장 형식으로 변환하지 못했습니다.")


def validate_decoding(path: Path, streams: ProbeResult, *, timeout: float) -> None:
    """저장할 영상·음성을 끝까지 디코딩한다. 파일 출력 없이 손상·시간 초과를 거절한다."""
    cmd = [
        _binary("ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-xerror",
        "-err_detect",
        "explode",
        "-protocol_whitelist",
        "file",
        "-i",
        str(path),
        *_stream_mapping(streams),
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeTimeout("영상 디코딩 검사 제한 시간을 초과했습니다.") from exc
    if proc.returncode != 0:
        raise ProbeFailed(
            "영상 또는 음성 프레임을 읽을 수 없습니다. 손상되지 않은 파일을 올려 주세요."
        )
