from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import ActorId, OptionalActorId, reject_query_parameters
from app.api.dependencies import ResourceId as ContentId
from app.core.config import get_settings
from app.core.exceptions import ApiError, ErrorResponse
from app.db.session import get_db
from app.integrations.storage import LocalVideoStorage
from app.modules.contents import deletion_service, service, thumbnail_service, video_service
from app.modules.contents.schemas import (
    ContentCreate,
    ContentDelete,
    ContentDetail,
    ContentDetailQuery,
    ContentListQuery,
    ContentPage,
    ContentUpdate,
    EditableContent,
    ThumbnailQuery,
    VideoInfo,
    VideoPolicyOut,
    VideoQuery,
)
from app.modules.videos.service import VideoIngestService, get_video_ingest_service

router = APIRouter(
    prefix="/contents",
    tags=["contents"],
    responses={
        403: {"model": ErrorResponse, "description": "관리자 역할 필요"},
        404: {"model": ErrorResponse, "description": "행위자·대상·참조 자료 없음"},
        409: {
            "model": ErrorResponse,
            "description": "영상 revision·상태 전환 조건 불충족 또는 처리 경합",
        },
        422: {"model": ErrorResponse, "description": "요청 형식 오류"},
        500: {"model": ErrorResponse, "description": "서버 처리·DB 오류"},
    },
)


@router.get(
    "",
    response_model=ContentPage,
    operation_id="API-CNT-02",
    summary="콘텐츠 목록·검색",
    description="제목·태그·핵심 내용 순으로 검색합니다. 학습자는 공개 콘텐츠만 조회합니다.",
)
def list_contents(
    query: Annotated[ContentListQuery, Query()],
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
):
    return service.list_contents(session, actor_id, query)


@router.get(
    "/video-policy",
    response_model=VideoPolicyOut,
    operation_id="API-CNT-VIDEO-POLICY",
    dependencies=[Depends(reject_query_parameters)],
    summary="영상 업로드 허용 조건",
    description="업로드 화면 안내와 파일 선택 accept 속성에 쓰는 용량·길이·형식 기준입니다.",
)
def video_policy(
    ingest: Annotated[VideoIngestService, Depends(get_video_ingest_service)],
) -> VideoPolicyOut:
    policy = ingest.policy
    return VideoPolicyOut(
        max_bytes=policy.max_bytes,
        min_duration_sec=policy.min_duration_sec,
        max_duration_sec=policy.max_duration_sec,
        max_long_edge_px=policy.max_long_edge_px,
        accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv",
        formats=[
            "MP4·MOV·MKV (H.264 영상, AAC·MP3 음성) → MP4로 저장",
            "WebM (VP8·VP9·AV1 영상, Opus·Vorbis 음성) → WebM으로 저장",
        ],
    )


@router.get(
    "/{content_id}",
    response_model=ContentDetail | EditableContent,
    operation_id="API-CNT-03",
    summary="콘텐츠 상세·편집 정보 조회",
    description="learner는 공개 상세, editor는 관리자 편집 상세와 공개 필수값 누락을 반환합니다.",
)
def get_content(
    content_id: ContentId,
    query: Annotated[ContentDetailQuery, Query()],
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
):
    return service.get_content(
        session, actor_id, content_id, query, LocalVideoStorage(get_settings().video_storage_root)
    )


@router.post(
    "",
    response_model=EditableContent,
    status_code=201,
    operation_id="API-CNT-04",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 초안 생성",
    description="관리자 콘텐츠 초안을 저장합니다. 영상은 별도로 업로드합니다.",
)
def create_content(
    body: ContentCreate, actor_id: ActorId, session: Annotated[Session, Depends(get_db)]
):
    return service.create_content(session, actor_id, body)


@router.patch(
    "/{content_id}",
    response_model=EditableContent,
    operation_id="API-CNT-05",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 정보·태그 연결 수정",
    description=(
        "전달한 필드만 수정합니다. 태그 배열은 전체 교체하며, 공개 필수값을 깨는 수정은 취소합니다."
    ),
)
def update_content(
    content_id: ContentId,
    body: ContentUpdate,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
):
    return service.update_content(
        session, actor_id, content_id, body, LocalVideoStorage(get_settings().video_storage_root)
    )


