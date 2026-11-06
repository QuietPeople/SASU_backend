# SASU Backend

SASU의 학습자·관리자 기능을 위한 백엔드 저장소입니다.

**공통 기반과 기능별 모듈을 분리하는 구조**를 사용합니다. `app/modules/` 아래에 기능별 폴더를 하나씩 추가하고, 해당 기능의 라우터·서비스·CRUD·스키마·모델을 그 안에 모읍니다.

현재 다음 기능을 구현했습니다.

- 콘텐츠 검색·상세·등록·수정·공개, 영상 업로드·교체·부분 재생
- 카테고리·태그 관리, 퀴즈 등록·버전 관리, 시리즈 편성·진행률
- 사용자 설정·학습 기록 초기화, 좋아요·저장·시청 기록
- 개인화 피드, 퀴즈 풀이·응답, 오답 복습·플래시카드·학습 이벤트
- 학습자 대시보드, 관리자 통계, DB·영상 저장소 상태 확인

현재 사용자 구분은 `X-Actor-Id`를 사용하는 목업 방식입니다. 로그인·회원가입·JWT 인증은 구현 범위에 포함되지 않습니다. API별 요청·응답은 실행 중인 Swagger에서 확인합니다.

DB 구조는 Alembic으로 적용하며 데이터는 자동 삽입하지 않습니다. 데모 데이터·영상 준비 방법은 [데모 적용 안내](demo_seeds/README.md)를 참고합니다.

## 프론트 직접 연결과 CORS

기본 허용 origin은 `http://127.0.0.1:5173`과 `http://localhost:5173`입니다.
다른 주소를 쓰면 백엔드 `.env`에 `CORS_ORIGINS=["https://실제-프론트-주소"]`처럼
경로 없는 origin의 JSON 배열을 지정하고 `docker compose up -d backend`로 적용합니다.
개발 DB나 볼륨을 삭제할 필요는 없습니다. 쿠키 인증은 사용하지 않습니다.

`GET`, `POST`, `PUT`, `PATCH`, `DELETE`와 `X-Actor-Id`, `X-Record-Generation`,
`Content-Type`, 영상의 `Range` 헤더를 허용합니다. Vite의 `/api` 프록시는 같은 origin
요청이므로 프록시 성공만으로 CORS를 확인할 수 없습니다. Git Bash에서 직접 preflight를
확인하려면 다음 요청의 `Access-Control-Allow-Origin`과 허용 메서드·헤더를 확인합니다.

```bash
curl -i -X OPTIONS 'http://127.0.0.1:8000/api/users/1/feed' \
  -H 'Origin: http://127.0.0.1:5173' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-Actor-Id,X-Record-Generation,Content-Type'
```

## 디렉터리 구조

```text
SASU_backend/
├── app/
│   ├── main.py             # FastAPI 앱·CORS·시작 및 종료 처리
│   ├── api/                # 공통 요청 규격·의존성·라우터 등록
│   ├── core/               # 환경 설정·목업 역할 확인·공통 오류
│   ├── db/                 # DB 세션·ORM 모델 등록
│   ├── modules/            # 콘텐츠·사용자·학습·복습·통계 등 기능별 모듈
│   ├── integrations/       # 영상 저장소·ffmpeg/ffprobe 실행
│   └── jobs/               # 예약 디렉터리
├── alembic/                # 전체 DB 구조 생성·변경 이력
├── scripts/                # DB 연결 확인 등 관리 명령
├── tests/                  # 기능별 단위·API·PostgreSQL 통합 테스트
├── demo_seeds/
│   ├── seed.sql            # 기본 계정·콘텐츠·퀴즈·시리즈·가상 학습 기록
│   ├── demo_injection.py   # 명시적으로 실행하는 데모 삽입 도구
│   ├── videos/             # Git에 포함된 데모 원본 영상
│   └── thumbnails/         # 영상별 첫 프레임 JPEG 썸네일
├── storage/videos/         # Docker 밖에서 실행할 때의 기본 영상 폴더, Git 제외
├── requirements.txt        # 직접·하위 의존성 버전
├── pyproject.toml          # 코드 검사·테스트 설정
├── Dockerfile
├── compose.yaml
└── .env.example
```

