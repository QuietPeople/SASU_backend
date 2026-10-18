"""로컬 영상 저장·경로 검증과 서비스 상태 확인을 함께 제공한다."""

import os
from dataclasses import dataclass
from os import scandir
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryFile
from typing import BinaryIO
from uuid import uuid4


class EmptyUploadError(Exception):
    pass


@dataclass(frozen=True)
class StoredVideo:
    relative_path: str
    size_bytes: int


class LocalVideoStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def save(self, stream: BinaryIO) -> StoredVideo:
        """서버가 파일명을 생성한다. 임시 파일을 다 쓴 뒤 최종 경로에 배치한다."""
        self.root.mkdir(parents=True, exist_ok=True)
        name = uuid4().hex
        temporary = self.root / f"{name}.part"
        destination = self.root / f"{name}.mp4"
        try:
            size = 0
            with temporary.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    output.write(chunk)
                if size == 0:
                    raise EmptyUploadError
            os.replace(temporary, destination)
            return StoredVideo(relative_path=destination.name, size_bytes=size)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, relative_path: str) -> None:
        self.resolve_path(relative_path).unlink(missing_ok=True)

    def resolve_path(self, relative_path: str) -> Path:
        """DB에서 읽은 경로도 저장 루트 안의 상대 경로인지 확인한다."""
        if (
            not relative_path
            or "\\" in relative_path
            or PureWindowsPath(relative_path).drive
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
        ):
            raise ValueError("올바른 영상 상대 경로가 아닙니다.")
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("파일이 저장 루트를 이탈했습니다.")
        return path


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
