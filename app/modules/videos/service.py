"""영상 업로드 처리 파이프라인.

    수신 → 시그니처 확인 → 분석(ffprobe) → 정책 검사 → 정규화(ffmpeg remux) → 재분석 → 저장

이 서비스는 파일만 다루고 DB를 모른다. 결과(IngestedVideo)를 받은 콘텐츠 모듈이
video_assets 행을 만들고, DB 저장이 실패하면 discard()로 파일을 지운다.
각 단계를 메서드로 나눠 두어, 이후 비동기 작업(트랜스코딩·썸네일)으로 확장할 때 재사용한다.
"""

import hashlib
import logging
import unicodedata
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from app.integrations.ffmpeg import ProbeResult, probe, remux, scale_and_remux, sniff_container
from app.integrations.storage import LocalVideoStorage

from .errors import DurationOutOfRange, EmptyFile, FileTooLarge, ProcessingFailed, UnsupportedMedia
from .policy import VideoPolicy

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024


class OutputKind(StrEnum):
    MP4 = "mp4"
    WEBM = "webm"

    @property
    def mime(self) -> str:
        return f"video/{self.value}"

    @property
    def ext(self) -> str:
        return f".{self.value}"


@dataclass(frozen=True)
class NormalizePlan:
    """정책 검사 결과: 어떤 형식으로 저장하고 음성을 다시 인코딩할지."""

    output: OutputKind
    transcode_audio: bool = False
    scale_to: int | None = None  # BE-01: 긴 변을 이 px로 축소. None이면 remux만
    notes: tuple[str, ...] = ()


@dataclass
class IngestedVideo:
    asset_id: uuid.UUID
    storage_path: str  # → video_assets.storage_path
    original_name: str  # → video_assets.original_name
    mime_type: str  # → video_assets.mime_type
    size_bytes: int  # 저장된(정규화 후) 크기 → video_assets.size_bytes
    duration_seconds: float  # 저장본 기준 서버 측정 길이 → video_assets.duration_seconds
    upload_sha256: str  # 원본 해시. 중복 업로드 확인용(현재 DB 미저장)
    probe: ProbeResult
    notes: list[str] = field(default_factory=list)
    _storage: LocalVideoStorage | None = field(default=None, repr=False)

    @property
    def duration_decimal(self) -> Decimal:
        """DB NUMERIC(12, 3)에 맞춘 길이."""
        return Decimal(str(self.duration_seconds)).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

    def discard(self) -> None:
        """DB 저장 실패 시 보상 정리. 여러 번 불러도 안전하다."""
        if self._storage is None:
            return
        try:
            removed = self._storage.delete(self.storage_path)
        except (OSError, ValueError):
            logger.exception("DB 저장 실패 후 업로드 파일 정리에 실패했습니다.")
            return
        logger.info("discarded video %s (removed=%s)", self.storage_path, removed)

    def summary(self) -> dict:
        p = self.probe
        return {
            "video_asset_id": str(self.asset_id),
            "original_name": self.original_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "duration_sec": round(self.duration_seconds, 3),
            "width": p.display_width,
            "height": p.display_height,
            "is_vertical": p.is_vertical,
            "video_codec": p.video_codec,
            "audio_codec": p.audio_codec,
            "notes": self.notes,
        }


def sanitize_original_name(name: str | None) -> str:
    """경로 구분자·제어문자를 지우고 255자로 자른다. 표시용이며 저장 경로에는 쓰지 않는다."""
    if not name:
        return "video"
    name = unicodedata.normalize("NFC", name).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return (name or "video")[:255]


def decide_plan(container: str, info: ProbeResult, policy: VideoPolicy) -> NormalizePlan:
    """정책 검사. 통과하면 저장 계획을, 아니면 예외를 낸다."""
    if not policy.min_duration_sec <= info.duration_sec <= policy.max_duration_sec:
        raise DurationOutOfRange(
            f"영상 길이는 {policy.min_duration_sec:g}초 이상 {policy.max_duration_sec:g}초 이하만 "
            f"올릴 수 있습니다. (현재 {info.duration_sec:.1f}초)",
            detail={
                "duration_sec": round(info.duration_sec, 3),
                "min": policy.min_duration_sec,
                "max": policy.max_duration_sec,
            },
        )
    if info.width <= 0 or info.height <= 0:
        raise UnsupportedMedia("영상 해상도를 확인할 수 없습니다.")

    # BE-01: 긴 변이 정책 한계를 넘으면 재인코딩으로 자동 축소한다.
    scale_to: int | None = None
    if max(info.width, info.height) > policy.max_long_edge_px:
        scale_to = policy.max_long_edge_px

    video, audio = info.video_codec, info.audio_codec
    if video in policy.mp4_video_codecs:
        # MP4·MOV·MKV 안의 H.264 → MP4로 다시 감싼다(재인코딩 없음).
        if audio is None or audio in policy.mp4_audio_codecs:
            notes = (f"긴 변을 {scale_to}px로 축소했습니다.",) if scale_to else ()
            return NormalizePlan(OutputKind.MP4, scale_to=scale_to, notes=notes)
        if policy.transcode_incompatible_audio:
            notes_list = []
            if scale_to:
                notes_list.append(f"긴 변을 {scale_to}px로 축소했습니다.")
            notes_list.append(f"음성 코덱 {audio}를 AAC로 변환했습니다.")
            return NormalizePlan(
                OutputKind.MP4,
                transcode_audio=True,
                scale_to=scale_to,
                notes=tuple(notes_list),
            )
        raise UnsupportedMedia(f"음성 코덱 {audio}는 브라우저에서 재생할 수 없습니다.")

    if container == "ebml" and video in policy.webm_video_codecs:
        if audio is None or audio in policy.webm_audio_codecs:
            notes = (f"긴 변을 {scale_to}px로 축소했습니다.",) if scale_to else ()
            return NormalizePlan(OutputKind.WEBM, scale_to=scale_to, notes=notes)
        raise UnsupportedMedia(
            f"WebM 음성 코덱 {audio}는 지원하지 않습니다. Opus 또는 Vorbis로 저장해 주세요."
        )

    hint = (
        " H.264(MP4)로 내보낸 뒤 다시 올려 주세요."
        if video in {"hevc", "h265", "prores", "mpeg4"}
        else ""
    )
    raise UnsupportedMedia(
        f"영상 코덱 {video or '알 수 없음'}은(는) 브라우저 공통 재생을 보장하지 않습니다.{hint}",
        detail={"video_codec": video, "audio_codec": audio},
    )