주요 모듈은 `contents`, `videos`, `categories`, `tags`, `users`, `likes`, `saved_contents`, `watch_records`, `feeds`, `questions`, `attempts`, `responses`, `reviews`, `events`, `curricula`, `dashboard`, `statistics`, `admin`, `system`입니다. `videos`처럼 HTTP 라우터 없이 내부 처리를 담당하는 모듈도 있습니다.

## 공통 디렉터리 역할

| 디렉터리 | 역할 |
|---|---|
| `app/api/` | 모듈의 라우터를 통합합니다. 개별 기능의 API 코드는 해당 모듈의 `router.py`에 둡니다. |
| `app/core/` | 환경 설정·공통 오류·목업 사용자 및 역할 확인을 담당합니다. `security.py`는 사용자 ID로 역할을 확인하며 로그인·JWT 인증을 제공하지 않습니다. |
| `app/db/` | 동기 DB 엔진·요청별 세션·ORM 공통 Base를 관리합니다. 개별 테이블 모델은 각 모듈의 `models.py`에 작성하고, `app/db/models.py`에서 등록합니다. |
| `app/modules/` | 구현된 기능별 라우터·서비스·저장소·스키마·DB 정의를 관리합니다. 관리자·학습자가 함께 쓰는 기능도 같은 모듈을 공유하며 필요한 파일만 구성합니다. |
| `app/integrations/` | 파일 저장소나 외부 API에 접근하는 코드를 둡니다. Compose에서는 `video_data`·`image_data` 볼륨을 사용하며, 컨테이너 안의 파일 저장소로 접근합니다. |
| `app/jobs/` | 향후 백그라운드 작업을 위한 예약 위치입니다. 현재 조회수·좋아요·저장 수는 DB 뷰에서 집계합니다. |
| `alembic/` | 전체 DB 초기 구조와 후속 변경 이력을 관리·적용합니다. 초기 이력은 기능별 ORM 모델 없이 실행할 수 있습니다. |
| `scripts/` | 직접 실행하는 관리 명령을 둡니다. `check_db.py`는 현재 설정의 DB에 `SELECT 1`을 실행하고 연결을 정리합니다. 데모 삽입 도구는 `demo_seeds/`에 있습니다. |
| `tests/` | 공통 기반 테스트와 모듈별 테스트를 둡니다. 기본 테스트는 대역·임시 파일·메모리 SQLite 등을 사용합니다. PostgreSQL 통합 테스트는 별도 활성화 조건과 fixture의 데이터 정리 방식을 확인한 후 실행합니다. |
| `storage/videos/` | Docker 밖에서 실행할 때의 기본 영상 폴더입니다. Compose에서는 호스트 폴더 대신 `video_data`를 `/app/storage/videos`에 연결합니다. DB에는 저장 루트 기준 상대 경로를 기록합니다. |

## 모듈 내부 역할

| 파일 | 담당할 내용 |
|---|---|
| `router.py` | HTTP 입력·응답 연결과 서비스 호출 |
| `schemas.py` | Pydantic 요청·응답 정의와 필드 검증 |
| `service.py` | 업무 규칙, 여러 DB 작업을 묶는 트랜잭션 관리 |
| `repository.py` | **CRUD(Create·Read·Update·Delete)**: DB 생성·조회·수정·삭제 쿼리. 기존 `crud.py`에 두던 DB 접근 역할이며 트랜잭션 커밋은 서비스에서 관리 |
| `models.py` | 해당 모듈이 소유하는 SQLAlchemy 테이블 정의 |

DB 작업이 있는 기능의 기본 호출 흐름은 다음과 같습니다.

```text
HTTP 요청
  → router.py       요청 연결·schemas.py의 입력 검증
  → service.py      업무 규칙 확인·트랜잭션 관리
  → repository.py   models.py를 사용한 DB CRUD
  → DB

처리 결과 → service.py → router.py → schemas.py의 응답 구조 → HTTP 응답
```

