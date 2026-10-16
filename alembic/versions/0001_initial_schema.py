"""Create the complete SASU schema without initial data.

Revision ID: 0001_initial_schema
Revises: None
Source: SASU_주요문서_MD/SASU_통합_DB_설계서.md (2026-10-16).
Requires PostgreSQL 16+. Runs independently of feature ORM models.
Alembic owns the transaction; no standalone SQL file or application data is loaded.
View columns and supporting index/function names are specified here where the design
leaves names open. curriculum_progress.progress_ratio uses 0~1; empty means NULL.
"""

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create 21 tables, constraints, indexes, validation triggers, functions and views."""
    op.execute(
        r"""
DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 160000 THEN
        RAISE EXCEPTION 'SASU schema requires PostgreSQL 16 or later';
    END IF;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE SCHEMA sasu
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.app_users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username varchar(32) NOT NULL UNIQUE CHECK (btrim(username) <> ''),
    display_name varchar(80) NOT NULL,
    role varchar(10) NOT NULL CHECK (role IN ('LEARNER','ADMIN')),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.app_users IS '사용자 식별. 고정 user1/admin 표시용 계정, 인증 정보 없음'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.app_users.user_id IS '사용자 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.app_users.username IS '고정 코드'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.app_users.display_name IS '표시 이름'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.app_users.role IS '로컬 역할 표시'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.app_users.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.categories (
    category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(80) NOT NULL CHECK (btrim(name) <> ''),
    group_name varchar(80),
    sort_order integer NOT NULL DEFAULT 0 CHECK (sort_order >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.categories IS '모든 기능이 공유하는 카테고리'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.category_id IS '카테고리 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.name IS '표시명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.group_name IS '대분류 표시명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.sort_order IS '표시 순서'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.categories.updated_at IS '수정 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.tags (
    tag_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name varchar(80) NOT NULL CHECK (btrim(name) <> ''),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.tags IS '검색·추천 태그'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.tags.tag_id IS '태그 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.tags.name IS '표시명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.tags.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.video_assets (
    video_asset_id uuid PRIMARY KEY,
    storage_path varchar(1024) NOT NULL UNIQUE CHECK (storage_path <> '' AND storage_path !~
        '(^/|(^|/)\.\.(/|$)|^[A-Za-z]:)' AND position(chr(92) in storage_path)=0),
    original_name varchar(255) NOT NULL,
    mime_type varchar(100) NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    duration_seconds numeric(12,3) NOT NULL CHECK (duration_seconds > 0 AND duration_seconds <
        'Infinity'::numeric),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.video_assets IS '원본 파일의 업로드·교체 관리'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.video_asset_id IS '서버 생성 UUID'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.storage_path IS '루트 기준 상대 경로'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.original_name IS '원본 파일명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.mime_type IS '서버 확인 형식'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.size_bytes IS '크기'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.duration_seconds IS '서버 측정 길이(초)'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.video_assets.created_at IS '업로드 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.contents (
    content_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_by_user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    video_asset_id uuid UNIQUE REFERENCES sasu.video_assets(video_asset_id) ON DELETE RESTRICT,
    category_id bigint REFERENCES sasu.categories(category_id) ON DELETE RESTRICT,
    title varchar(200),
    core_content text,
    source text,
    reviewed_on date,
    caution_enabled boolean NOT NULL DEFAULT false,
    caution_text text,
    status varchar(12) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PUBLISHED')),
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_contents_caution CHECK (NOT caution_enabled OR coalesce(btrim(caution_text),
        '') <> ''),
    CONSTRAINT ck_contents_published_fields CHECK (status <> 'PUBLISHED' OR (video_asset_id IS
        NOT NULL AND category_id IS NOT NULL AND coalesce(btrim(title), '') <> '' AND
        coalesce(btrim(core_content), '') <> '' AND coalesce(btrim(source), '') <> '' AND
        reviewed_on IS NOT NULL AND published_at IS NOT NULL))
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.contents IS '임시저장·공개 콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.content_id IS '전체 연결의 콘텐츠 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.created_by_user_id IS '관리자 작성자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.video_asset_id IS '현재 영상 자산; 초안 NULL'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.category_id IS '분류; 초안 NULL'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.title IS '제목'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.core_content IS '핵심 내용'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.source IS '출처 URL 또는 문헌'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.reviewed_on IS '검토일'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.caution_enabled IS '해석 주의'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.caution_text IS '관리자 주의 문구'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.status IS '공개 상태'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.published_at IS '최초 공개 시각'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.created_at IS '등록 시각'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.contents.updated_at IS '내용 수정 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.content_tags (
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    tag_id bigint NOT NULL REFERENCES sasu.tags(tag_id) ON DELETE RESTRICT,
    PRIMARY KEY (content_id, tag_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.content_tags IS '콘텐츠-태그 연결'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_tags.content_id IS '콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_tags.tag_id IS '태그'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.user_settings (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT PRIMARY KEY,
    onboarding_status varchar(12) NOT NULL DEFAULT 'PENDING' CHECK (onboarding_status IN
        ('PENDING','DONE','SKIPPED')),
    review_interval smallint NOT NULL DEFAULT 5 CHECK (review_interval BETWEEN 1 AND 20),
    last_content_id bigint REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL DEFAULT 1 CHECK (learning_epoch >= 1),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.user_settings IS '관심 안내·복기 간격·마지막 피드·초기화 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.onboarding_status IS '안내 상태'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.review_interval IS '복기 간격; 상한 제안'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.last_content_id IS 'FEED 진입만 갱신'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.learning_epoch IS '초기화 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_settings.updated_at IS '수정 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.user_interests (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    category_id bigint NOT NULL REFERENCES sasu.categories(category_id) ON DELETE RESTRICT,
    PRIMARY KEY (user_id, category_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.user_interests IS '관심 카테고리'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_interests.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.user_interests.category_id IS '카테고리'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.quizzes (
    quiz_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT UNIQUE,
    current_version_id bigint,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.quizzes IS '콘텐츠당 최대 한 개의 논리 문항'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quizzes.quiz_id IS '문항 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quizzes.content_id IS '콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quizzes.current_version_id IS '현재 버전; 초기 트랜잭션 중 NULL 허용'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quizzes.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.quiz_versions (
    quiz_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id bigint NOT NULL REFERENCES sasu.quizzes(quiz_id) ON DELETE RESTRICT,
    version_no integer NOT NULL CHECK (version_no > 0),
    question_type varchar(8) NOT NULL DEFAULT 'MCQ3' CHECK (question_type IN
        ('OX','MCQ3','MCQ4')),
    question_text text NOT NULL CHECK (btrim(question_text) <> ''),
    explanation text NOT NULL CHECK (btrim(explanation) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (quiz_id, version_no),
    UNIQUE (quiz_id, quiz_version_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.quiz_versions IS '수정하지 않는 문항 버전'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.quiz_version_id IS '버전 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.quiz_id IS '논리 문항'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.version_no IS '버전 순서'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.question_type IS '문항 형식'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.question_text IS '질문'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.explanation IS '해설'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_versions.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.quiz_options (
    option_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_version_id bigint NOT NULL REFERENCES sasu.quiz_versions(quiz_version_id) ON DELETE
        RESTRICT,
    position smallint NOT NULL CHECK (position BETWEEN 1 AND 4),
    option_text text NOT NULL CHECK (btrim(option_text) <> ''),
    is_correct boolean NOT NULL DEFAULT false,
    UNIQUE (quiz_version_id, position),
    UNIQUE (quiz_version_id, option_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.quiz_options IS '문항 버전별 보기·정답'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_options.option_id IS '보기 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_options.quiz_version_id IS '소속 버전'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_options.position IS '1부터 연속'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_options.option_text IS '보기 문장'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_options.is_correct IS '정답 여부'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.curricula (
    curriculum_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title varchar(200) NOT NULL CHECK (btrim(title) <> ''),
    description text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.curricula IS '커리큘럼 정보'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curricula.curriculum_id IS '과정 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curricula.title IS '과정명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curricula.description IS '설명'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curricula.created_at IS '생성 시각'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curricula.updated_at IS '수정 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.curriculum_items (
    curriculum_id bigint NOT NULL REFERENCES sasu.curricula(curriculum_id) ON DELETE RESTRICT,
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    position integer NOT NULL CHECK (position > 0),
    PRIMARY KEY (curriculum_id, content_id),
    UNIQUE (curriculum_id, position) DEFERRABLE INITIALLY DEFERRED
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.curriculum_items IS '과정 단계와 순서'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curriculum_items.curriculum_id IS '과정'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curriculum_items.content_id IS '영상'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.curriculum_items.position IS '단계 순서'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.watch_visits (
    visit_id uuid PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    video_asset_id uuid NOT NULL REFERENCES sasu.video_assets(video_asset_id) ON DELETE
        RESTRICT,
    context varchar(16) NOT NULL CHECK (context IN
        ('FEED','SEARCH','SAVED','CURRICULUM','REVIEW')),
    elapsed_seconds numeric(14,3) NOT NULL DEFAULT 0 CHECK (elapsed_seconds >= 0 AND
        elapsed_seconds < 'Infinity'::numeric),
    watched_ranges jsonb NOT NULL DEFAULT '[]'::jsonb CHECK
        (jsonb_typeof(watched_ranges)='array'),
    last_sequence bigint NOT NULL DEFAULT 0 CHECK (last_sequence >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.watch_visits IS '머무름 단위 검증·재전송용 보조 상태'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.visit_id IS '클라이언트 방문 UUID'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.content_id IS '영상'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.video_asset_id IS '방문 당시 자산'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.context IS '재개 위치 갱신 구분'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.elapsed_seconds IS '실제 경과 초; 배속과 별도'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.watched_ranges IS '이번 방문 구간; service 병합·검증'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.last_sequence IS '수신 순번'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_visits.created_at IS '방문 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.watch_records (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    first_played_at timestamptz NOT NULL,
    last_watched_at timestamptz NOT NULL,
    view_counted_at timestamptz,
    completed_at timestamptz,
    max_coverage_ratio numeric(9,8) NOT NULL DEFAULT 0 CHECK (max_coverage_ratio BETWEEN 0 AND
        1),
    PRIMARY KEY (user_id, content_id),
    CHECK (last_watched_at >= first_played_at)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.watch_records IS '사용자·콘텐츠별 영구 요약'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.content_id IS '영상'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.first_played_at IS '첫 실제 재생'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.last_watched_at IS '최근 실제 재생'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.view_counted_at IS '최초 3초 인정'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.completed_at IS '최초 90% 완료'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.watch_records.max_coverage_ratio IS '방문별 최고 비율 0~1; 판정은 원구간'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.content_likes (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, content_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.content_likes IS '좋아요'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_likes.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_likes.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_likes.content_id IS '콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.content_likes.created_at IS '등록 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.saved_contents (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    content_id bigint NOT NULL REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, content_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.saved_contents IS '저장 영상'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.saved_contents.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.saved_contents.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.saved_contents.content_id IS '콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.saved_contents.created_at IS '등록 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.quiz_attempts (
    attempt_id uuid PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    quiz_id bigint NOT NULL REFERENCES sasu.quizzes(quiz_id) ON DELETE RESTRICT,
    quiz_version_id bigint NOT NULL,
    context varchar(16) NOT NULL CHECK (context IN ('VIDEO_END','FEED_REVIEW','WRONG_REVIEW')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (quiz_id, quiz_version_id) REFERENCES sasu.quiz_versions (quiz_id,
        quiz_version_id) ON DELETE RESTRICT,
    UNIQUE (attempt_id, quiz_version_id)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.quiz_attempts IS '버전을 고정하는 풀이, 아직 미제출인 상태도 보존'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.attempt_id IS '클라이언트 생성; 동일 요청 재사용'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.quiz_id IS '논리 문항'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.quiz_version_id IS '노출 버전'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.context IS '풀이 경로'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_attempts.created_at IS '풀이 생성; 노출 시각 아님'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.quiz_responses (
    response_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    attempt_id uuid NOT NULL UNIQUE,
    quiz_version_id bigint NOT NULL,
    selected_option_id bigint,
    result varchar(10) NOT NULL CHECK (result IN ('CORRECT','WRONG','SKIPPED')),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (attempt_id, quiz_version_id) REFERENCES sasu.quiz_attempts (attempt_id,
        quiz_version_id) ON DELETE RESTRICT,
    FOREIGN KEY (quiz_version_id, selected_option_id) REFERENCES sasu.quiz_options
        (quiz_version_id, option_id) ON DELETE RESTRICT,
    CHECK ((result = 'SKIPPED' AND selected_option_id IS NULL) OR (result IN ('CORRECT',
        'WRONG') AND selected_option_id IS NOT NULL))
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.quiz_responses IS '풀이당 최대 한 번의 불변 응답'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.response_id IS '응답 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.attempt_id IS '풀이 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.quiz_version_id IS '선택 보기 소속 보장용 중복 키'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.selected_option_id IS '선택 보기; SKIPPED는 NULL'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.result IS '서버 판정'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.quiz_responses.submitted_at IS '제출 시각'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.wrong_answers (
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    quiz_version_id bigint NOT NULL REFERENCES sasu.quiz_versions(quiz_version_id) ON DELETE
        RESTRICT,
    status varchar(12) NOT NULL DEFAULT 'UNRESOLVED' CHECK (status IN
        ('UNRESOLVED','RESOLVED')),
    wrong_count integer NOT NULL DEFAULT 1 CHECK (wrong_count > 0),
    first_wrong_at timestamptz NOT NULL,
    last_wrong_at timestamptz NOT NULL,
    resolved_at timestamptz,
    resolved_response_id bigint REFERENCES sasu.quiz_responses(response_id) ON DELETE RESTRICT,
    PRIMARY KEY (user_id, quiz_version_id),
    CHECK ((status = 'UNRESOLVED' AND resolved_at IS NULL AND resolved_response_id IS NULL) OR
        (status = 'RESOLVED' AND resolved_at IS NOT NULL AND resolved_response_id IS NOT NULL)),
    CHECK (last_wrong_at >= first_wrong_at)
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.wrong_answers IS '사용자·문항 버전별 오답; 현재 목록은 최신 버전만'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.quiz_version_id IS '해당 오답 버전'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.status IS '현재 상태'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.wrong_count IS '누적 오답'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.first_wrong_at IS '최초 오답'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.last_wrong_at IS '최근 오답'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.resolved_at IS '해결 시각'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.wrong_answers.resolved_response_id IS '해결 정답 근거'
"""
    )
    op.execute(
        r"""
CREATE TABLE sasu.learning_events (
    event_id uuid PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES sasu.app_users(user_id) ON DELETE RESTRICT,
    learning_epoch integer NOT NULL CHECK (learning_epoch > 0),
    event_type varchar(24) NOT NULL CHECK (event_type IN
        ('QUIZ_DISPLAYED','CARD_OPENED','CARD_REVEALED','PLAYBACK_ERROR','SEARCH_EMPTY')),
    content_id bigint REFERENCES sasu.contents(content_id) ON DELETE RESTRICT,
    quiz_version_id bigint REFERENCES sasu.quiz_versions(quiz_version_id) ON DELETE RESTRICT,
    attempt_id uuid REFERENCES sasu.quiz_attempts(attempt_id) ON DELETE RESTRICT,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata)='object'),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((event_type = 'QUIZ_DISPLAYED' AND attempt_id IS NOT NULL AND content_id IS NOT NULL
        AND quiz_version_id IS NOT NULL) OR (event_type IN ('CARD_OPENED', 'CARD_REVEALED') AND
        attempt_id IS NULL AND content_id IS NOT NULL AND quiz_version_id IS NOT NULL) OR
        (event_type = 'PLAYBACK_ERROR' AND attempt_id IS NULL AND quiz_version_id IS NULL AND
        content_id IS NOT NULL) OR (event_type = 'SEARCH_EMPTY' AND attempt_id IS NULL AND
        quiz_version_id IS NULL AND content_id IS NULL))
)
"""
    )
    op.execute(
        r"""
COMMENT ON TABLE sasu.learning_events IS '실제 노출·열람·오류 이벤트'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.event_id IS '클라이언트 재전송 UUID'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.user_id IS '사용자'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.learning_epoch IS '요청 세대'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.event_type IS '노출 경로는 attempt.context'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.content_id IS '관련 콘텐츠'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.quiz_version_id IS '관련 버전'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.attempt_id IS '실제 표시된 풀이'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.metadata IS '오류 코드 등'
"""
    )
    op.execute(
        r"""
COMMENT ON COLUMN sasu.learning_events.occurred_at IS '서버 수신 시각'
"""
    )
    op.execute(
        r"""
ALTER TABLE sasu.quizzes
    ADD CONSTRAINT fk_quizzes_current_version
    FOREIGN KEY (quiz_id, current_version_id)
    REFERENCES sasu.quiz_versions (quiz_id, quiz_version_id)
    ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_categories_display ON sasu.categories (sort_order, category_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_contents_author ON sasu.contents (created_by_user_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_contents_category_status ON sasu.contents (category_id, status)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_contents_published ON sasu.contents (published_at DESC, content_id DESC)
    WHERE status = 'PUBLISHED'
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_content_tags_tag ON sasu.content_tags (tag_id, content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_user_settings_last_content ON sasu.user_settings (last_content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_user_interests_category ON sasu.user_interests (category_id, user_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_quizzes_current_version ON sasu.quizzes (current_version_id)
"""
    )
    op.execute(
        r"""
CREATE UNIQUE INDEX uq_quiz_options_one_correct ON sasu.quiz_options (quiz_version_id)
    WHERE is_correct
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_curriculum_items_content ON sasu.curriculum_items (content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_watch_visits_user_created ON sasu.watch_visits (user_id, created_at DESC)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_watch_visits_content ON sasu.watch_visits (content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_watch_visits_asset ON sasu.watch_visits (video_asset_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_watch_records_content ON sasu.watch_records (content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_watch_records_user_recent ON sasu.watch_records (user_id, last_watched_at DESC)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_content_likes_content ON sasu.content_likes (content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_saved_contents_content ON sasu.saved_contents (content_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_quiz_attempts_user_created ON sasu.quiz_attempts (user_id, created_at DESC)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_quiz_attempts_quiz_version ON sasu.quiz_attempts (quiz_id, quiz_version_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_quiz_attempts_version_context ON sasu.quiz_attempts (quiz_version_id, context)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_quiz_responses_option ON sasu.quiz_responses (quiz_version_id,
    selected_option_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_wrong_answers_version_status ON sasu.wrong_answers (quiz_version_id, status)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_wrong_answers_resolution ON sasu.wrong_answers (resolved_response_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_learning_events_user_time ON sasu.learning_events (user_id, occurred_at DESC)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_learning_events_content ON sasu.learning_events (content_id, event_type)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_learning_events_version ON sasu.learning_events (quiz_version_id)
"""
    )
    op.execute(
        r"""
CREATE INDEX ix_learning_events_attempt ON sasu.learning_events (attempt_id)
"""
    )
    op.execute(
        r"""
CREATE UNIQUE INDEX uq_learning_events_quiz_displayed ON sasu.learning_events (attempt_id)
    WHERE event_type = 'QUIZ_DISPLAYED'
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.lock_content_tags_parent() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    content_ids bigint[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        content_ids := ARRAY[NEW.content_id];
    ELSIF TG_OP = 'DELETE' THEN
        content_ids := ARRAY[OLD.content_id];
    ELSE
        content_ids := ARRAY[OLD.content_id, NEW.content_id];
    END IF;
    PERFORM c.content_id FROM sasu.contents c
    WHERE c.content_id = ANY(content_ids) ORDER BY c.content_id FOR UPDATE;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER lock_content_tags_parent
BEFORE INSERT OR UPDATE OR DELETE ON sasu.content_tags
FOR EACH ROW EXECUTE FUNCTION sasu.lock_content_tags_parent()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.check_published_content_tags() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    content_ids bigint[];
    target_id bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        content_ids := ARRAY[NEW.content_id];
    ELSIF TG_OP = 'DELETE' THEN
        content_ids := ARRAY[OLD.content_id];
    ELSE
        content_ids := ARRAY[OLD.content_id, NEW.content_id];
    END IF;
    FOR target_id IN SELECT DISTINCT id FROM unnest(content_ids) AS ids(id) ORDER BY id LOOP
        IF EXISTS (SELECT 1 FROM sasu.contents WHERE content_id = target_id AND status =
            'PUBLISHED')
           AND NOT EXISTS (SELECT 1 FROM sasu.content_tags WHERE content_id = target_id) THEN
            RAISE EXCEPTION 'Published content % requires at least one tag', target_id
                USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NULL;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE CONSTRAINT TRIGGER ck_contents_published_tags
AFTER INSERT OR UPDATE ON sasu.contents DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION sasu.check_published_content_tags()
"""
    )
    op.execute(
        r"""
CREATE CONSTRAINT TRIGGER ck_content_tags_published_tags
AFTER INSERT OR UPDATE OR DELETE ON sasu.content_tags DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION sasu.check_published_content_tags()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.check_quiz_current_version() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM sasu.quizzes WHERE quiz_id = NEW.quiz_id AND current_version_id IS
        NULL) THEN
        RAISE EXCEPTION 'Quiz % requires a current version before commit', NEW.quiz_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE CONSTRAINT TRIGGER ck_quizzes_current_version
AFTER INSERT OR UPDATE ON sasu.quizzes DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION sasu.check_quiz_current_version()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.check_quiz_options() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    target_version bigint := NEW.quiz_version_id;
    kind varchar(8);
    expected_count integer;
    actual_count integer;
    correct_count integer;
    first_position integer;
    last_position integer;
    ordered_options text[];
BEGIN
    SELECT question_type INTO kind FROM sasu.quiz_versions WHERE quiz_version_id =
        target_version;
    IF NOT FOUND THEN RETURN NULL; END IF;
    expected_count := CASE kind WHEN 'OX' THEN 2 WHEN 'MCQ3' THEN 3 WHEN 'MCQ4' THEN 4 END;
    SELECT count(*), count(*) FILTER (WHERE is_correct), min(position), max(position),
           array_agg(option_text ORDER BY position)
    INTO actual_count, correct_count, first_position, last_position, ordered_options
    FROM sasu.quiz_options WHERE quiz_version_id = target_version;
    IF actual_count <> expected_count OR correct_count <> 1
       OR first_position <> 1 OR last_position <> expected_count THEN
        RAISE EXCEPTION
            'Version % requires % consecutive options and exactly one correct answer',
            target_version, expected_count USING ERRCODE = '23514';
    END IF;
    IF kind = 'OX' AND ordered_options IS DISTINCT FROM ARRAY['O', 'X']::text[] THEN
        RAISE EXCEPTION 'OX version % requires options O, X in that order', target_version
            USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE CONSTRAINT TRIGGER ck_quiz_versions_options
AFTER INSERT ON sasu.quiz_versions DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION sasu.check_quiz_options()
"""
    )
    op.execute(
        r"""
CREATE CONSTRAINT TRIGGER ck_quiz_options_complete
AFTER INSERT ON sasu.quiz_options DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION sasu.check_quiz_options()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.reject_immutable_change() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    RAISE EXCEPTION '% rows are immutable; % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = '23514';
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER immutable_quiz_versions
BEFORE UPDATE OR DELETE ON sasu.quiz_versions
FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER immutable_quiz_options
BEFORE UPDATE OR DELETE ON sasu.quiz_options
FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER immutable_quiz_attempts
BEFORE UPDATE ON sasu.quiz_attempts
FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER immutable_quiz_responses
BEFORE UPDATE ON sasu.quiz_responses
FOR EACH ROW EXECUTE FUNCTION sasu.reject_immutable_change()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.lock_learning_epoch(target_user_id bigint, expected_epoch integer) RETURNS
    void
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    current_epoch integer;
BEGIN
    SELECT learning_epoch INTO current_epoch FROM sasu.user_settings
    WHERE user_id = target_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'User settings not found for user %', target_user_id USING ERRCODE =
            '23503';
    END IF;
    IF expected_epoch IS DISTINCT FROM current_epoch THEN
        RAISE EXCEPTION 'Stale learning epoch for user %: expected %, current %',
            target_user_id, expected_epoch, current_epoch USING ERRCODE = '23514';
    END IF;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.guard_learning_epoch() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    PERFORM sasu.lock_learning_epoch(NEW.user_id, NEW.learning_epoch);
    RETURN NEW;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.watch_visits
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.watch_records
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.content_likes
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.saved_contents
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.quiz_attempts
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.wrong_answers
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE TRIGGER a_guard_learning_epoch BEFORE INSERT OR UPDATE ON sasu.learning_events
FOR EACH ROW EXECUTE FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.validate_quiz_response() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    attempt sasu.quiz_attempts%ROWTYPE;
    correct boolean;
BEGIN
    SELECT * INTO attempt FROM sasu.quiz_attempts WHERE attempt_id = NEW.attempt_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Quiz attempt does not exist' USING ERRCODE = '23503';
    END IF;
    PERFORM sasu.lock_learning_epoch(attempt.user_id, attempt.learning_epoch);
    PERFORM 1 FROM sasu.quiz_attempts WHERE attempt_id = NEW.attempt_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Quiz attempt was reset' USING ERRCODE = '23503';
    END IF;
    IF NEW.quiz_version_id IS DISTINCT FROM attempt.quiz_version_id THEN
        RAISE EXCEPTION 'Response version differs from attempt version' USING ERRCODE = '23503';
    END IF;
    IF NEW.result <> 'SKIPPED' THEN
        SELECT is_correct INTO correct FROM sasu.quiz_options
        WHERE quiz_version_id = NEW.quiz_version_id AND option_id = NEW.selected_option_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Selected option does not belong to this version' USING ERRCODE =
                '23503';
        END IF;
        IF (NEW.result = 'CORRECT') IS DISTINCT FROM correct THEN
            RAISE EXCEPTION 'Response result does not match the selected option' USING ERRCODE =
                '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER validate_quiz_response BEFORE INSERT ON sasu.quiz_responses
FOR EACH ROW EXECUTE FUNCTION sasu.validate_quiz_response()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.validate_wrong_answer_resolution() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
BEGIN
    IF NEW.status = 'RESOLVED' AND NOT EXISTS (
        SELECT 1 FROM sasu.quiz_responses r
        JOIN sasu.quiz_attempts a ON a.attempt_id = r.attempt_id
        WHERE r.response_id = NEW.resolved_response_id AND r.result = 'CORRECT'
          AND a.user_id = NEW.user_id AND a.learning_epoch = NEW.learning_epoch
          AND r.quiz_version_id = NEW.quiz_version_id
    ) THEN
        RAISE EXCEPTION
            'Resolution requires a correct response by the same user for the same version'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER b_validate_wrong_answer_resolution BEFORE INSERT OR UPDATE ON sasu.wrong_answers
FOR EACH ROW EXECUTE FUNCTION sasu.validate_wrong_answer_resolution()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.apply_quiz_response_to_wrong_answers() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    attempt sasu.quiz_attempts%ROWTYPE;
BEGIN
    SELECT * INTO STRICT attempt FROM sasu.quiz_attempts WHERE attempt_id = NEW.attempt_id;
    IF NEW.result = 'WRONG' THEN
        INSERT INTO sasu.wrong_answers AS existing (
            user_id, learning_epoch, quiz_version_id, first_wrong_at, last_wrong_at
        ) VALUES (
            attempt.user_id, attempt.learning_epoch, NEW.quiz_version_id, NEW.submitted_at,
                NEW.submitted_at
        ) ON CONFLICT (user_id, quiz_version_id) DO UPDATE SET
            wrong_count = existing.wrong_count + 1,
            first_wrong_at = least(existing.first_wrong_at, EXCLUDED.first_wrong_at),
            last_wrong_at = greatest(existing.last_wrong_at, EXCLUDED.last_wrong_at),
            status = 'UNRESOLVED', resolved_at = NULL, resolved_response_id = NULL;
    ELSIF NEW.result = 'CORRECT' THEN
        UPDATE sasu.wrong_answers SET status = 'RESOLVED', resolved_at = NEW.submitted_at,
            resolved_response_id = NEW.response_id
        WHERE user_id = attempt.user_id AND quiz_version_id = NEW.quiz_version_id
          AND status = 'UNRESOLVED';
    END IF;
    RETURN NULL;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER apply_quiz_response_to_wrong_answers AFTER INSERT ON sasu.quiz_responses
FOR EACH ROW EXECUTE FUNCTION sasu.apply_quiz_response_to_wrong_answers()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.validate_learning_event() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    version_content bigint;
BEGIN
    IF NEW.quiz_version_id IS NOT NULL THEN
        SELECT q.content_id INTO version_content FROM sasu.quiz_versions v
        JOIN sasu.quizzes q ON q.quiz_id = v.quiz_id
        WHERE v.quiz_version_id = NEW.quiz_version_id;
        IF NOT FOUND OR NEW.content_id IS DISTINCT FROM version_content THEN
            RAISE EXCEPTION 'Learning event content differs from version content' USING ERRCODE
                = '23514';
        END IF;
    END IF;
    IF NEW.event_type = 'QUIZ_DISPLAYED' AND NOT EXISTS (
        SELECT 1 FROM sasu.quiz_attempts a WHERE a.attempt_id = NEW.attempt_id
          AND a.user_id = NEW.user_id AND a.learning_epoch = NEW.learning_epoch
          AND a.quiz_version_id = NEW.quiz_version_id
    ) THEN
        RAISE EXCEPTION 'Displayed quiz must match event user, epoch and version' USING ERRCODE
            = '23514';
    END IF;
    RETURN NEW;
END;
$$
"""
    )
    op.execute(
        r"""
CREATE TRIGGER b_validate_learning_event BEFORE INSERT OR UPDATE ON sasu.learning_events
FOR EACH ROW EXECUTE FUNCTION sasu.validate_learning_event()
"""
    )
    op.execute(
        r"""
CREATE FUNCTION sasu.reset_learning(target_user_id bigint, expected_epoch integer) RETURNS
    integer
LANGUAGE plpgsql SET search_path = pg_catalog, sasu AS $$
DECLARE
    next_epoch integer;
BEGIN
    PERFORM sasu.lock_learning_epoch(target_user_id, expected_epoch);
    DELETE FROM sasu.learning_events WHERE user_id = target_user_id;
    DELETE FROM sasu.wrong_answers WHERE user_id = target_user_id;
    DELETE FROM sasu.quiz_responses r USING sasu.quiz_attempts a
    WHERE r.attempt_id = a.attempt_id AND a.user_id = target_user_id;
    DELETE FROM sasu.quiz_attempts WHERE user_id = target_user_id;
    DELETE FROM sasu.watch_visits WHERE user_id = target_user_id;
    DELETE FROM sasu.watch_records WHERE user_id = target_user_id;
    DELETE FROM sasu.content_likes WHERE user_id = target_user_id;
    DELETE FROM sasu.saved_contents WHERE user_id = target_user_id;
    UPDATE sasu.user_settings SET learning_epoch = learning_epoch + 1,
        last_content_id = NULL, updated_at = now()
    WHERE user_id = target_user_id RETURNING learning_epoch INTO next_epoch;
    RETURN next_epoch;
END;
$$
"""
    )
    op.execute(
        r"""
COMMENT ON FUNCTION sasu.reset_learning(bigint, integer) IS
    '사용자 설정 행 잠금과 expected_epoch 확인 후 학습 기록만 삭제하고 증가한 epoch를 반환한다.'
"""
    )
    op.execute(
        r"""
CREATE VIEW sasu.content_metrics AS
WITH views AS (
    SELECT content_id, count(*) AS view_count FROM sasu.watch_records
    WHERE view_counted_at IS NOT NULL GROUP BY content_id
), likes AS (
    SELECT content_id, count(*) AS like_count FROM sasu.content_likes GROUP BY content_id
), saves AS (
    SELECT content_id, count(*) AS saved_count FROM sasu.saved_contents GROUP BY content_id
)
SELECT c.content_id, coalesce(v.view_count, 0::bigint) AS view_count,
       coalesce(l.like_count, 0::bigint) AS like_count,
       coalesce(s.saved_count, 0::bigint) AS saved_count
FROM sasu.contents c
LEFT JOIN views v ON v.content_id = c.content_id
LEFT JOIN likes l ON l.content_id = c.content_id
LEFT JOIN saves s ON s.content_id = c.content_id
"""
    )
    op.execute(
        r"""
CREATE VIEW sasu.current_wrong_answers AS
SELECT w.*, q.quiz_id, q.content_id
FROM sasu.wrong_answers w
JOIN sasu.quiz_versions v ON v.quiz_version_id = w.quiz_version_id
JOIN sasu.quizzes q ON q.quiz_id = v.quiz_id AND q.current_version_id = v.quiz_version_id
JOIN sasu.contents c ON c.content_id = q.content_id
WHERE w.status = 'UNRESOLVED' AND c.status = 'PUBLISHED'
"""
    )
    op.execute(
        r"""
CREATE VIEW sasu.first_video_responses AS
SELECT DISTINCT ON (a.user_id, a.quiz_id)
       a.user_id, a.learning_epoch, a.quiz_id, a.quiz_version_id,
       a.attempt_id, r.response_id, r.selected_option_id, r.result, r.submitted_at
FROM sasu.quiz_attempts a JOIN sasu.quiz_responses r ON r.attempt_id = a.attempt_id
WHERE a.context = 'VIDEO_END' AND r.result IN ('CORRECT', 'WRONG')
ORDER BY a.user_id, a.quiz_id, r.submitted_at, r.response_id
"""
    )
    op.execute(
        r"""
CREATE VIEW sasu.curriculum_progress AS
WITH correct_quizzes AS (
    SELECT DISTINCT a.user_id, a.quiz_id FROM sasu.quiz_attempts a
    JOIN sasu.quiz_responses r ON r.attempt_id = a.attempt_id WHERE r.result = 'CORRECT'
)
SELECT u.user_id, u.learning_epoch, c.curriculum_id,
       count(i.content_id) AS total_steps,
       count(i.content_id) FILTER (WHERE content.status = 'PUBLISHED') AS available_steps,
       count(i.content_id) FILTER (
           WHERE w.completed_at IS NOT NULL AND correct.quiz_id IS NOT NULL
       ) AS completed_steps,
       (count(i.content_id) FILTER (
           WHERE w.completed_at IS NOT NULL AND correct.quiz_id IS NOT NULL
       ))::numeric / nullif(count(i.content_id), 0) AS progress_ratio
FROM sasu.user_settings u CROSS JOIN sasu.curricula c
LEFT JOIN sasu.curriculum_items i ON i.curriculum_id = c.curriculum_id
LEFT JOIN sasu.contents content ON content.content_id = i.content_id
LEFT JOIN sasu.watch_records w ON w.user_id = u.user_id AND w.content_id = i.content_id
LEFT JOIN sasu.quizzes q ON q.content_id = i.content_id
LEFT JOIN correct_quizzes correct ON correct.user_id = u.user_id AND correct.quiz_id = q.quiz_id
GROUP BY u.user_id, u.learning_epoch, c.curriculum_id
"""
    )
    op.execute(
        r"""
COMMENT ON VIEW sasu.content_metrics IS '콘텐츠별 실제 유효 조회·좋아요·저장 건수. 캐시 없음.'
"""
    )
    op.execute(
        r"""
COMMENT ON VIEW sasu.current_wrong_answers IS
    '공개 콘텐츠의 현재 문항 버전 미해결 오답. 과거 상태는 유지.'
"""
    )
    op.execute(
        r"""
COMMENT ON VIEW sasu.first_video_responses IS
    '사용자·논리 문항별 최초 VIDEO_END 정오 응답. 건너뛰기 제외.'
"""
    )
    op.execute(
        r"""
COMMENT ON VIEW sasu.curriculum_progress IS
    '전체 편성 기준 사용자별 완료 단계와 0~1 진행률. 빈 과정은 NULL.'
"""
    )


def downgrade() -> None:
    """Remove this revision's schema objects, including any data they contain."""
    op.execute(
        r"""
DROP VIEW sasu.curriculum_progress, sasu.first_video_responses, sasu.current_wrong_answers,
    sasu.content_metrics
"""
    )
    op.execute(
        r"""
DROP TABLE sasu.learning_events, sasu.wrong_answers, sasu.quiz_responses, sasu.quiz_attempts,
    sasu.saved_contents, sasu.content_likes, sasu.watch_records, sasu.watch_visits,
    sasu.curriculum_items, sasu.curricula, sasu.quiz_options, sasu.quiz_versions, sasu.quizzes,
    sasu.user_interests, sasu.user_settings, sasu.content_tags, sasu.contents,
    sasu.video_assets, sasu.tags, sasu.categories, sasu.app_users
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.reset_learning(bigint, integer)
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.validate_learning_event()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.apply_quiz_response_to_wrong_answers()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.validate_wrong_answer_resolution()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.validate_quiz_response()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.guard_learning_epoch()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.lock_learning_epoch(bigint, integer)
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.reject_immutable_change()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.check_quiz_options()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.check_quiz_current_version()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.check_published_content_tags()
"""
    )
    op.execute(
        r"""
DROP FUNCTION sasu.lock_content_tags_parent()
"""
    )
    op.execute(
        r"""
DROP SCHEMA sasu
"""
    )
