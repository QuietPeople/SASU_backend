# SASU Backend

SASU의 학습자·관리자 기능을 위한 백엔드 저장소입니다.

**공통 기반과 기능별 모듈을 분리하는 구조**를 사용합니다. `app/modules/` 아래에 기능별 폴더를 하나씩 추가하고, 해당 기능의 라우터·서비스·CRUD·스키마·모델을 그 안에 모읍니다.

현재 `contents/`와 `users/`는 **모듈 작성 방식을 보여주는 예시**입니다. 실제 서비스의 전체 모듈 목록이나 경계를 확정한 것은 아니며, 새 기능을 개발할 때 같은 방식으로 모듈을 추가합니다.

FastAPI·Swagger UI·환경변수 검증·동기 DB 세션·Alembic과 Docker Compose 실행 설정을 구성했습니다. 예시 모듈의 파일은 역할을 표시한 틀이며 개별 API·업무 처리·테이블 모델은 구현하지 않았습니다. Docker 이미지 빌드·백엔드와 PostgreSQL 실행·실제 DB 연결·API 문서 응답을 검증했으며, 공통 기반 테스트 13개와 Ruff 코드 검사를 통과했습니다.

## 디렉터리 구조

Python 패키지 표시용 `__init__.py`는 트리에서 생략했습니다.

```text
SASU_backend/
├── app/
│   ├── main.py                  # FastAPI 앱·Swagger UI 설정·공통 라우터 연결
│   │
│   ├── api/
│   │   └── router.py            # 모듈별 API 라우터를 /api 아래 통합
│   │
│   ├── core/                    # 애플리케이션 공통 설정
│   │   ├── config.py            # 환경변수 로딩·필수값 검증·DB URL 구성
│   │   ├── security.py          # 인증·암호화 공통 처리의 예약 위치
│   │   └── exceptions.py        # 공통 예외·핸들러 위치
│   │
│   ├── db/                      # DB 공통 기반
│   │   ├── session.py           # DB 엔진·요청별 세션·연결 확인·종료
│   │   ├── base.py              # ORM 공통 Base·제약조건 이름 규칙
│   │   └── models.py            # 모듈별 모델 등록 (새 모델 추가 시 갱신)
│   │
│   ├── modules/                 # 기능별 폴더를 추가하는 위치 (아래 2개는 작성 예시)
│   │   ├── contents/            # 예시 1: 콘텐츠 기능을 한 폴더에 모음
│   │   │   ├── router.py        # 콘텐츠 API 요청·응답 → service 호출
│   │   │   ├── service.py       # 콘텐츠 업무 규칙·트랜잭션 → repository 호출
│   │   │   ├── repository.py    # 콘텐츠 CRUD: DB 생성·조회·수정·삭제
│   │   │   ├── schemas.py       # 콘텐츠 요청·응답 구조·필드 검증
│   │   │   └── models.py        # 콘텐츠 DB 테이블·관계 정의
│   │   └── users/               # 예시 2: 다른 기능도 같은 구성으로 추가
│   │       ├── router.py        # 사용자 API 요청·응답 → service 호출
│   │       ├── service.py       # 사용자 업무 규칙·트랜잭션 → repository 호출
│   │       ├── repository.py    # 사용자 CRUD: DB 생성·조회·수정·삭제
│   │       ├── schemas.py       # 사용자 요청·응답 구조·필드 검증
│   │       └── models.py        # 사용자 DB 테이블·관계 정의
│   │
│   ├── integrations/            # 저장소·외부 서비스 접근
│   │   └── storage.py           # 로컬 영상 저장소 접근 위치
│   │
│   └── jobs/                    # 주기 집계 코드 배치 위치
│
├── alembic/                     # DB 마이그레이션 환경
│   ├── env.py                  # 공통 설정·모델로 online/offline 마이그레이션
│   ├── script.py.mako          # 변경 이력 파일 생성 템플릿
│   └── versions/               # 0001_initial_schema: 전체 DB 초기 구조
├── alembic.ini                  # Alembic 경로·로그 설정
├── scripts/
│   └── check_db.py             # 실제 DB 연결 확인 명령
├── tests/
│   ├── conftest.py              # 실제 .env·개발 DB와 분리하는 fixture
│   ├── test_config.py          # 설정 우선순위·잘못된 입력·비밀번호 처리
│   ├── test_database.py        # 세션 종료·커밋·실패 시 롤백
│   ├── test_application.py     # 앱 시작·종료·Swagger UI 검증
│   ├── test_migrations.py      # 임시 DB에서 Alembic 생성·적용·되돌리기
│   ├── contents/                # modules/contents에 대응하는 테스트 예시
│   │   └── test_api.py          # 콘텐츠 API 테스트 위치·아직 미작성
│   └── users/                   # modules/users에 대응하는 테스트 예시
│       └── test_api.py          # 사용자 API 테스트 위치·아직 미작성
├── storage/
│   └── videos/                  # 실제 로컬 영상 파일 저장 위치
├── requirements.txt             # Python 3.13 직접·하위 의존성과 버전 관리
├── pyproject.toml               # Ruff·pytest 도구 설정
├── Dockerfile                   # Python 이미지·의존성·서버 실행
├── compose.yaml                 # 백엔드·PostgreSQL·볼륨 실행 설정
├── .env.example                 # Python·PostgreSQL 버전과 DB 설정 예시
├── .gitignore
├── .dockerignore
└── README.md
```