예를 들어 콘텐츠 공개 조건 확인은 `contents/service.py`, 콘텐츠 조회·수정 쿼리는 `contents/repository.py`, 공개 요청·응답 필드는 `contents/schemas.py`에 작성합니다. `repository.py`에 공개 정책을 섞거나 `router.py`에서 채점·집계 같은 업무 처리를 직접 구현하지 않습니다.

## 새 모듈을 추가하는 방법

`app/modules/<기능명>/` 아래에 필요한 파일만 추가합니다. HTTP 요청을 받으면 `router.py`를 만들고 `app/api/router.py`에 등록합니다. 서비스는 처리 흐름과 트랜잭션을 관리하고, 저장소는 DB 조회·저장을 담당합니다.

현재 DB 접근은 ORM 모델, SQLAlchemy Core 테이블, SQL을 함께 사용합니다. 다른 기능이 소유한 정의는 해당 모듈에서 가져오며, ORM 모델을 추가한 경우 `app/db/models.py`의 등록 대상을 확인합니다. 기능별 테스트도 함께 작성합니다.

DB 전체 구조는 Alembic이 관리합니다. 기능별 모델을 모두 만들거나 `create_all()`로 테이블을 생성할 필요는 없습니다. 모델·스키마·라우터가 필요 없는 내부 처리 모듈에는 빈 파일을 일괄 생성하지 않습니다.

## 의존성·실행 설정 상태

- 직접 사용하는 패키지와 하위 의존성의 버전은 `requirements.txt` 하나에서 관리합니다. 의존성은 Docker 이미지 빌드 중 자동 설치하므로 로컬 Python·가상환경 준비나 수동 패키지 설치가 필요하지 않습니다. `pyproject.toml`은 Ruff·pytest 설정에 사용합니다.
- `Dockerfile`은 의존성 설치와 `pip check` 검사를 완료한 뒤 애플리케이션을 이미지에 포함합니다. 컨테이너를 실행·재시작할 때 패키지를 다시 설치하지 않습니다. `compose.yaml`은 백엔드·DB·소스 및 영상 폴더 연결을 구성합니다.
- Compose는 DB 접속 환경변수를 백엔드 컨테이너에 전달합니다. 로컬 실행은 루트 `.env`를 읽으며 환경변수가 `.env`보다 우선합니다. DB 비밀번호 누락·빈 값·잘못된 포트는 설정 검증에서 거부합니다.
- 서버 시작 시 설정 검증·모델 등록·실제 DB 연결 확인을 수행하며 실패하면 앱 시작도 실패합니다. 동기 DB 연결 확인은 별도 스레드에서 실행하고 종료 시 커넥션 풀을 정리합니다.

현재 의존성 목록에 포함된 기술과 적용 상태는 다음과 같습니다.

| 기술 | 용도·현재 상태 |
|---|---|
| Python 3.13·FastAPI·Uvicorn | 서버 런타임·앱 진입점·개발 자동 재시작 설정 |
| Swagger UI·ReDoc·OpenAPI | FastAPI 기본 제공. 문서 URL·제목·버전·Swagger UI 표시 옵션 설정 |
| PostgreSQL 18 | Compose 이미지·초기 DB 접속값·데이터 볼륨·준비 상태 검사 설정 |
| Pydantic·pydantic-settings | 환경변수와 API 요청·응답 검증 |
| SQLAlchemy·Psycopg 3 | 동기 세션·트랜잭션, 기능별 ORM·Core·SQL 기반 조회·저장 |
| Alembic | online/offline 실행 설정·변경 이력 생성 템플릿·전체 DB 초기 마이그레이션 |
| python-multipart | multipart 영상 업로드 수신 |
| ffmpeg·ffprobe | 영상 코덱·길이·해상도 검사와 웹 재생용 정규화 |
| Ruff·pytest·HTTPX | 정적 검사·기능별 단위 및 API 테스트·조건부 PostgreSQL 통합 테스트 |

