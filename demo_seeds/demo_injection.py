# 데모 삽입용 스크립트. 필요 없어지면 demo_seeds/ 및 전용 테스트와 함께 제거할 수 있다.
"""원본 파일명의 demo_seeds/videos 영상을 서버 저장소로 복사한 뒤 seed.sql을 적용한다.

DB 구조는 기존 Alembic 절차로 먼저 준비한다. 서버 시작 시 자동 실행하지 않는다.
실행: docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro \
backend python -m demo_seeds.demo_injection
"""

import hashlib
import json
import shutil
import unicodedata
from pathlib import Path

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import close_database, get_engine
from app.integrations.storage import LocalVideoStorage

BUNDLE_ROOT = Path(__file__).resolve().parent


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare_videos(records: list[dict], bundle_root: Path, storage_root: Path) -> list[tuple]:
    storage = LocalVideoStorage(storage_root)
    sources = {}
    for source in (bundle_root / "videos").glob("*"):
        if not source.is_file():
            continue
        name = unicodedata.normalize("NFC", source.name)
        if name in sources:
            raise RuntimeError(f"같은 이름의 데모 영상이 여러 개입니다: {name}")
        sources[name] = source

    prepared = []
    for item in records:
        name = unicodedata.normalize("NFC", item["original_name"])
        source = sources.get(name)
        if (
            source is None
            or source.stat().st_size != item["size_bytes"]
            or file_digest(source) != item["sha256"]
        ):
            raise RuntimeError(f"데모 영상이 없거나 SQL과 다릅니다: {name}")
        prepared.append((source, storage.resolve_path(item["storage_path"]), item["sha256"]))
    return prepared


def verify_stored_videos(connection, storage_root: Path) -> None:
    """현재 콘텐츠에 연결된 파일을 DB 기준으로 확인한다. 교체 전 자산은 제외한다."""
    storage = LocalVideoStorage(storage_root)
    rows = connection.execute(
        text(
            "SELECT c.content_id, a.storage_path, a.size_bytes "
            "FROM sasu.contents c JOIN sasu.video_assets a USING (video_asset_id) "
            "ORDER BY c.content_id"
        )
    ).mappings()
    problems = []
    for row in rows:
        reason = None
        try:
            path = storage.resolve_path(row["storage_path"])
            if not path.is_file():
                reason = "파일이 없습니다."
            elif path.stat().st_size != row["size_bytes"]:
                reason = f"파일 크기가 DB 기록({row['size_bytes']}바이트)과 다릅니다."
            else:
                with path.open("rb"):
                    pass
        except (OSError, RuntimeError, ValueError):
            reason = "저장 경로 또는 파일 접근 권한을 확인해 주세요."
        if reason:
            problems.append(f"콘텐츠 {row['content_id']} / {row['storage_path']}: {reason}")
    if problems:
        raise RuntimeError(
            f"서버 영상 확인 실패 ({storage_root}):\n- "
            + "\n- ".join(problems)
            + "\n현재 DB에 연결된 서버 영상을 확인해 주세요. 기존 파일은 자동 복구하지 않습니다."
        )


def apply_demo_seed(engine, bundle_root: Path, storage_root: Path) -> int:
    sql = (bundle_root / "seed.sql").read_text()
    records = json.loads(sql.split("$sasu_demo_data$")[1])["contents"]
    created = []
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(2026102901)"))
            existing = connection.scalar(
                text(
                    "SELECT count(*) FROM sasu.video_assets "
                    "WHERE video_asset_id = ANY(CAST(:asset_ids AS uuid[]))"
                ),
                {"asset_ids": [item["video_asset_id"] for item in records]},
            )
            if existing:
                # 영상은 유지하고 미적용 학습 데모만 SQL에서 보강한다. 영상 일부만 있으면 거부한다.
                connection.exec_driver_sql(sql, execution_options={"no_parameters": True})
                verify_stored_videos(connection, storage_root)
                return 0

            prepared = prepare_videos(records, bundle_root, storage_root)
            for source, destination, digest in prepared:
                if destination.exists():
                    if not destination.is_file() or file_digest(destination) != digest:
                        raise RuntimeError(f"기존 서버 영상과 충돌합니다: {destination.name}")
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as output:
                    created.append(destination)
                    with source.open("rb") as input_file:
                        shutil.copyfileobj(input_file, output)
            connection.exec_driver_sql(sql, execution_options={"no_parameters": True})
            verify_stored_videos(connection, storage_root)
        return len(created)
    except BaseException:
        # 이번 호출에서 만든 사본만 정리한다. 기존 서버 파일과 배포 원본은 유지한다.
        for path in created:
            path.unlink(missing_ok=True)
        raise


def main() -> None:
    try:
        count = apply_demo_seed(get_engine(), BUNDLE_ROOT, get_settings().video_storage_root)
        print(f"데모 seed 처리 완료: 서버 영상 {count}개 복사. 이미 적용된 데이터는 유지합니다.")
    except RuntimeError as exc:
        raise SystemExit(f"데모 seed 처리 중단: {exc}") from None
    finally:
        close_database()


if __name__ == "__main__":
    main()