class VideoIngestService:
    def __init__(self, storage: LocalVideoStorage, policy: VideoPolicy) -> None:
        self.storage = storage
        self.policy = policy

    def receive(self, src: BinaryIO) -> tuple[Path, str, bytes]:
        """업로드 스트림을 임시 파일로 복사한다. 크기 제한을 넘는 순간 중단한다."""
        tmp = self.storage.temp_file(".upload")
        digest = hashlib.sha256()
        size = 0
        head = b""
        try:
            with open(tmp, "wb") as out:
                while chunk := src.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.policy.max_bytes:
                        raise FileTooLarge(
                            f"영상은 최대 {self.policy.max_megabytes}MB까지 올릴 수 있습니다.",
                            detail={"max_bytes": self.policy.max_bytes},
                        )
                    if len(head) < 64:
                        head += chunk[: 64 - len(head)]
                    digest.update(chunk)
                    out.write(chunk)
            if size == 0:
                raise EmptyFile("빈 파일입니다.")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return tmp, digest.hexdigest(), head

    def normalize(self, src: Path, plan: NormalizePlan) -> Path:
        dst = self.storage.temp_file(plan.output.ext)
        if plan.scale_to is not None:
            scale_and_remux(
                src,
                dst,
                output_format=plan.output.value,
                transcode_audio=plan.transcode_audio,
                long_edge=plan.scale_to,
                timeout=self.policy.scale_timeout_sec,
            )
        else:
            remux(
                src,
                dst,
                output_format=plan.output.value,
                transcode_audio=plan.transcode_audio,
                timeout=self.policy.remux_timeout_sec,
            )
        return dst

    def ingest(self, src: BinaryIO, original_name: str | None) -> IngestedVideo:
        upload, sha256, head = self.receive(src)
        normalized: Path | None = None
        try:
            container = sniff_container(head)
            info = probe(upload, timeout=self.policy.probe_timeout_sec)
            plan = decide_plan(container, info, self.policy)
            normalized = self.normalize(upload, plan)
            final = probe(normalized, timeout=self.policy.probe_timeout_sec)
            _verify_normalized(info, final, plan, self.policy)  # BE-02
            asset_id = uuid.uuid4()
            relative_path = self.storage.new_relative_path(asset_id, plan.output.ext)
            stored = self.storage.commit(normalized, relative_path)
            normalized = None
            return IngestedVideo(
                asset_id=asset_id,
                storage_path=relative_path,
                original_name=sanitize_original_name(original_name),
                mime_type=plan.output.mime,
                size_bytes=stored.stat().st_size,
                duration_seconds=final.duration_sec,
                upload_sha256=sha256,
                probe=final,
                notes=list(plan.notes),
                _storage=self.storage,
            )
        finally:
            upload.unlink(missing_ok=True)
            if normalized is not None:
                normalized.unlink(missing_ok=True)


def _verify_normalized(
    original: ProbeResult,
    result: ProbeResult,
    plan: NormalizePlan,
    policy: VideoPolicy,
) -> None:
    """BE-02: 정규화 결과를 재검증한다. 유효 치수·재생 호환 코덱·길이 오차 5% 이내를 확인한다."""
    if result.width <= 0 or result.height <= 0:
        raise ProcessingFailed("정규화 후 영상 해상도를 읽을 수 없습니다.")

    if plan.output == OutputKind.MP4:
        ok_video, ok_audio = policy.mp4_video_codecs, policy.mp4_audio_codecs
    else:
        ok_video, ok_audio = policy.webm_video_codecs, policy.webm_audio_codecs

    if result.video_codec not in ok_video:
        raise ProcessingFailed(
            f"정규화 후 영상 코덱 {result.video_codec!r}이(가) 재생 허용 목록에 없습니다."
        )
    if result.audio_codec is not None and result.audio_codec not in ok_audio:
        raise ProcessingFailed(
            f"정규화 후 음성 코덱 {result.audio_codec!r}이(가) 재생 허용 목록에 없습니다."
        )

    if original.duration_sec > 0:
        delta = abs(result.duration_sec - original.duration_sec) / original.duration_sec
        if delta > 0.05:
            raise ProcessingFailed(
                f"정규화 후 영상 길이가 원본과 크게 다릅니다 "
                f"({original.duration_sec:.1f}s → {result.duration_sec:.1f}s)."
            )


def get_video_ingest_service() -> VideoIngestService:
    """FastAPI Depends용. 설정(.env)의 저장 루트와 용량·길이 제한을 요청마다 읽는다."""
    # 영상 처리 단독 테스트가 DB 설정 없이 돌도록 지연 import
    from app.core.config import get_settings

    settings = get_settings()
    policy = VideoPolicy(
        max_bytes=settings.video_max_mb * 1024 * 1024,
        min_duration_sec=settings.video_min_seconds,
        max_duration_sec=settings.video_max_seconds,
    )
    return VideoIngestService(LocalVideoStorage(settings.video_storage_root), policy)
