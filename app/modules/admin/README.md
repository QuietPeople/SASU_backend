# 관리자 API

통합 DB 마이그레이션의 기존 테이블·뷰·함수를 사용한다. 별도 ORM 모델이나 마이그레이션은 추가하지 않는다.

| API | 기능 |
| --- | --- |
| `GET /api/categories` | 전체 카테고리 목록 |
| `POST /api/categories` | 카테고리 추가·동일 이름 재사용 |
| `PATCH /api/categories/{category_id}` | 카테고리 이름 수정 |
| `GET /api/tags` | 태그 검색·페이지 목록 |
| `POST /api/tags` | 태그 추가·동일 이름 재사용 |
| `GET /api/contents/{content_id}/statistics/reactions` | 반응·시청 통계 |
| `POST /api/users/{user_id}/test-records/reset` | 대상 학습자의 테스트 기록 초기화 |

카테고리·태그 목록은 `X-Actor-Id` 없이 조회할 수 있다.
나머지 API는 `X-Actor-Id`에 실제 `sasu.app_users`의 관리자 ID가 필요하다.
계정 ID를 하드코딩하거나 요청만으로 사용자를 생성하지 않는다.
관리자에게 `user_settings` 행은 필요하지 않으며, 초기화 대상은 LEARNER 역할과 설정 행이 모두 필요하다.

## 카테고리·태그

카테고리는 `app/modules/categories/`, 태그는 `app/modules/tags/`에 구현한다.
공개 목록과 관리자 쓰기가 같은 기능 모듈을 공유한다. 기존 DB 테이블을 직접 사용하므로
다른 모듈의 ORM 모델 등록이나 콘텐츠·사용자 구현 완료를 기다릴 필요가 없다.

이름 입력은 `{"name":"엑셀"}` 형식이며 앞뒤 공백 제거 후 1~30자다.
대소문자나 내부 공백은 변경하지 않는다. 새 이름은 201, 완전히 같은 이름은 기존 ID와 200을 반환한다.
카테고리 수정 시 ID와 콘텐츠·관심 연결은 유지한다. 다른 카테고리 이름과 겹치면
`409 CATEGORY_NAME_CONFLICT`이며, 현재 이름과 같은 수정은 `updated_at`도 유지한다.

기존 DB에는 이름 UNIQUE 제약이 없다. 생성과 이름 수정을 `SHARE ROW EXCLUSIVE` 테이블 잠금으로
직렬화하여 이름 확인과 쓰기를 같은 트랜잭션으로 처리한다. 일반 조회는 계속 허용한다.
다른 기능에서도 이름을 생성·수정할 때 해당 모듈의 서비스를 재사용한다.

카테고리는 페이지 구분 없이 ID 오름차순의 `{"items":[...]}`를 반환한다.
태그는 `q`, `page`(기본 1), `size`(기본 20, 최대 100)를 받으며 ID 오름차순으로 정렬한다.
`q`는 양끝 공백 제거 후 대소문자를 구분하지 않는 부분 문자열로 찾는다.
`%`, `_`, 역슬래시도 입력 문자 그대로 찾으며 와일드카드로 해석하지 않는다.
태그 목록은 `items/page/size/total/has_next` 구조이며 결과가 없거나 페이지 범위를 넘겨도 200이다.
태그 생성만으로 콘텐츠 연결을 추가하지 않으며, 연결은 콘텐츠 PATCH의 `tag_ids`를 사용한다.

## 반응·시청 통계

`sasu.content_metrics` 뷰의 조회수·좋아요·저장 수를 사용한다.
시청 완료율은 `watch_records`의 완료 행 수 / 실제 재생 기록 행 수 × 100이다.
분모가 0이면 `percent=null`이고 공개 상태와 관계없이 관리자가 콘텐츠를 조회할 수 있다.
API 취합 초안에 남아 있는 주기 캐시 대신 적재된 통합 DB의 집계 뷰를 따른다.

## 초기화와 세대 계약

```json
{"confirm": true, "expected_record_generation": 0}
```

API의 `record_generation`은 0부터, DB의 `learning_epoch`은 1부터 시작한다.
`expected_epoch = expected_record_generation + 1`, `record_generation = learning_epoch - 1`로 변환한다.
users 모듈에서 세대를 반환하거나 다른 학습 쓰기를 검사할 때도 같은 대응을 사용해야 한다.

대상 설정 행 잠금 → 세대 확인 → 삭제 건수 조회 → `sasu.reset_learning()` 호출 → 커밋 순서다.
함수는 새 DB 세대만 반환하므로 삭제 건수는 동일 잠금·트랜잭션 안에서 사전 집계한다.
`deleted_counts`는 방문 기록 `watch_visits`를 포함해 실제 삭제하는 8종의 건수를 제공한다.

사용자·관심·관심 안내 상태·복기 간격·콘텐츠·문항 버전·커리큘럼·영상 파일은 유지한다.
기존 성공 요청을 같은 세대로 재전송하면 409이며 이후 생긴 학습 기록을 다시 삭제하지 않는다.
실패하면 삭제와 세대 변경을 모두 롤백한다. 집계 뷰이므로 별도 캐시 재계산은 하지 않는다.
응답의 `clear_client_feed_state=true`를 받으면 프론트가 탭별 임시 상태와 대기 요청을 정리한다.

## 검증

컨테이너에서 다음 명령으로 전체 테스트와 PostgreSQL 통합 테스트를 실행한다.

```powershell
docker compose exec -T -e SASU_TEST_POSTGRES=1 backend pytest -q
```

PostgreSQL 통합 테스트는 현재 DB 서버에 UUID 이름의 별도 테스트 DB를 생성하고
기존 Alembic 마이그레이션을 적용한다. 일반 테스트는 트랜잭션을 롤백하며,
별도 연결을 쓰는 동시성 테스트는 직접 만든 UUID 이름의 테스트 행을 정리한다.
마지막에는 직접 생성한 테스트 DB만 삭제한다.
개발 DB의 사용자·콘텐츠·학습 기록을 초기화하지 않는다. 테스트 연결 계정에 DB 생성 권한이 필요하다.
환경변수 없이 실행하면 PostgreSQL 전용 테스트는 건너뛴다.