전체 DB 구조는 마이그레이션으로 구성하며 데모 데이터는 별도로 삽입합니다. 영상은 ffprobe로 검사한 뒤 ffmpeg로 정규화하고, 조회수·좋아요·저장 수는 기존 DB 뷰에서 집계합니다.

## API 문서 (Swagger UI)

별도 Swagger 패키지나 컨테이너 없이 FastAPI가 문서를 제공합니다. 기본 포트 기준 접속 주소는 다음과 같습니다.

| 문서 | 주소 |
|---|---|
| Swagger UI·요청 실행 | `http://localhost:8000/docs` |
| ReDoc·문서 열람 | `http://localhost:8000/redoc` |
| OpenAPI 명세 JSON | `http://localhost:8000/openapi.json` |

`app/main.py`에서 문서 제목·설명·버전·URL을 설정합니다. Swagger UI에는 API 필터와 요청 소요 시간 표시를 활성화했습니다. 각 모듈에서 요청·응답 스키마와 라우터를 작성하고 `app/api/router.py`에 연결하면 해당 API가 문서에 자동 반영됩니다. 모듈별 묶음은 라우터의 `tags`로 지정합니다.

`GET /api/health`는 DB 연결과 영상 저장소의 읽기·쓰기 상태를 함께 확인합니다. 학습 기록을 변경하는 API는 Swagger에 표시된 `X-Record-Generation` 등 각 요청 조건을 확인합니다.

## Docker 실행과 버전 설정

설정 파일은 저장소 루트의 `compose.yaml`, `Dockerfile`, `.env.example`입니다. `.env.example`을 `.env`로 복사한 뒤 버전·DB 비밀번호·포트를 조정합니다.

macOS와 Windows 모두 파일 탐색기나 편집기에서 복사해도 됩니다. 기존 `.env`가 있으면 유지합니다.

| 설정 | 기본값 | 적용 위치 |
|---|---|---|
| `PYTHON_VERSION` | `3.13` | Compose의 빌드 인자 → Dockerfile의 `python:3.13-slim` 이미지 |
| `POSTGRES_VERSION` | `18` | Compose의 `postgres:18` 이미지 |
| `BACKEND_PORT` | `8000` | 로컬 PC에서 백엔드에 접속할 포트 |
| `POSTGRES_PORT` | `5432` | 로컬 PC에서 DB에 접속할 포트 |
| `POSTGRES_DB` | `sasu` | 초기 DB 이름 |
| `POSTGRES_USER` | `sasu` | 초기 DB 사용자 |
| `POSTGRES_PASSWORD` | 예시 값 | 로컬 개발용 DB 비밀번호·필수 |
| `DB_HOST` | `localhost` | 로컬 Python 실행에서 DB에 접속할 호스트. Compose 내부는 `db`로 지정 |
| `LOG_LEVEL` | `INFO` | 애플리케이션 로그 수준 |
| `DB_ECHO` | `false` | SQLAlchemy SQL 로그 출력 여부 |
| `DB_CONNECT_TIMEOUT` | `5` | DB 연결 대기 시간(초) |
| `VIDEO_STORAGE_ROOT` | `storage/videos` | 영상 저장 루트. 상대 경로는 프로젝트 루트 기준이며 Compose 내부는 `/app/storage/videos`로 지정 |

이미 `.env`가 있다면 덮어쓰지 않고 `.env.example`의 필요한 항목을 반영합니다. 로컬 Python 실행 시 DB 이름·계정·비밀번호는 `POSTGRES_*` 값을 사용하며, `DB_NAME`·`DB_USER`·`DB_PASSWORD`가 지정되어 있으면 해당 이름을 우선합니다. 로컬 DB 포트는 `DB_PORT`, 미지정 시 `POSTGRES_PORT`를 사용합니다. Compose는 내부 주소 `db:5432`를 전달하므로 호스트 포트를 변경해도 컨테이너 간 주소는 바뀌지 않습니다.

설정 확인 후 실행합니다.

```sh
docker compose config --quiet
docker compose up --build -d --wait
```