## 공통 디렉터리 역할

| 디렉터리 | 역할 |
|---|---|
| `app/api/` | 모듈의 라우터를 통합합니다. 개별 기능의 API 코드는 해당 모듈의 `router.py`에 둡니다. |
| `app/core/` | 환경 설정·로그 등 공통 기반과 예외·보안 처리를 배치합니다. `security.py`는 예약 파일이며 현재 범위에 로그인·JWT를 추가한 것은 아닙니다. |
| `app/db/` | 동기 DB 엔진·요청별 세션·ORM 공통 Base를 관리합니다. 개별 테이블 모델은 각 모듈의 `models.py`에 작성하고, `app/db/models.py`에서 등록합니다. |
| `app/modules/` | 기능별 모듈을 추가하는 위치입니다. `contents/`·`users/`는 작성 예시이며 각 모듈 안에 라우터·서비스·CRUD·스키마·모델을 둡니다. 관리자·학습자가 함께 쓰는 기능도 같은 모듈을 공유합니다. |
| `app/integrations/` | 파일 저장소나 외부 API에 접근하는 코드를 둡니다. 현재 영상 저장 대상은 로컬 `storage/videos/`이며 외부 저장 서비스는 도입하지 않았습니다. |
| `app/jobs/` | 조회수·좋아요 수 등 주기 집계 코드를 둡니다. 실행 도구와 주기는 추후 결정합니다. |
| `alembic/` | 전체 DB 초기 구조와 후속 변경 이력을 관리·적용합니다. 초기 이력은 기능별 ORM 모델 없이 실행할 수 있습니다. |
| `scripts/` | 직접 실행하는 관리 명령을 둡니다. `check_db.py`는 현재 설정의 DB에 `SELECT 1`을 실행하고 연결을 정리합니다. |
| `tests/` | 공통 기반 테스트와 모듈별 테스트를 둡니다. 설정 테스트는 실제 `.env`를 읽지 않으며, 트랜잭션·마이그레이션 테스트는 임시 SQLite DB를 사용합니다. 실제 PostgreSQL 검증은 별도 연결 확인 명령으로 수행합니다. |
| `storage/videos/` | 실제 영상 파일을 저장하며 컨테이너의 `/app/storage/videos`에 연결합니다. DB에는 저장 루트 기준 상대 경로를 기록하는 방향입니다. |

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

예를 들어 카테고리 기능을 개발한다면 아래 순서로 확장합니다. `categories/`는 설명을 위한 이름이며 현재 생성하지 않았습니다.

1. `app/modules/categories/`를 만들고 Python 패키지용 `__init__.py`를 추가합니다.
2. 예시 모듈처럼 `router.py`, `service.py`, `repository.py`, `schemas.py`, `models.py`를 필요한 만큼 작성합니다.
3. 해당 모듈의 라우터를 `app/api/router.py`에서 `include_router`로 연결합니다. 모듈마다 FastAPI 앱을 새로 만들지 않고 `app/main.py`의 앱을 공유합니다.
4. DB 모델은 `app/db/base.py`의 `Base`를 상속하고, 해당 모델 모듈 경로를 `app/db/models.py`의 `MODEL_MODULES`에 추가합니다. Alembic으로 스키마 변경을 관리하며 엔진·세션 기반은 공통 `app/db/`를 사용합니다.
5. `tests/categories/`에 해당 기능의 테스트를 추가합니다.

