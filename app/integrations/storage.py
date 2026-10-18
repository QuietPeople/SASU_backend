"""로컬 영상 저장소(storage/videos/) 접근과 저장소 상태 확인.

- DB(video_assets.storage_path)에는 저장 루트 기준 상대 경로만 기록한다. 예: <영상자산 UUID>.mp4
- 파일명은 서버가 만들고, 업로드한 원본 파일명은 경로에 쓰지 않는다.
- 처리 중 임시 파일은 같은 루트에 숨김 이름(.sasu-tmp-*)으로 두어 최종 이동(os.replace)이
  원자적으로 끝나게 하고, 처리가 끝나면 바로 지운다.
- 파일과 DB는 하나의 트랜잭션이 아니므로 호출 측이 실패 시 delete()로 보상 정리한다.
"""

import os
import time
import uuid
from os import scandir
from pathlib import Path, PurePosixPath, PureWindowsPath
from tempfile import TemporaryFile

TEMP_PREFIX = ".sasu-tmp-"


class StoragePathError(ValueError):
    """루트 밖을 가리키거나 형식이 잘못된 저장 경로."""


class LocalVideoStorage:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).resolve()

    # --- 준비·정리 -----------------------------------------------------------
    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def cleanup_stale_temp(self, older_than_sec: float = 3600) -> int:
        """업로드 도중 서버가 종료되어 남은 임시 파일을 지운다. 서버 시작 시 1회 호출."""
        if not self.root.is_dir():
            return 0
        cutoff = time.time() - older_than_sec
        removed = 0
        for item in self.root.iterdir():
            try:
                if (
                    item.name.startswith(TEMP_PREFIX)
                    and item.is_file()
                    and item.stat().st_mtime < cutoff
                ):
                    item.unlink()
                    removed += 1
            except OSError:
                pass
        return removed

    # --- 쓰기 ----------------------------------------------------------------
    def temp_file(self, suffix: str = "") -> Path:
        self.ensure_root()
        return self.root / f"{TEMP_PREFIX}{uuid.uuid4().hex}{suffix}"

    @staticmethod
    def new_relative_path(asset_id: uuid.UUID, ext: str) -> str:
        return f"{asset_id.hex}{ext}"

    def commit(self, tmp_path: Path, relative_path: str) -> Path:
        """임시 파일을 최종 위치로 옮긴다. 같은 디렉터리라 원자적이다."""
        target = self.resolve_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise StoragePathError(f"이미 존재하는 경로: {relative_path}")
        os.replace(tmp_path, target)
        return target

    def delete(self, relative_path: str) -> bool:
        """파일을 지운다. 없으면 False, 경로가 잘못되면 StoragePathError(ValueError)."""
        try:
            self.resolve_path(relative_path).unlink()
            return True
        except FileNotFoundError:
            return False

    # --- 읽기 ----------------------------------------------------------------
    def resolve_path(self, relative_path: str) -> Path:
        """상대 경로를 실제 경로로 바꾸며 ../·절대 경로·드라이브 문자·심볼릭 링크 이탈을 막는다.

        DB CHECK(video_assets.storage_path)와 별도로 파일을 열기 전에 서버에서 다시 검사한다.
        """
        rel = PurePosixPath(relative_path)
        if (
            not relative_path
            or rel.is_absolute()
            or ".." in rel.parts
            or "\\" in relative_path
            or PureWindowsPath(relative_path).drive
        ):
            raise StoragePathError("올바른 영상 상대 경로가 아닙니다.")
        full = (self.root / rel).resolve()
        if not full.is_relative_to(self.root) or full == self.root:
            raise StoragePathError("파일이 저장 루트를 이탈했습니다.")
        return full


def check_video_storage_access(root: Path) -> None:
    """저장 루트의 읽기·쓰기 가능 여부를 실제 I/O로 확인한다. 검사 파일은 남기지 않는다."""
    if not root.is_dir():
        raise NotADirectoryError("Video storage is not a directory")
    with scandir(root):
        pass
    marker = b"sasu-storage-health"
    with TemporaryFile(mode="w+b", dir=root, prefix=".sasu-health-") as probe:
        probe.write(marker)
        probe.flush()
        probe.seek(0)
        if probe.read() != marker:
            raise OSError("Video storage read/write verification failed")