이 명령으로 이미지 빌드·Python 패키지 설치·의존성 검사·백엔드와 DB 실행을 함께 처리합니다. 첫 실행은 패키지를 다운로드할 수 있도록 네트워크 연결이 필요합니다.

### 의존성 재사용과 실패 처리

| 상황 | 처리 |
|---|---|
| `requirements.txt`와 Python 이미지·설치 단계가 같고 빌드 캐시가 있음 | 설치 완료 레이어를 재사용합니다. 소스만 바꿔도 패키지를 다시 설치하지 않습니다. |
| 설치 단계에서 같은 버전이 이미 설치되어 있음 | pip가 충족된 요구사항으로 판단하고 재설치를 생략합니다. 중복 설치 오류로 처리하지 않습니다. |
| `requirements.txt` 또는 Python 버전 변경 | 의존성 레이어를 다시 빌드합니다. 기존 다운로드 캐시는 가능한 범위에서 재사용합니다. |
| 다운로드·설치 실패 또는 버전 충돌 | 명령이 실패 상태를 반환하여 이미지 빌드를 중단합니다. 오류를 무시하고 성공한 빌드로 처리하지 않습니다. |
| 설치 후 누락·호환되지 않는 하위 의존성 발견 | `pip check`가 실패하여 이미지 빌드를 중단합니다. |

패키지를 추가·변경할 때는 `requirements.txt`를 수정하고 같은 `docker compose up --build -d --wait` 명령을 실행합니다. 컨테이너 내부에 직접 설치한 패키지는 재생성 시 유지되지 않으므로 의존성 변경은 파일에 반영합니다.

이미 빌드한 이미지를 그대로 사용해 다시 시작할 때:

```sh
docker compose up -d --wait
```

- API 문서: 기본 설정에서 `http://localhost:8000/docs`.
- 백엔드 → DB: `db:5432`. 로컬 PC의 DB 도구 → DB: `localhost:5432`.
- 소스 변경: `app/` 연결과 Uvicorn `--reload`로 반영합니다. 의존성·Python 버전 변경 시 이미지를 다시 빌드합니다.
- DB 준비 상태를 확인한 후 백엔드를 시작합니다. DB 데이터는 `postgres_data` 이름 있는 볼륨에 보존합니다.
- 백엔드는 `/openapi.json`의 HTTP 응답으로 프로세스 상태를 검사합니다. DB 연결까지 확인하는 검사는 아니며, `--wait`는 백엔드·DB의 상태 검사가 통과할 때까지 기다립니다.
- `init: true`로 백엔드 하위 프로세스의 신호 전달·종료 처리를 보조합니다.
- 서버 영상은 `video_data`, 썸네일은 `image_data` 볼륨에 저장합니다. 컨테이너 내부 경로는 각각 `/app/storage/videos`, `/app/storage/images`입니다.

이 Compose 파일은 소스 연결과 `--reload`를 사용하는 로컬 개발 구성입니다. 기본 검사는 다음과 같습니다.

```sh
docker compose exec backend ruff check app tests scripts alembic
docker compose exec backend pytest
```

PostgreSQL 전용 테스트는 해당 실행 변수를 지정하지 않으면 건너뜁니다. 따라서 기본 테스트 통과가 DB 통합·동시성 검증 완료를 의미하지는 않습니다.

- `SASU_TEST_POSTGRES=1`: 해당 기능의 fixture가 별도 테스트 DB를 생성·제거합니다. 별도 테스트 DB를 허용한 환경에서 사용합니다.
- `SASU_TEST_LIKES_POSTGRES=1`, `SASU_TEST_SAVED_CONTENTS_POSTGRES=1`: 연결된 DB에서 검증용 데이터를 생성하고 정리합니다.
- 데모 전용 테스트는 `demo_seeds/` 마운트가 필요합니다. `SASU_TEST_SEED_POSTGRES=1`을 지정하면 연결된 DB의 테이블을 트랜잭션 안에서 비운 뒤 검증하고 롤백합니다. 실행 중 테이블 잠금이 발생합니다.

