"""로컬 영상 저장소(storage/videos/) 접근.

- DB(video_assets.storage_path)에는 저장 루트 기준 상대 경로만 기록한다. 예: 2026/10/<uuid>.mp4
- 파일명은 서버가 UUID로 만들고, 업로드한 원본 파일명은 경로에 쓰지 않는다.
- 임시 파일은 같은 루트의 .tmp/에 두어 최종 이동(os.replace)이 원자적으로 끝나게 한다.
- 파일과 DB는 하나의 트랜잭션이 아니므로 호출 측이 실패 시 delete()로 보상 정리한다.
"""

import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath


class StoragePathError(ValueError):
    """루트 밖을 가리키거나 형식이 잘못된 저장 경로."""


class LocalVideoStorage:
    TMP_DIR = ".tmp"

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()

    # --- 준비·상태 -----------------------------------------------------------
    def ensure_ready(self) -> None:
        (self.root / self.TMP_DIR).mkdir(parents=True, exist_ok=True)

    def is_writable(self) -> bool:
        try:
            self.ensure_ready()
            probe = self.root / self.TMP_DIR / f"health-{uuid.uuid4().hex}"
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False

    def cleanup_stale_temp(self, older_than_sec: float = 3600) -> int:
        """업로드 도중 서버가 종료되어 남은 임시 파일을 지운다. 서버 시작 시 1회 호출."""
        tmp = self.root / self.TMP_DIR
        if not tmp.is_dir():
            return 0
        cutoff = time.time() - older_than_sec
        removed = 0
        for item in tmp.iterdir():
            try:
                if item.is_file() and item.stat().st_mtime < cutoff:
                    item.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    # --- 쓰기 ----------------------------------------------------------------
    def temp_file(self, suffix: str = "") -> Path:
        self.ensure_ready()
        return self.root / self.TMP_DIR / f"{uuid.uuid4().hex}{suffix}"

    @staticmethod
    def new_relative_path(asset_id: uuid.UUID, ext: str) -> str:
        now = datetime.now(UTC)
        return f"{now:%Y}/{now:%m}/{asset_id}{ext}"

    def commit(self, tmp_path: Path, relative_path: str) -> Path:
        """임시 파일을 최종 위치로 옮긴다. 같은 파일시스템이라 원자적이다."""
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise StoragePathError(f"이미 존재하는 경로: {relative_path}")
        os.replace(tmp_path, target)
        return target

    def delete(self, relative_path: str) -> bool:
        try:
            self.resolve(relative_path).unlink()
            return True
        except FileNotFoundError:
            return False

    # --- 읽기 ----------------------------------------------------------------
    def resolve(self, relative_path: str) -> Path:
        """상대 경로를 실제 경로로 바꾸며 ../·절대 경로·드라이브 문자·심볼릭 링크 이탈을 막는다.

        DB CHECK(video_assets.storage_path)와 별도로 파일을 열기 전에 서버에서 다시 검사한다.
        """
        rel = PurePosixPath(relative_path)
        if (
            not relative_path
            or rel.is_absolute()
            or ".." in rel.parts
            or "\\" in relative_path
            or (len(relative_path) > 1 and relative_path[1] == ":")
        ):
            raise StoragePathError(f"허용되지 않는 저장 경로: {relative_path!r}")
        full = (self.root / rel).resolve()
        if not full.is_relative_to(self.root):
            raise StoragePathError(f"영상 루트를 벗어난 경로: {relative_path!r}")
        return full

    def open_path(self, relative_path: str) -> Path | None:
        """재생용 파일 경로. 없거나 경로가 잘못되면 None(API는 404)."""
        try:
            path = self.resolve(relative_path)
        except StoragePathError:
            return None
        return path if path.is_file() else None
