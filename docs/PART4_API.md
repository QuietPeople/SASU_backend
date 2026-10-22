# 파트 4 API와 연동 안내

새 API 10개를 제공한다. X-Actor-Id는 기존 목업 역할 확인이며 로그인 인증이 아니다. 개인 현황은 본인 또는 관리자, 모든 통계와 응답 목록은 관리자만 조회할 수 있다. 다른 학습자 현황은 404로 처리한다.

## 경로

| ID | 메서드 | 경로 | 설명 |
| --- | --- | --- | --- |
| DSH-01 | GET | /api/users/{user_id}/dashboard | 개인 학습 현황 |
| DSH-02 | GET | /api/users/{user_id}/dashboard/categories | 카테고리별 학습 상태 |
| STA-01 | GET | /api/statistics | 서비스 전체 통계 |
| STA-02 | GET | /api/statistics/contents | 콘텐츠 반응 통계 목록 |
| STA-03 | GET | /api/contents/{content_id}/statistics | 콘텐츠 전체 통계 |
| STA-05 | GET | /api/contents/{content_id}/statistics/quiz | 영상 끝 퀴즈 및 최초 정답률 |
| STA-06 | GET | /api/contents/{content_id}/statistics/feed-review | 반복 피드 복습 통계 |
| STA-07 | GET | /api/contents/{content_id}/statistics/wrong-answer-review | 오답 복습 및 해결 상태 |
| STA-08 | GET | /api/contents/{content_id}/statistics/flashcards | 카드 열람·정답 펼침 수 |
| STA-09 | GET | /api/responses | 제출 응답 이력 목록 |

기존 STA-04 `/api/contents/{content_id}/statistics/reactions`, CRS-01~07, SYS-01, TST-01, 응답 상세 경로는 유지한다.

역할분담안의 STA 번호와 예전 API 초안의 번호가 서로 다르다. 이번 첨부에는 최신 API 취합본이 없어 역할분담안의 번호와 현재 코드의 `/statistics` 명명에 맞춰 위 신규 경로·응답을 작성했다. 위 신규 경로는 프런트엔드 연결 전에 팀의 최신 취합본과 대조할 계약안이다. DSH 경로, `/responses` 목록과 기존 구현 경로는 유지했다.

## 조회 조건

`/statistics/contents`는 page(기본1), size(기본20, 최대100)를 받는다. `/responses`도 같은 페이지 조건과 다음 선택 필터를 받는다.

| 조건 | 허용 값 |
| --- | --- |
| user_id, content_id, quiz_version_id | 양의 BIGINT |
| context | VIDEO_END, FEED_REVIEW, WRONG_REVIEW |
| result | CORRECT, WRONG, SKIPPED |
| submitted_from | 시간대가 있는 ISO 8601 시각, 이상 |
| submitted_to | 시간대가 있는 ISO 8601 시각, 미만 |

응답 목록은 submitted_at DESC, response_id DESC로 고정 정렬한다. 페이지 범위를 넘어도 total은 전체 일치 건수이며 items는 []이다. 미정의 조건·범위 오류는 422이다. 다른 신규 조회 API는 쿼리 조건을 받지 않는다.

## Swagger 사용 예

서버 `/docs`에서 관리자 사용자의 실제 ID를 X-Actor-Id에 입력하고 다음 요청을 실행한다. ID를 숫자 1이나 2로 가정하지 않는다.

```http
GET /api/statistics
X-Actor-Id: <관리자 ID>

GET /api/responses?context=VIDEO_END&result=WRONG&page=1&size=20
X-Actor-Id: <관리자 ID>

GET /api/users/<학습자 ID>/dashboard
X-Actor-Id: <해당 학습자 ID 또는 관리자 ID>
```

빈 퀴즈 통계는 다음과 같다. `percent=null`은 표본 없음이며 정답률 0%와 구분한다.

```json
{
  "context": "VIDEO_END",
  "displayed_count": 0,
  "answered_count": 0,
  "correct_count": 0,
  "wrong_count": 0,
  "skipped_count": 0,
  "unanswered_display_count": 0,
  "response_without_display_count": 0,
  "accuracy": {"numerator": 0, "denominator": 0, "percent": null},
  "participation": {"numerator": 0, "denominator": 0, "percent": null},
  "skip_rate": {"numerator": 0, "denominator": 0, "percent": null},
  "first_accuracy": {"numerator": 0, "denominator": 0, "percent": null}
}
```

정확한 전체 응답 타입은 각 모듈 schemas.py와 생성된 Swagger에서 확인한다. 공통 오류 구조는 기존 ErrorResponse를 그대로 사용한다.

## 다른 파트에 전달할 사항

- 파트1: `docs/part1_router_registration.patch`의 두 라우터 등록을 반영한다. 기존 admin의 STA-04는 이동·중복 등록하지 않는다.
- 파트2: watch_records는 실제 재생 이후 생성, 완료는 completed_at으로 기록한다. CARD_OPENED/CARD_REVEALED와 QUIZ_DISPLAYED를 실제 표시 시점에 기록한다.
- 파트3: quiz_attempts.context와 제출 당시 quiz_version_id를 보존한다. 응답 상세는 기존 responses 모듈 소유이며 이 작업에서는 수정하지 않는다.
- 초기화: 기존 reset_learning 함수를 사용한다. 신규 집계 테이블이나 캐시가 없어서 추가 삭제 대상은 없다.