데모 도구의 파일 처리 테스트만 실행하려면:

```sh
docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro backend python -m pytest tests/test_demo_seed_files.py -q
```

일반적인 재시작은 `docker compose down` / `up`으로 충분합니다. 전체 데모 초기화에만 `docker compose down -v`를 사용하며 DB·영상·썸네일이 함께 삭제됩니다. 이후 `up --build` → `alembic upgrade head` → 데모 삽입 순서로 다시 구성합니다.

## 데모 데이터

데모 원본 영상과 썸네일은 `demo_seeds/videos/`, `demo_seeds/thumbnails/`에 Git으로 함께 관리합니다. 원본은 각각 31개이며 `seed.sql`에 정의한 콘텐츠 25개를 삽입합니다. 자세한 실행 순서는 [데모 적용 안내](demo_seeds/README.md)를 참고합니다. 서버 영상은 `video_data`, 썸네일은 `image_data` 볼륨에 복사합니다. 데모 원본 폴더와 서버 저장소는 별개입니다.

```sh
docker compose run --rm -v ./demo_seeds:/app/demo_seeds:ro backend python -m demo_seeds.demo_injection
```

처음에는 영상·썸네일의 원본 파일명·크기·SHA-256을 확인하고 서버 저장소로 복사합니다. 재실행 시 기존 데이터는 유지하며, 기존 데모 영상에 썸네일이 없으면 이미지만 추가합니다. 직접 등록한 썸네일과 교체한 영상은 유지합니다. 시리즈에 별도 이미지를 등록하지 않고 첫 영상의 썸네일을 사용합니다.

현재 콘텐츠에 연결된 모든 영상과 데모 콘텐츠의 썸네일은 존재·크기·읽기 가능 여부를 DB 정보로 확인합니다. 파일이 누락되거나 DB 정보와 맞지 않으면 완료 메시지 대신 문제의 콘텐츠 ID와 파일 경로를 안내하고 중단합니다. 교체 전 영상 자산은 검사하지 않으며 기존 파일을 자동 복구하거나 덮어쓰지 않습니다.

SQL의 삽입과 파일 검사가 모두 성공해야 DB 변경을 확정합니다. 실패하면 이번 실행의 DB 변경과 새로 복사한 파일만 정리합니다. `docker compose down`은 DB·영상·이미지 볼륨을 유지합니다. `docker compose down -v`는 세 볼륨을 모두 삭제하므로 전체 초기화할 때만 사용합니다. 호스트의 `demo_seeds/` 원본과 이전 `storage/videos/` 폴더는 삭제되지 않습니다.

로그 확인과 종료:

```sh
docker compose logs -f
docker compose down
```

