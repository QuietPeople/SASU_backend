"""영상 업로드 허용 정책. 용량·길이는 Settings(.env)에서, 나머지는 기본값을 쓴다."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VideoPolicy:
    # 1080p H.264 60초 ≈ 40~80MB. 여유를 둔 상한 [제안]
    max_bytes: int = 200 * 1024 * 1024
    # 숏폼 기준. 15/40초 구분 없이 길이만 제한(기능 정의서 7.2 답변 6번) [제안]
    min_duration_sec: float = 1.0
    max_duration_sec: float = 180.0
    # 긴 변 기준 해상도 상한. 4K 초과는 브라우저 부담이 커서 차단 [제안]
    max_long_edge_px: int = 2160

    # 브라우저(Chrome·Edge·Safari·Firefox) 공통 재생이 되는 조합만 받는다.
    #   MP4 계열: 영상 H.264 + 음성 AAC/MP3 → MP4(faststart)로 저장
    #   WebM 계열: 영상 VP8/VP9/AV1 + 음성 Opus/Vorbis → WebM으로 저장
    mp4_video_codecs: frozenset[str] = field(default_factory=lambda: frozenset({"h264"}))
    mp4_audio_codecs: frozenset[str] = field(default_factory=lambda: frozenset({"aac", "mp3"}))
    webm_video_codecs: frozenset[str] = field(
        default_factory=lambda: frozenset({"vp8", "vp9", "av1"})
    )
    webm_audio_codecs: frozenset[str] = field(
        default_factory=lambda: frozenset({"opus", "vorbis"})
    )
    # MP4 계열인데 음성만 맞지 않으면(휴대폰 MOV의 PCM 등) 음성만 AAC로 다시 인코딩한다.
    # 영상 재인코딩보다 훨씬 가벼워 요청 안에서 처리할 수 있다.
    transcode_incompatible_audio: bool = True

    probe_timeout_sec: float = 20.0
    remux_timeout_sec: float = 120.0

    @property
    def max_megabytes(self) -> int:
        return self.max_bytes // (1024 * 1024)