다섯 파일은 역할을 보여주는 기본 예시이며, DB 테이블이 필요 없는 기능에는 `models.py`를 만들지 않는 등 필요한 파일만 둡니다. 다른 모듈과 공유하는 규칙은 담당 서비스에서 관리하고 중복 구현을 피합니다. **새 기능은 `modules/` 아래 새 모듈로 확장하고, 서버 전체에서 공유하는 설정·DB 연결·외부 연동은 공통 디렉터리에 둡니다.**

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
| Pydantic·pydantic-settings | 환경변수 로딩·검증 구현. 요청·응답 스키마는 기능 개발 시 작성 |
| SQLAlchemy·Psycopg 3 | 동기 엔진·요청별 세션·공통 Base·모델 등록 구현. 개별 테이블 모델은 미작성 |
| Alembic | online/offline 실행 설정·변경 이력 생성 템플릿·전체 DB 초기 마이그레이션 |
| python-multipart | 영상 업로드에 사용 예정. 업로드 API는 아직 미구현 |
| Ruff·pytest·HTTPX | 검사·테스트용 설정과 공통 기반 테스트 작성. 예시 모듈 API 테스트는 미작성 |

모듈별 ORM 모델·API는 기능 설계에 맞춰 이어서 작성합니다. 전체 DB 구조는 아래 초기 마이그레이션으로 구성하며 초기 데이터는 포함하지 않습니다. 영상 길이·형식 검사용 도구와 주기 집계 실행 방식은 해당 기능을 구현할 때 결정합니다.

## API 문서 (Swagger UI)

별도 Swagger 패키지나 컨테이너 없이 FastAPI가 문서를 제공합니다. 기본 포트 기준 접속 주소는 다음과 같습니다.

| 문서 | 주소 |
|---|---|
| Swagger UI·요청 실행 | `http://localhost:8000/docs` |
| ReDoc·문서 열람 | `http://localhost:8000/redoc` |
| OpenAPI 명세 JSON | `http://localhost:8000/openapi.json` |

`app/main.py`에서 문서 제목·설명·버전·URL을 설정합니다. Swagger UI에는 API 필터와 요청 소요 시간 표시를 활성화했습니다. 각 모듈에서 요청·응답 스키마와 라우터를 작성하고 `app/api/router.py`에 연결하면 해당 API가 문서에 자동 반영됩니다. 모듈별 묶음은 라우터의 `tags`로 지정합니다.

현재 개별 API는 구현하지 않았으므로 문서에 표시할 업무 API 목록은 비어 있습니다.

## Docker 실행과 버전 설정

설정 파일은 저장소 루트의 `compose.yaml`, `Dockerfile`, `.env.example`입니다. `.env.example`을 `.env`로 복사한 뒤 버전·DB 비밀번호·포트를 조정합니다.

```sh
cp -n .env.example .env
```

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
- 영상은 로컬 `storage/videos/`에 저장합니다.

이 Compose 파일은 소스 연결과 `--reload`를 사용하는 로컬 개발 구성입니다. 컨테이너에서도 다음 명령으로 검사할 수 있습니다. 공통 기반 테스트는 실제 개발 DB의 데이터를 변경하지 않습니다.

```sh
docker compose exec backend ruff check app tests scripts alembic
docker compose exec backend ruff format --check app tests scripts alembic
docker compose exec backend pytest
```

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
cp -n .env.example .env
# .env의 POSTGRES_PASSWORD 등 로컬 설정 확인
docker compose up --build -d --wait
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

`current` 결과가 `0001_initial_schema (head)`이면 초기 적용이 완료된 상태입니다. 이미 적용한 DB에서 `upgrade head`를 다시 실행하면 기존 이력은 재실행하지 않습니다. 이후 변경도 Git으로 받은 새 이력을 같은 명령으로 적용합니다.

초기 이력은 `sasu` 스키마에 21개 테이블과 외래키·제약조건·인덱스·검증 트리거·집계 뷰 4개·초기화 함수를 생성합니다. 사용자·카테고리·테스트 데이터를 삽입하지 않으며 초기화 함수도 정의만 합니다. 이력은 기본 `public.alembic_version`에 기록됩니다. 기능별 ORM 모델은 이후 `sasu` 스키마의 실제 테이블에 맞춰 매핑합니다.

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