@router.get(
    "/{content_id}/video",
    response_class=Response,
    operation_id="API-CNT-06",
    summary="영상 파일 제공·관리자 미리보기",
    description=(
        "공개 영상은 헤더 없이 제공합니다. 초안 미리보기는 preview=true와 "
        "관리자 actor_id가 필요합니다. 단일 Range를 지원하고 복수 Range는 무시합니다."
    ),
    responses={
        200: {
            "description": "전체 영상 파일 응답",
            "content": {
                "video/mp4": {"schema": {"type": "string", "format": "binary"}},
                "video/webm": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        206: {
            "description": "단일 Range 부분 응답",
            "content": {
                "video/mp4": {"schema": {"type": "string", "format": "binary"}},
                "video/webm": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        416: {
            "model": ErrorResponse,
            "description": "잘못되거나 이용 불가능한 Range; Content-Range 포함",
        },
    },
)
def get_video(
    content_id: ContentId,
    query: Annotated[VideoQuery, Query()],
    session: Annotated[Session, Depends(get_db)],
    actor_header: OptionalActorId = None,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
):
    if query.actor_id is not None and actor_header is not None and query.actor_id != actor_header:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "Query와 헤더의 행위자가 다릅니다."},
        )
    video = video_service.get_video(
        session,
        content_id,
        query,
        LocalVideoStorage(get_settings().video_storage_root),
        range_header,
    )
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
        "Content-Length": str(video.end - video.start + 1),
    }
    if video.partial:
        headers["Content-Range"] = f"bytes {video.start}-{video.end}/{video.size}"
    return StreamingResponse(
        video.chunks(),
        status_code=206 if video.partial else 200,
        media_type=video.mime_type,
        headers=headers,
        background=BackgroundTask(video.close),
    )


@router.put(
    "/{content_id}/video",
    response_model=VideoInfo,
    operation_id="API-CNT-07",
    dependencies=[Depends(reject_query_parameters)],
    summary="영상 업로드·교체",
    responses={
        413: {"model": ErrorResponse, "description": "허용 용량 초과"},
        415: {"model": ErrorResponse, "description": "영상이 아니거나 재생 불가 형식"},
        422: {
            "model": ErrorResponse,
            "description": "요청·영상 검증 실패, 길이 범위 밖, 검사 시간 초과",
        },
        500: {"model": ErrorResponse, "description": "영상 변환 또는 저장 실패"},
        503: {"model": ErrorResponse, "description": "서버 영상 처리 도구(ffmpeg) 사용 불가"},
    },
    description=(
        "영상을 저장·연결합니다. 교체에는 현재 expected_media_revision이 필요합니다. "
        "revision 불일치는 409입니다. "
        "교체 성공 후 구 파일을 삭제하며 기존 시청·풀이 기록은 유지합니다. "
        "서버가 파일 내용으로 형식을 판별하고(확장자·MIME 미사용) ffprobe로 코덱·길이·해상도를 "
        "검사한 뒤, 웹 재생용으로 정규화(MP4 faststart, 메타데이터 제거)해 저장합니다. "
        "허용 조건은 GET /api/contents/video-policy로 확인합니다."
    ),
)
async def upload_video(
    request: Request,
    content_id: ContentId,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
    ingest: Annotated[VideoIngestService, Depends(get_video_ingest_service)],
    file: Annotated[
        UploadFile,
        File(description="영상 파일 1개(MP4·MOV·MKV·WebM). 서버에서 형식·코덱·길이 검사"),
    ],
    expected_media_revision: Annotated[
        str | None, Form(min_length=1, description="최초 연결 시 생략, 교체 시 필수")
    ] = None,
):
    form = await request.form()
    if (
        set(form) - {"file", "expected_media_revision"}
        or len(form.getlist("file")) != 1
        or len(form.getlist("expected_media_revision")) > 1
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "파일 1개와 정의된 폼 필드만 허용합니다.",
            },
        )
    length = request.headers.get("content-length")
    limit = ingest.policy.max_bytes + 1024 * 1024  # 폼 필드 여유분
    if length and length.isdigit() and int(length) > limit:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            f"영상은 최대 {ingest.policy.max_megabytes}MB까지 올릴 수 있습니다.",
            fields=[{"field": "file", "reason": "too_large"}],
        )
    return await run_in_threadpool(
        video_service.upload_video,
        session,
        actor_id,
        content_id,
        file.file,
        ingest,
        file.filename or "",
        expected_media_revision,
    )