현재 볼륨 경로는 [PostgreSQL 18 이상 공식 이미지](https://hub.docker.com/_/postgres)에 맞춘 `/var/lib/postgresql`입니다. 17 이하로 변경할 때는 해당 버전의 데이터 경로도 맞춰야 합니다. 기존 데이터가 생긴 뒤 메이저 버전을 변경할 경우 데이터 마이그레이션이 별도로 필요하며, DB 이름·계정·비밀번호 초기값 변경도 기존 볼륨에 자동 적용되지 않습니다.

Python 버전을 변경하면 `requirements.txt`의 패키지 호환성과 `pyproject.toml`의 Ruff `target-version`도 맞춥니다.

## DB 연결·트랜잭션·마이그레이션

실제 DB 접속 확인:

```sh
docker compose exec backend python -m scripts.check_db
```

API에서 세션이 필요하면 `app/db/session.py`의 `get_db`를 FastAPI `Depends`로 주입합니다. 세션은 요청마다 생성·종료하고 자동 커밋하지 않습니다. 여러 CRUD 작업을 하나로 처리하는 서비스에서 `with session.begin():`으로 트랜잭션을 감싸면 성공 시 커밋하고 실패 시 롤백합니다. `repository.py`에서 임의로 커밋하지 않습니다.

### 최초 DB 구조 세팅

최종 통합 DB 설계서(2026-10-16)를 기준으로 `0001_initial_schema`에 전체 구조를 작성했습니다. PostgreSQL 16 이상이 필요하며 현재 Compose는 18을 사용합니다. 각 팀원은 공유된 마이그레이션을 자신의 로컬 Docker DB에 적용합니다. 별도 SQL 파일 실행이나 기능 모듈·ORM 모델 전체 구현은 필요하지 않습니다.

저장소 루트에서 `.env`를 준비하고 DB 비밀번호를 설정한 뒤 실행합니다. 기존 `.env`가 있다면 그대로 사용합니다.

```sh
docker compose up --build -d --wait
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

`current` 결과가 저장소의 최신 이력(`alembic heads`)과 일치하면 적용이 완료된 상태입니다. 이미 적용한 DB에서 `upgrade head`를 다시 실행하면 기존 이력은 재실행하지 않습니다. 이후 변경도 Git으로 받은 새 이력을 같은 명령으로 적용합니다.

초기 이력은 `sasu` 스키마에 21개 테이블과 외래키·제약조건·인덱스·검증 트리거·집계 뷰 4개·초기화 함수를 생성합니다. 사용자·카테고리·테스트 데이터를 삽입하지 않으며 초기화 함수도 정의만 합니다. 이력은 기본 `public.alembic_version`에 기록됩니다. 기능별 ORM 모델·Core 테이블·SQL은 이 실제 DB 구조를 참조합니다.

이 절차는 `sasu` 스키마가 없는 신규 DB 기준입니다. 수동으로 만든 `sasu` 스키마나 다른 마이그레이션 이력이 있는 DB를 자동으로 덮어쓰거나 초기화하지 않습니다. 적용 실패 시 기존 구조·이력의 일치 여부를 먼저 확인합니다. `downgrade base`는 이 초기 이력의 테이블과 데이터를 삭제하므로 최초 세팅 절차에는 사용하지 않습니다.

서버 실행 시 `create_all()`이나 자동 마이그레이션을 수행하지 않습니다. 신규 환경에서는 공유된 이력을 적용하면 되며 `revision --autogenerate`를 실행하지 않습니다. 전체 ORM 모델은 아직 작성되지 않았으므로 후속 변경 이력도 설계서를 기준으로 검토·작성합니다. Compose에서 `alembic/`을 연결하므로 컨테이너에서 생성한 이력 파일도 저장소에 남습니다.

### DB 구조 변경 시

변경 담당자는 기존 이력을 수정하는 대신 새 마이그레이션 파일을 생성합니다.

```sh
docker compose exec backend alembic revision -m "describe schema change"
```

생성된 `alembic/versions/` 파일의 `upgrade()`에 변경 내용을, `downgrade()`에 되돌릴 내용을 작성합니다. 현재는 전체 ORM 모델이 준비되지 않아 수동 작성하며, 적용 검증 후 파일을 Git으로 공유합니다.

팀원은 공유된 이력을 받은 뒤 아래 명령으로 각자 로컬 DB에 적용합니다.

```sh
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

## 썸네일 API

콘텐츠와 시리즈 모두 `PUT /api/contents/{id}/thumbnail`, `PUT /api/curriculums/{id}/thumbnail`에 multipart `file` 하나를 보냅니다. 교체도 같은 API를 사용하고, 삭제는 같은 경로의 `DELETE`입니다. 등록·교체·삭제 성공은 204입니다.

- JPEG·PNG·WebP, 최대 10MB. 실제 이미지 디코딩이 실패하면 `422 INVALID_IMAGE`, 용량을 초과하면 `413 IMAGE_TOO_LARGE`, 지원하지 않는 형식이면 `415 UNSUPPORTED_IMAGE_TYPE`입니다.
- 조회 응답의 `thumbnail_url`을 그대로 사용합니다. 공개 이미지는 기존 캐시 설정을 유지합니다. 관리자 미리보기 URL은 preview=true와 actor_id를 포함하며 공유 캐시에 저장하지 않습니다.
- 시리즈는 직접 등록한 이미지가 있으면 우선 사용하고, 없으면 편성 순서상 첫 콘텐츠의 썸네일을 사용합니다. 별도의 방식 선택 값은 보내지 않습니다. 첫 콘텐츠나 그 이미지도 없으면 `thumbnail_url`은 null이며 다른 콘텐츠로 대체하지 않습니다.
- 임시저장 콘텐츠 이미지는 관리자 미리보기로만 제공합니다. 공개된 이용 가능 단계가 없는 시리즈의 이미지도 관리자 전용입니다. 시리즈 첫 콘텐츠가 비공개이면 학습자 자동 참조 이미지는 null입니다.
- 시리즈 썸네일 PUT은 직접 이미지를 등록·교체하고, DELETE는 직접 이미지만 제거합니다. 삭제 후에는 첫 콘텐츠의 썸네일을 사용하며 콘텐츠 이미지 자체는 삭제하지 않습니다. 직접 등록 이미지가 없으면 DELETE는 404입니다.
- 썸네일 변경 후 관련 콘텐츠·시리즈 목록과 상세를 재조회합니다. 시리즈 순서 변경이나 첫 콘텐츠의 이미지 교체·삭제도 대표 이미지에 반영됩니다.
- 편집 요청의 `expected_updated_at`에는 조회한 수정 시각을 그대로 보냅니다. 콘텐츠 기본정보 PATCH, 시리즈 PATCH·단계 PUT에서 불일치하면 `409 EDIT_CONFLICT`입니다. 필수값이며 생략하거나 null이면 422입니다.

기존 썸네일 이미지 연결과 시리즈 편성 정보를 사용하므로 이 동작을 위한 DB 구조 변경은 없습니다. Pillow 의존성 추가 후에는 백엔드 이미지를 재빌드합니다.

## 영상 업로드 중단 후 확인

브라우저의 업로드 취소·응답 대기 종료는 서버 저장 취소를 보장하지 않습니다. 이미 시작된 처리 작업은 DB 연결까지 완료될 수 있습니다.

- 재시도 전 `GET /api/contents/{id}?view=editor`에서 현재 `media_revision`과 영상을 확인합니다. 조회에는 관리자 `X-Actor-Id`가 필요합니다.
- revision이 그대로여도 처리가 진행 중일 수 있으므로 즉시 실패로 단정하지 않습니다. 바뀌었더라도 다른 관리자의 교체일 수 있으므로 현재 영상까지 확인합니다. 서버 작업 상태·취소 전용 API는 없습니다.
- 교체 요청은 최신 `expected_media_revision`을 사용합니다. 409이면 최신 정보를 다시 조회합니다.
- 정상적인 처리 실패 시 임시 파일을 정리하고, DB 연결 실패 시 새 파일을 삭제합니다. 교체 전 파일은 DB 연결 성공 후 제거합니다. 프로세스 강제 종료 등으로 남은 파일까지 즉시 정리되는 것은 아닙니다.

## 영상 입력과 저장 해상도

`GET /api/contents/video-policy`의 `max_long_edge_px`는 입력 상한(3840px), `target_long_edge_px`는 저장 목표(2160px)입니다. 긴 변 3840px 초과는 `422 VIDEO_RESOLUTION_OUT_OF_RANGE`로 거절하고, 허용 범위 중 2160px 초과는 비율·방향을 유지하며 축소합니다. 2160px 이하는 확대하지 않습니다. 용량·길이 제한은 별도로 적용합니다.

8비트 YUV 4:2:0 영상과 허용 프로필(H.264 Baseline·Constrained Baseline·Main·High, VP8, VP9 Profile 0, AV1 Main)을 검사합니다. 코덱별 기존 컨테이너·음성 규칙은 유지합니다. 저장 전 전체 영상·음성 디코딩 검사(최대 120초)를 수행하며 손상은 `422 INVALID_VIDEO`, 검사 시간 초과는 `422 VIDEO_INSPECTION_TIMEOUT`으로 거절합니다. 이 검사는 모든 브라우저·기기의 재생을 보증하는 것은 아닙니다.