@router.put(
    "/{content_id}/thumbnail",
    status_code=204,
    operation_id="API-CNT-IMG-01",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 썸네일 등록·교체",
    description="관리자가 JPEG·PNG·WebP 이미지를 썸네일로 등록합니다. 최대 10MB.",
    responses={
        413: {"model": ErrorResponse, "description": "이미지 용량 초과"},
        415: {"model": ErrorResponse, "description": "지원하지 않는 이미지 형식"},
    },
)
async def put_thumbnail(
    content_id: ContentId,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File(description="썸네일 이미지(JPEG·PNG·WebP, 최대 10MB)")],
):
    data = await file.read()
    thumbnail_service.put_content_thumbnail(session, content_id, actor_id, data)


@router.get(
    "/{content_id}/thumbnail",
    response_class=Response,
    operation_id="API-CNT-IMG-02",
    summary="콘텐츠 썸네일 제공",
    responses={
        200: {
            "description": "썸네일 이미지",
            "content": {
                "image/jpeg": {},
                "image/png": {},
                "image/webp": {},
            },
        }
    },
)
def get_thumbnail(
    content_id: ContentId,
    query: Annotated[ThumbnailQuery, Query()],
    session: Annotated[Session, Depends(get_db)],
    actor_header: OptionalActorId = None,
):
    if query.actor_id is not None and actor_header is not None and query.actor_id != actor_header:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "Query와 헤더의 행위자가 다릅니다."},
        )
    data, mime = thumbnail_service.get_content_thumbnail(
        session,
        content_id,
        preview=query.preview,
        actor_id=query.actor_id or actor_header,
    )
    # 공개 해제 직후에도 캐시된 이미지를 새 응답처럼 재사용하지 않게 한다.
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})


@router.delete(
    "/{content_id}/thumbnail",
    status_code=204,
    operation_id="API-CNT-IMG-03",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 썸네일 삭제",
)
def delete_thumbnail(
    content_id: ContentId,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
):
    thumbnail_service.delete_content_thumbnail(session, content_id, actor_id)


@router.post(
    "/{content_id}/publish",
    response_model=EditableContent,
    operation_id="API-CNT-08",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 공개",
    description=(
        "영상·제목·카테고리·태그·핵심 내용·출처·검토일과 실제 파일을 검사합니다. "
        "최초 공개 시각은 유지합니다."
    ),
)
def publish_content(
    content_id: ContentId, actor_id: ActorId, session: Annotated[Session, Depends(get_db)]
):
    return service.publish_content(
        session, actor_id, content_id, LocalVideoStorage(get_settings().video_storage_root)
    )


@router.post(
    "/{content_id}/unpublish",
    response_model=EditableContent,
    operation_id="API-CNT-09",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠 비공개 전환",
    description=(
        "공개 콘텐츠를 PRIVATE로 전환합니다. 이력은 보존하고 학습자 조회·집계에서 제외합니다. "
        "이미 비공개이면 그대로 반환하며 초안은 409입니다. 재공개는 기존 publish API를 사용합니다."
    ),
)
def unpublish_content(
    content_id: ContentId, actor_id: ActorId, session: Annotated[Session, Depends(get_db)]
):
    return service.make_private(
        session, actor_id, content_id, LocalVideoStorage(get_settings().video_storage_root)
    )


@router.delete(
    "/{content_id}",
    status_code=204,
    operation_id="API-CNT-10",
    dependencies=[Depends(reject_query_parameters)],
    summary="콘텐츠와 연관 데이터 영구 삭제",
    description=(
        "관리자 전용입니다. confirm=true가 필요하며 콘텐츠·전체 퀴즈 버전·학습 이력·좋아요·저장·"
        "시리즈 연결을 복구할 수 없게 삭제합니다. 공유 분야·태그·사용자·시리즈는 유지합니다. "
        "DB 커밋 후 파일을 정리하며 실패한 파일 정리는 재시도 작업으로 보존합니다. "
        "동시 편집·학습 처리 중에는 409 CONTENT_IN_USE를 반환할 수 있습니다."
    ),
)
def delete_content(
    content_id: ContentId,
    body: ContentDelete,
    actor_id: ActorId,
    session: Annotated[Session, Depends(get_db)],
) -> None:
    deletion_service.delete_content(session, actor_id, content_id, body)
