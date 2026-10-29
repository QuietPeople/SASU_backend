-- 임시 개발·데모 데이터: 기본 데이터·더존 목업·퀴즈·시리즈·가상 학습 기록.
-- 운영용 데이터 또는 회원가입 로직이 아니다. 불필요해지면 이 파일과 안내·전용 테스트를 제거한다.
-- 테이블·Alembic 이력은 변경하지 않는다. DO 문 전체가 하나의 트랜잭션으로 처리된다.
-- demo_seeds/videos에 원본 파일명으로 둔 영상을 demo_seeds/demo_injection.py가 복사한 뒤 실행한다.
-- 재실행: 영상 UUID 25개가 존재하면 기초·콘텐츠 삽입을 생략하고 보강 단계로 진행한다.
-- 보강은 전용 demo_dozone 계정을 처음 만들 때 한 번만 수행한다. 이후 수정·초기화를 유지한다.
-- 영상 일부만 존재하면 중단한다. 기존 데이터와 원본 영상은 덮어쓰지 않는다.

DO $sasu_seed$
DECLARE
    dataset jsonb := $sasu_demo_data$
{
  "users": [
    {
      "username": "admin",
      "display_name": "관리자",
      "role": "ADMIN"
    },
    {
      "username": "user1",
      "display_name": "학습자",
      "role": "LEARNER"
    }
  ],
  "categories": [
    {
      "name": "실무 용어",
      "group_name": "실무 용어·커뮤니케이션",
      "sort_order": 1
    },
    {
      "name": "한자어 업무 용어",
      "group_name": "실무 용어·커뮤니케이션",
      "sort_order": 2
    },
    {
      "name": "비즈니스 영어 표현",
      "group_name": "실무 용어·커뮤니케이션",
      "sort_order": 3
    },
    {
      "name": "업무 메일",
      "group_name": "실무 용어·커뮤니케이션",
      "sort_order": 4
    },
    {
      "name": "비즈니스 매너",
      "group_name": "실무 용어·커뮤니케이션",
      "sort_order": 5
    },
    {
      "name": "엑셀",
      "group_name": "문서·OA",
      "sort_order": 6
    },
    {
      "name": "보고서 작성",
      "group_name": "문서·OA",
      "sort_order": 7
    },
    {
      "name": "재경",
      "group_name": "재무·회계·경영",
      "sort_order": 8
    },
    {
      "name": "AI 업무 활용",
      "group_name": "일하는 방식·커리어",
      "sort_order": 9
    },
    {
      "name": "신입 온보딩",
      "group_name": "일하는 방식·커리어",
      "sort_order": 10
    },
    {
      "name": "문서·OA",
      "group_name": null,
      "sort_order": 11
    },
    {
      "name": "커뮤니케이션",
      "group_name": null,
      "sort_order": 12
    },
    {
      "name": "데이터",
      "group_name": null,
      "sort_order": 13
    },
    {
      "name": "IT",
      "group_name": null,
      "sort_order": 14
    },
    {
      "name": "업무 생산성",
      "group_name": null,
      "sort_order": 15
    },
    {
      "name": "비즈니스 기초",
      "group_name": null,
      "sort_order": 16
    }
  ],
  "contents": [
    {
      "number": 1,
      "video_asset_id": "15acecfa-99a8-5147-8335-0ccbb8cc34fe",
      "storage_path": "dozone-demo-20261029/01.mp4",
      "original_name": "엑셀 VLOOKUP 3분 정리.mp4",
      "size_bytes": 86642,
      "duration_seconds": 20.0,
      "category": "문서·OA",
      "title": "엑셀 VLOOKUP 3분 정리",
      "tags": [
        "엑셀",
        "함수"
      ],
      "core_content": "VLOOKUP은 기준 값으로 다른 표의 값을 찾아옵니다. 찾을 값, 범위, 열 번호, 일치 옵션 순서로 입력합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "1b21ccb7ce9e554718e33e4a39d781fa693a20d8ed14c7e745d3cfb6b99ee1ae"
    },
    {
      "number": 2,
      "video_asset_id": "2b45589c-8e26-5c56-876d-c182c5fda0ec",
      "storage_path": "dozone-demo-20261029/02.mp4",
      "original_name": "피벗 테이블로 월별 매출 요약하기.mp4",
      "size_bytes": 88071,
      "duration_seconds": 20.0,
      "category": "문서·OA",
      "title": "피벗 테이블로 월별 매출 요약하기",
      "tags": [
        "엑셀",
        "피벗테이블"
      ],
      "core_content": "피벗 테이블은 원본 데이터를 원하는 기준으로 요약합니다. 행에 월, 값에 매출을 넣으면 월별 합계가 나옵니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "993c0438fa952a156fc7d721783039206b16288f8f094e6ca677272e12364f23"
    },
    {
      "number": 3,
      "video_asset_id": "5748e975-f58d-501c-bb12-30c53749c014",
      "storage_path": "dozone-demo-20261029/03.mp4",
      "original_name": "파워포인트 슬라이드 정렬 단축키.mp4",
      "size_bytes": 92210,
      "duration_seconds": 20.0,
      "category": "문서·OA",
      "title": "파워포인트 슬라이드 정렬 단축키",
      "tags": [
        "파워포인트",
        "단축키"
      ],
      "core_content": "정렬 기능을 쓰면 도형을 일정한 간격으로 맞출 수 있습니다. 여러 개를 선택한 뒤 맞춤 메뉴를 사용합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "bf863a033a0c1e91b0c8a88a0a6610eb6a4c599784740d3e8b04ba93908d0d6c"
    },
    {
      "number": 4,
      "video_asset_id": "ea5c549d-d7a9-5df3-a11d-89eac408fa91",
      "storage_path": "dozone-demo-20261029/04.mp4",
      "original_name": "워드 스타일로 목차 자동 만들기.mp4",
      "size_bytes": 90069,
      "duration_seconds": 20.0,
      "category": "문서·OA",
      "title": "워드 스타일로 목차 자동 만들기",
      "tags": [
        "워드",
        "문서작성"
      ],
      "core_content": "제목 스타일을 지정하면 목차를 자동으로 만들 수 있습니다. 내용이 바뀌면 목차 업데이트만 누르면 됩니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "05b503e5fc9082b23caba72c9846024e2d8d6e458772ef9a3d7f3fa4be3f8133"
    },
    {
      "number": 5,
      "video_asset_id": "6b38f690-6e06-5dc2-bb53-067fb2a1f41e",
      "storage_path": "dozone-demo-20261029/05.mp4",
      "original_name": "업무 메일 첫 문장 쓰는 법.mp4",
      "size_bytes": 89010,
      "duration_seconds": 20.0,
      "category": "커뮤니케이션",
      "title": "업무 메일 첫 문장 쓰는 법",
      "tags": [
        "이메일",
        "글쓰기"
      ],
      "core_content": "업무 메일은 첫 문장에 목적을 밝힙니다. 인사 뒤에 요청이나 공유 내용을 한 줄로 먼저 씁니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "a6444bbd94c7870e1008d4fac605c906498506c8ae9425418732dd846634de05"
    },
    {
      "number": 6,
      "video_asset_id": "2f873b4e-c96b-57bd-95e6-8f2f0923bd0a",
      "storage_path": "dozone-demo-20261029/06.mp4",
      "original_name": "보고는 결론부터 두괄식 말하기.mp4",
      "size_bytes": 87013,
      "duration_seconds": 20.0,
      "category": "커뮤니케이션",
      "title": "보고는 결론부터 두괄식 말하기",
      "tags": [
        "보고",
        "말하기"
      ],
      "core_content": "보고는 결론을 먼저 말하고 근거를 이어 붙입니다. 듣는 사람이 판단할 내용을 앞에 둡니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "5d49f59d89a8bb12cfef4664ac5442593ea54b6a754324a4671737ae35f3e38a"
    },
    {
      "number": 7,
      "video_asset_id": "ec30e7f0-f045-5be1-81fe-e7f6bc94840f",
      "storage_path": "dozone-demo-20261029/07.mp4",
      "original_name": "회의록 5줄로 정리하는 템플릿.mp4",
      "size_bytes": 90181,
      "duration_seconds": 20.0,
      "category": "커뮤니케이션",
      "title": "회의록 5줄로 정리하는 템플릿",
      "tags": [
        "회의록",
        "문서작성"
      ],
      "core_content": "회의록은 일시, 참석자, 결정 사항, 할 일, 담당자 다섯 줄로 정리합니다. 결정과 할 일을 구분해 적습니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "5d2db4ad3812d546597770566c0aed1b63d6b264e464017dee60562cc4a31f9a"
    },
    {
      "number": 8,
      "video_asset_id": "654d4f13-a190-57d7-b1da-44b408ea643d",
      "storage_path": "dozone-demo-20261029/08.mp4",
      "original_name": "평균과 중앙값 언제 무엇을 쓸까.mp4",
      "size_bytes": 94492,
      "duration_seconds": 20.0,
      "category": "데이터",
      "title": "평균과 중앙값 언제 무엇을 쓸까",
      "tags": [
        "통계",
        "데이터"
      ],
      "core_content": "평균은 극단값에 영향을 크게 받습니다. 값이 한쪽으로 치우치면 중앙값이 대표값으로 더 적합합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "d941899028367173d54a2d62c6b56e5f84f2bc1f7f138073a920c9bee9aebd87"
    },
    {
      "number": 9,
      "video_asset_id": "9416ec95-3fe8-5352-9076-43dd4b90c4dc",
      "storage_path": "dozone-demo-20261029/09.mp4",
      "original_name": "SQL SELECT 기본 문법 한눈에.mp4",
      "size_bytes": 89759,
      "duration_seconds": 20.0,
      "category": "데이터",
      "title": "SQL SELECT 기본 문법 한눈에",
      "tags": [
        "SQL",
        "데이터베이스"
      ],
      "core_content": "SELECT는 조회할 열을, FROM은 테이블을 지정합니다. WHERE로 조건을 걸어 필요한 행만 가져옵니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "0be30a41a8f07ab105a109ed3949f7e2c6f6d8339e2eff3992acaf44719d5c59"
    },
    {
      "number": 10,
      "video_asset_id": "bffa6459-d7e2-504e-b4b3-aae25f6589b2",
      "storage_path": "dozone-demo-20261029/10.mp4",
      "original_name": "막대 vs 선 그래프 고르는 기준.mp4",
      "size_bytes": 87039,
      "duration_seconds": 20.0,
      "category": "데이터",
      "title": "막대 vs 선 그래프 고르는 기준",
      "tags": [
        "시각화",
        "그래프"
      ],
      "core_content": "항목끼리 비교할 때는 막대 그래프를 씁니다. 시간에 따른 변화를 볼 때는 선 그래프가 적합합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "dcee39a0b093684e2d7bf73608a9da8b138f6002bf27462e966002c90c65d59b"
    },
    {
      "number": 11,
      "video_asset_id": "717b386c-28c8-5bc8-91a1-e386568f1317",
      "storage_path": "dozone-demo-20261029/11.mp4",
      "original_name": "RnR이 뭐예요 역할과 책임 정리.mp4",
      "size_bytes": 86017,
      "duration_seconds": 20.0,
      "category": "IT",
      "title": "R&R이 뭐예요? 역할과 책임 정리",
      "tags": [
        "용어",
        "협업"
      ],
      "core_content": "R&R은 역할과 책임을 뜻합니다. 누가 무엇을 맡고 어디까지 책임지는지 정해 업무 혼선을 줄입니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "9b377bd2c15cf325d9533619eac28422c8eae5f6f2b94ba4c2ff72b36c11259a"
    },
    {
      "number": 12,
      "video_asset_id": "565b5be3-c5d0-560f-a141-50c507732a70",
      "storage_path": "dozone-demo-20261029/12.mp4",
      "original_name": "Git 커밋 메시지 잘 쓰는 법.mp4",
      "size_bytes": 81088,
      "duration_seconds": 20.0,
      "category": "IT",
      "title": "Git 커밋 메시지 잘 쓰는 법",
      "tags": [
        "Git",
        "개발"
      ],
      "core_content": "커밋 메시지는 유형과 변경 내용을 한 줄로 씁니다. 무엇을 왜 바꿨는지 알 수 있게 작성합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "f75fca4f01afe0f4c9e7903463a8208b64129e52895fdb57461c7c99262d0a28"
    },
    {
      "number": 13,
      "video_asset_id": "7cbbf6b3-3261-5307-a449-6464caab7cec",
      "storage_path": "dozone-demo-20261029/13.mp4",
      "original_name": "명함 주고받는 순서와 예절.mp4",
      "size_bytes": 88292,
      "duration_seconds": 20.0,
      "category": "비즈니스 매너",
      "title": "명함 주고받는 순서와 예절",
      "tags": [
        "매너",
        "첫인상"
      ],
      "core_content": "명함은 아랫사람이 먼저 건넵니다. 받은 명함은 바로 넣지 않고 잠시 확인합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "307ae9f22caccf355c289244ca4e9186f66840fb0db01488d253c18ee8d59651"
    },
    {
      "number": 14,
      "video_asset_id": "bc68e5ec-09ad-5255-ad89-e70715820a35",
      "storage_path": "dozone-demo-20261029/14.mp4",
      "original_name": "뽀모도로 기법 25분 집중하기.mp4",
      "size_bytes": 87958,
      "duration_seconds": 20.0,
      "category": "업무 생산성",
      "title": "뽀모도로 기법 25분 집중하기",
      "tags": [
        "시간관리",
        "집중"
      ],
      "core_content": "25분 집중하고 5분 쉬는 것을 한 단위로 반복합니다. 네 번 반복한 뒤에는 길게 쉽니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "3753da913afbc662afde9e419b3f4a5df5a2d07ad2c6f8c0b2d446bfae1ca1b4"
    },
    {
      "number": 15,
      "video_asset_id": "fb1a1732-dd18-51a7-a5e4-61f4e1a3d292",
      "storage_path": "dozone-demo-20261029/15.mp4",
      "original_name": "할 일 우선순위 아이젠하워 매트릭스.mp4",
      "size_bytes": 91199,
      "duration_seconds": 20.0,
      "category": "업무 생산성",
      "title": "할 일 우선순위 아이젠하워 매트릭스",
      "tags": [
        "시간관리",
        "우선순위"
      ],
      "core_content": "할 일을 긴급성과 중요도로 나눠 네 칸에 배치합니다. 중요하지만 급하지 않은 일에 시간을 먼저 확보합니다.",
      "source": "SASU 자체 제작(목업)",
      "reviewed_on": "2026-10-29",
      "sha256": "b4761ee0fb280a1bec0469303f2b930802d1879397dd483c9cd9e0d41ed595af"
    },
    {
      "number": 16,
      "video_asset_id": "71f3e12b-cc2f-5ceb-99cb-78f7d7b02863",
      "storage_path": "dozone-demo-20261029/16.mp4",
      "original_name": "엑셀 조건부 서식으로 마감일 강조하기.mp4",
      "size_bytes": 10676107,
      "duration_seconds": 21.525,
      "category": "문서·OA",
      "title": "엑셀 조건부 서식으로 마감일 강조하기",
      "tags": [
        "엑셀",
        "서식"
      ],
      "core_content": "조건부 서식은 조건에 맞는 셀에 자동으로 색을 칠합니다. 마감일이 지난 행을 한눈에 찾을 수 있습니다.",
      "source": "SASU 데모 영상팀 01 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "f89fcfc84af690bd3173a067f755812e89dfd88376a33b2fd35894ead7b47026"
    },
    {
      "number": 17,
      "video_asset_id": "e909125f-2f4b-53e2-b886-5d6409a310a5",
      "storage_path": "dozone-demo-20261029/17.mp4",
      "original_name": "1분 자기소개, 이렇게 시작하세요.mp4",
      "size_bytes": 21865515,
      "duration_seconds": 20.8,
      "category": "커뮤니케이션",
      "title": "1분 자기소개, 이렇게 시작하세요",
      "tags": [
        "자기소개",
        "말하기"
      ],
      "core_content": "자기소개는 이름, 하는 일, 강점 순서로 짧게 말합니다. 마지막에 함께 일하고 싶은 이유를 덧붙입니다.",
      "source": "SASU 데모 영상팀 02 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "1f196ae940f489830d6ee69d9295d5cad61d57971d6fdd5886701c8cd62555ed"
    },
    {
      "number": 18,
      "video_asset_id": "f0ea44fe-50f1-5054-a027-0695e45e639c",
      "storage_path": "dozone-demo-20261029/18.mp4",
      "original_name": "거절할 때 쓰는 부드러운 말투 3가지.mp4",
      "size_bytes": 62796707,
      "duration_seconds": 34.282,
      "category": "커뮤니케이션",
      "title": "거절할 때 쓰는 부드러운 말투 3가지",
      "tags": [
        "거절",
        "대화"
      ],
      "core_content": "거절할 때는 이유와 대안을 함께 말합니다. 감사 표현으로 시작하면 관계를 해치지 않습니다.",
      "source": "SASU 데모 영상팀 03 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "8fda281f450cef1aa53edcb10b93e821a72cc7ca7bc7d246ce2600ec6cd82b17"
    },
    {
      "number": 19,
      "video_asset_id": "25672be2-1a60-5386-8763-bb2097f86439",
      "storage_path": "dozone-demo-20261029/19.mp4",
      "original_name": "화상회의 전 체크리스트 5가지.mp4",
      "size_bytes": 2025895,
      "duration_seconds": 10.0,
      "category": "업무 생산성",
      "title": "화상회의 전 체크리스트 5가지",
      "tags": [
        "화상회의",
        "준비"
      ],
      "core_content": "카메라, 마이크, 조명, 배경, 공유할 화면을 미리 확인합니다. 시작 5분 전에 접속해 두면 지연을 줄일 수 있습니다.",
      "source": "SASU 데모 영상팀 04 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "12ee5871447fdebeaa4bb263fb6853d6097617562e2a9fe124c015bae54ed4d6"
    },
    {
      "number": 20,
      "video_asset_id": "24888744-f0fc-5497-855e-ee1f990890b0",
      "storage_path": "dozone-demo-20261029/20.mp4",
      "original_name": "업무 메모, 노션으로 정리하는 법.mp4",
      "size_bytes": 19559912,
      "duration_seconds": 17.04,
      "category": "업무 생산성",
      "title": "업무 메모, 노션으로 정리하는 법",
      "tags": [
        "노션",
        "메모"
      ],
      "core_content": "메모는 날짜와 주제별 페이지로 나눠 정리합니다. 태그를 달면 나중에 관련 메모를 쉽게 찾습니다.",
      "source": "SASU 데모 영상팀 05 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "2f987227fe196c45928c1df0dab548310caf980763476cb13627ccc9694a509f"
    },
    {
      "number": 21,
      "video_asset_id": "33c0ef4e-f904-5e21-b76f-be6ff2d7fa03",
      "storage_path": "dozone-demo-20261029/21.mp4",
      "original_name": "KPI와 OKR 차이 한 번에 이해하기.mp4",
      "size_bytes": 14510089,
      "duration_seconds": 10.027,
      "category": "비즈니스 기초",
      "title": "KPI와 OKR 차이 한 번에 이해하기",
      "tags": [
        "KPI",
        "OKR"
      ],
      "core_content": "KPI는 성과를 꾸준히 측정하는 지표입니다. OKR은 도전적인 목표와 그 달성 여부를 확인할 핵심 결과를 함께 정합니다.",
      "source": "SASU 데모 영상팀 06 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "00c4c09e412fadf04822eb0efddd66f6e06ae4db0fd79bff1e803c38cb094fb7"
    },
    {
      "number": 22,
      "video_asset_id": "7ff64bc9-3866-5193-960e-b15341b9dc7c",
      "storage_path": "dozone-demo-20261029/22.mp4",
      "original_name": "보고서 그래프 색상 고르는 기준.mp4",
      "size_bytes": 19404320,
      "duration_seconds": 12.32,
      "category": "데이터",
      "title": "보고서 그래프 색상 고르는 기준",
      "tags": [
        "시각화",
        "디자인"
      ],
      "core_content": "강조할 항목 하나에만 진한 색을 씁니다. 나머지는 회색 계열로 두면 핵심이 잘 드러납니다.",
      "source": "SASU 데모 영상팀 07 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "590c8a7238b07ff860771477ab90bf1ff44b27818668ec8067bcda4faf6e0a39"
    },
    {
      "number": 23,
      "video_asset_id": "236add78-78f4-5f75-92af-a83e766dd85c",
      "storage_path": "dozone-demo-20261029/23.mp4",
      "original_name": "비밀번호 관리, 이것만 지키세요.mp4",
      "size_bytes": 15653919,
      "duration_seconds": 10.73,
      "category": "IT",
      "title": "비밀번호 관리, 이것만 지키세요",
      "tags": [
        "보안",
        "비밀번호"
      ],
      "core_content": "사이트마다 다른 비밀번호를 사용합니다. 비밀번호 관리자와 2단계 인증을 함께 쓰면 안전합니다.",
      "source": "SASU 데모 영상팀 08 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "0cfe21d3a539ff09a4afbab0ec049ba6da6df475c194fe2f3081779d7fea02ef"
    },
    {
      "number": 24,
      "video_asset_id": "a477b90d-4905-53d5-b802-48e28f51fae9",
      "storage_path": "dozone-demo-20261029/24.mp4",
      "original_name": "첫 출근 날 꼭 챙길 것들.mp4",
      "size_bytes": 22565861,
      "duration_seconds": 10.01,
      "category": "비즈니스 매너",
      "title": "첫 출근 날 꼭 챙길 것들",
      "tags": [
        "첫출근",
        "매너"
      ],
      "core_content": "신분증, 서류, 필기구를 미리 챙깁니다. 출근 시간보다 10분 일찍 도착해 인사를 준비합니다.",
      "source": "SASU 데모 영상팀 09 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "c879dd3ececc756ee3755bbcbe4b83d03a752c09dba0aede08504332967309d2"
    },
    {
      "number": 25,
      "video_asset_id": "5c83ac16-d100-5a37-a55b-12ae7d5403c7",
      "storage_path": "dozone-demo-20261029/25.mp4",
      "original_name": "집중력 높이는 책상 정리 습관.mp4",
      "size_bytes": 23803989,
      "duration_seconds": 16.417,
      "category": "업무 생산성",
      "title": "집중력 높이는 책상 정리 습관",
      "tags": [
        "정리",
        "집중"
      ],
      "core_content": "책상에는 지금 하는 일에 필요한 물건만 둡니다. 퇴근 전에 정리하면 다음 날 바로 시작할 수 있습니다.",
      "source": "SASU 데모 영상팀 10 (가상 출처)",
      "reviewed_on": "2026-10-29",
      "sha256": "126e60887b7f86715833f5b551ab1ed7280c6dc6a7d689111f3b74420196c8b9"
    }
  ],
  "quizzes": [
    {
      "content_number": 1,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "VLOOKUP 함수는 어떤 작업에 사용하나요?",
          "explanation": "VLOOKUP은 기준 값으로 다른 표의 값을 찾아옵니다. 찾을 값, 범위, 열 번호, 일치 옵션 순서로 입력합니다.",
          "options": [
            {
              "text": "셀의 글자색만 바꾼다",
              "correct": false
            },
            {
              "text": "VLOOKUP으로 기준값에 대응하는 정보를 찾는다",
              "correct": true
            },
            {
              "text": "현재 표의 모든 행을 삭제한다",
              "correct": false
            }
          ]
        },
        {
          "question_type": "MCQ3",
          "question_text": "다른 표에서 사번을 기준으로 부서명을 찾으려 합니다. 알맞은 방법은 무엇인가요?",
          "explanation": "VLOOKUP은 기준 값으로 다른 표의 값을 찾아옵니다. 찾을 값, 범위, 열 번호, 일치 옵션 순서로 입력합니다.",
          "options": [
            {
              "text": "셀의 글자색만 바꾼다",
              "correct": false
            },
            {
              "text": "VLOOKUP으로 기준값에 대응하는 정보를 찾는다",
              "correct": true
            },
            {
              "text": "현재 표의 모든 행을 삭제한다",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 2,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "피벗 테이블은 원본 데이터를 원하는 기준으로 요약할 수 있다.",
          "explanation": "피벗 테이블은 원본 데이터를 원하는 기준으로 요약합니다. 행에 월, 값에 매출을 넣으면 월별 합계가 나옵니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        },
        {
          "question_type": "OX",
          "question_text": "피벗 테이블에서 행에 월, 값에 매출을 배치하면 월별 매출 합계를 볼 수 있다.",
          "explanation": "피벗 테이블은 원본 데이터를 원하는 기준으로 요약합니다. 행에 월, 값에 매출을 넣으면 월별 합계가 나옵니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 3,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "여러 도형의 간격을 맞추는 기능은 무엇인가요?",
          "explanation": "정렬 기능을 쓰면 도형을 일정한 간격으로 맞출 수 있습니다. 여러 개를 선택한 뒤 맞춤 메뉴를 사용합니다.",
          "options": [
            {
              "text": "파일 암호 설정",
              "correct": false
            },
            {
              "text": "도형을 선택한 뒤 맞춤·간격 정렬 기능",
              "correct": true
            },
            {
              "text": "슬라이드 숨기기",
              "correct": false
            },
            {
              "text": "글꼴 색상 변경",
              "correct": false
            }
          ]
        },
        {
          "question_type": "MCQ4",
          "question_text": "슬라이드의 도형 여러 개를 같은 간격으로 배치하려면 무엇을 사용해야 할까요?",
          "explanation": "정렬 기능을 쓰면 도형을 일정한 간격으로 맞출 수 있습니다. 여러 개를 선택한 뒤 맞춤 메뉴를 사용합니다.",
          "options": [
            {
              "text": "파일 암호 설정",
              "correct": false
            },
            {
              "text": "도형을 선택한 뒤 맞춤·간격 정렬 기능",
              "correct": true
            },
            {
              "text": "슬라이드 숨기기",
              "correct": false
            },
            {
              "text": "글꼴 색상 변경",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 4,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "워드 문서의 내용이 바뀌어도 목차를 쉽게 갱신하려면 어떻게 작성해야 할까요?",
          "explanation": "제목 스타일을 지정하면 목차를 자동으로 만들 수 있습니다. 내용이 바뀌면 목차 업데이트만 누르면 됩니다.",
          "options": [
            {
              "text": "목차의 페이지 번호를 이미지로 붙인다",
              "correct": false
            },
            {
              "text": "모든 문단을 일반 본문으로 작성한다",
              "correct": false
            },
            {
              "text": "제목 스타일을 지정하고 자동 목차를 사용한다",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 5,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "업무 메일은 인사 뒤 첫 문장에서 요청이나 공유 목적을 밝히는 것이 좋다.",
          "explanation": "업무 메일은 첫 문장에 목적을 밝힙니다. 인사 뒤에 요청이나 공유 내용을 한 줄로 먼저 씁니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 6,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "일정 지연을 상사에게 보고할 때 두괄식으로 말한 예시는 무엇인가요?",
          "explanation": "보고는 결론을 먼저 말하고 근거를 이어 붙입니다. 듣는 사람이 판단할 내용을 앞에 둡니다.",
          "options": [
            {
              "text": "납기가 하루 늦어질 예정입니다. 원인과 대응 방안을 말씀드리겠습니다.",
              "correct": true
            },
            {
              "text": "어제 있었던 일을 시간순으로 모두 말씀드리겠습니다.",
              "correct": false
            },
            {
              "text": "관련 이야기를 먼저 길게 하고 결론은 마지막에 말씀드리겠습니다.",
              "correct": false
            },
            {
              "text": "배경 설명만 하고 결론은 전달하지 않겠습니다.",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 7,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "회의록을 작성할 때 결정 사항과 함께 남겨야 할 내용은 무엇인가요?",
          "explanation": "회의록은 일시, 참석자, 결정 사항, 할 일, 담당자 다섯 줄로 정리합니다. 결정과 할 일을 구분해 적습니다.",
          "options": [
            {
              "text": "참석자의 취미와 선호 음식",
              "correct": false
            },
            {
              "text": "할 일과 담당자",
              "correct": true
            },
            {
              "text": "회의실 벽지 색상",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 8,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "평균은 극단적으로 큰 값이나 작은 값의 영향을 전혀 받지 않는다.",
          "explanation": "평균은 극단값에 영향을 크게 받습니다. 값이 한쪽으로 치우치면 중앙값이 대표값으로 더 적합합니다.",
          "options": [
            {
              "text": "O",
              "correct": false
            },
            {
              "text": "X",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 9,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "SQL에서 조회할 데이터의 조건을 지정하는 절은 무엇인가요?",
          "explanation": "SELECT는 조회할 열을, FROM은 테이블을 지정합니다. WHERE로 조건을 걸어 필요한 행만 가져옵니다.",
          "options": [
            {
              "text": "SELECT",
              "correct": false
            },
            {
              "text": "FROM",
              "correct": false
            },
            {
              "text": "WHERE",
              "correct": true
            },
            {
              "text": "AS",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 10,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "월별 매출이 시간에 따라 어떻게 변하는지 보여주려 합니다. 알맞은 그래프는 무엇인가요?",
          "explanation": "항목끼리 비교할 때는 막대 그래프를 씁니다. 시간에 따른 변화를 볼 때는 선 그래프가 적합합니다.",
          "options": [
            {
              "text": "항목별 개수만 나열한 표",
              "correct": false
            },
            {
              "text": "선 그래프",
              "correct": true
            },
            {
              "text": "내용과 관계없는 이미지",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 11,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "R&R은 누가 무엇을 맡고 어디까지 책임지는지 정하는 역할과 책임을 뜻한다.",
          "explanation": "R&R은 역할과 책임을 뜻합니다. 누가 무엇을 맡고 어디까지 책임지는지 정해 업무 혼선을 줄입니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 12,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "변경 내용을 구체적으로 알 수 있는 커밋 메시지는 무엇인가요?",
          "explanation": "커밋 메시지는 유형과 변경 내용을 한 줄로 씁니다. 무엇을 왜 바꿨는지 알 수 있게 작성합니다.",
          "options": [
            {
              "text": "수정",
              "correct": false
            },
            {
              "text": "feat: 사용자 조회 API 구현",
              "correct": true
            },
            {
              "text": "최종 진짜 최종",
              "correct": false
            },
            {
              "text": "여러 가지 작업",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 13,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "데모 자료에서 안내한 명함을 받은 직후의 행동으로 알맞은 것은 무엇인가요?",
          "explanation": "명함은 아랫사람이 먼저 건넵니다. 받은 명함은 바로 넣지 않고 잠시 확인합니다.",
          "options": [
            {
              "text": "읽지 않고 바로 주머니에 넣는다",
              "correct": false
            },
            {
              "text": "받자마자 메모지로 사용한다",
              "correct": false
            },
            {
              "text": "이름과 소속을 잠시 확인한다",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 14,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "소개된 뽀모도로 방식은 25분 집중하고 5분 쉬는 단위를 반복한다.",
          "explanation": "25분 집중하고 5분 쉬는 것을 한 단위로 반복합니다. 네 번 반복한 뒤에는 길게 쉽니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 15,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "아이젠하워 매트릭스에서 일을 나누는 두 가지 기준은 무엇인가요?",
          "explanation": "할 일을 긴급성과 중요도로 나눠 네 칸에 배치합니다. 중요하지만 급하지 않은 일에 시간을 먼저 확보합니다.",
          "options": [
            {
              "text": "긴급성과 중요도",
              "correct": true
            },
            {
              "text": "파일 크기와 이름",
              "correct": false
            },
            {
              "text": "담당자의 나이와 직급",
              "correct": false
            },
            {
              "text": "회의실과 좌석 위치",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 16,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "마감일이 지난 행을 자동으로 강조하려면 엑셀의 어떤 기능이 적합할까요?",
          "explanation": "조건부 서식은 조건에 맞는 셀에 자동으로 색을 칠합니다. 마감일이 지난 행을 한눈에 찾을 수 있습니다.",
          "options": [
            {
              "text": "시트 이름 변경",
              "correct": false
            },
            {
              "text": "파일 압축",
              "correct": false
            },
            {
              "text": "조건부 서식",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 17,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "소개된 자기소개 방식은 이름과 하는 일을 생략하고 취미만 길게 설명하는 것이다.",
          "explanation": "자기소개는 이름, 하는 일, 강점 순서로 짧게 말합니다. 마지막에 함께 일하고 싶은 이유를 덧붙입니다.",
          "options": [
            {
              "text": "O",
              "correct": false
            },
            {
              "text": "X",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 18,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "요청을 거절하면서 관계를 배려하는 표현으로 가장 알맞은 것은 무엇인가요?",
          "explanation": "거절할 때는 이유와 대안을 함께 말합니다. 감사 표현으로 시작하면 관계를 해치지 않습니다.",
          "options": [
            {
              "text": "안 됩니다. 더 설명하지 않겠습니다.",
              "correct": false
            },
            {
              "text": "왜 그런 요청을 했는지 모르겠습니다.",
              "correct": false
            },
            {
              "text": "답변을 하지 않고 넘어갑니다.",
              "correct": false
            },
            {
              "text": "제안해 주셔서 감사합니다. 지금은 일정상 어렵지만 다음 주에는 도와드릴 수 있습니다.",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 19,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "화상회의 전에 확인할 항목으로 알맞은 것은 무엇인가요?",
          "explanation": "카메라, 마이크, 조명, 배경, 공유할 화면을 미리 확인합니다. 시작 5분 전에 접속해 두면 지연을 줄일 수 있습니다.",
          "options": [
            {
              "text": "카메라·마이크·조명·배경·공유 화면",
              "correct": true
            },
            {
              "text": "회의와 무관한 게임 설정",
              "correct": false
            },
            {
              "text": "다른 사람의 개인 문서",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 20,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "업무 메모를 날짜와 주제별로 나누고 태그를 붙이면 나중에 관련 내용을 찾기 쉽다.",
          "explanation": "메모는 날짜와 주제별 페이지로 나눠 정리합니다. 태그를 달면 나중에 관련 메모를 쉽게 찾습니다.",
          "options": [
            {
              "text": "O",
              "correct": true
            },
            {
              "text": "X",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 21,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "KPI와 OKR에 대한 설명으로 알맞은 것은 무엇인가요?",
          "explanation": "KPI는 성과를 꾸준히 측정하는 지표입니다. OKR은 도전적인 목표와 그 달성 여부를 확인할 핵심 결과를 함께 정합니다.",
          "options": [
            {
              "text": "둘 다 파일 확장자이다",
              "correct": false
            },
            {
              "text": "KPI는 명함 예절, OKR은 이메일 제목이다",
              "correct": false
            },
            {
              "text": "KPI는 성과 측정 지표이고 OKR은 목표와 핵심 결과를 함께 정하는 방식이다",
              "correct": true
            },
            {
              "text": "둘 다 업무와 무관한 단축키이다",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 22,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "보고서 그래프에서 핵심 항목을 강조하는 방법으로 알맞은 것은 무엇인가요?",
          "explanation": "강조할 항목 하나에만 진한 색을 씁니다. 나머지는 회색 계열로 두면 핵심이 잘 드러납니다.",
          "options": [
            {
              "text": "강조할 항목에 진한 색을 쓰고 나머지는 차분한 색으로 구분한다",
              "correct": true
            },
            {
              "text": "모든 항목에 서로 다른 강한 색을 사용한다",
              "correct": false
            },
            {
              "text": "중요한 항목을 배경과 같은 색으로 숨긴다",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 23,
      "versions": [
        {
          "question_type": "OX",
          "question_text": "여러 사이트에 동일한 비밀번호를 사용하면 계정 보안을 높일 수 있다.",
          "explanation": "사이트마다 다른 비밀번호를 사용합니다. 비밀번호 관리자와 2단계 인증을 함께 쓰면 안전합니다.",
          "options": [
            {
              "text": "O",
              "correct": false
            },
            {
              "text": "X",
              "correct": true
            }
          ]
        }
      ]
    },
    {
      "content_number": 24,
      "versions": [
        {
          "question_type": "MCQ4",
          "question_text": "첫 출근 전 준비로 알맞은 것은 무엇인가요?",
          "explanation": "신분증, 서류, 필기구를 미리 챙깁니다. 출근 시간보다 10분 일찍 도착해 인사를 준비합니다.",
          "options": [
            {
              "text": "필요 서류는 확인하지 않는다",
              "correct": false
            },
            {
              "text": "신분증·필요 서류·필기구를 챙기고 도착 시간을 확인한다",
              "correct": true
            },
            {
              "text": "출근 장소는 도착 후 알아본다",
              "correct": false
            },
            {
              "text": "준비물을 모두 동료에게 빌리기로 한다",
              "correct": false
            }
          ]
        }
      ]
    },
    {
      "content_number": 25,
      "versions": [
        {
          "question_type": "MCQ3",
          "question_text": "집중하기 좋은 책상을 만드는 습관으로 알맞은 것은 무엇인가요?",
          "explanation": "책상에는 지금 하는 일에 필요한 물건만 둡니다. 퇴근 전에 정리하면 다음 날 바로 시작할 수 있습니다.",
          "options": [
            {
              "text": "현재 작업에 필요한 물건 위주로 두고 퇴근 전에 정리한다",
              "correct": true
            },
            {
              "text": "모든 물건을 항상 책상 위에 쌓아 둔다",
              "correct": false
            },
            {
              "text": "중요 서류를 찾기 어렵게 섞어 둔다",
              "correct": false
            }
          ]
        }
      ]
    }
  ],
  "curricula": [
    {
      "title": "엑셀 실무 첫걸음",
      "description": "조회 함수, 피벗 테이블, 조건부 서식을 순서대로 익힙니다.",
      "content_numbers": [
        1,
        2,
        16
      ]
    },
    {
      "title": "문서와 보고서 정리",
      "description": "슬라이드·문서·회의록·메모·그래프를 깔끔하게 정리하는 과정입니다.",
      "content_numbers": [
        3,
        4,
        7,
        20,
        22
      ]
    },
    {
      "title": "업무 소통 기본기",
      "description": "메일 작성부터 보고, 자기소개와 거절 표현까지 연습합니다.",
      "content_numbers": [
        5,
        6,
        17,
        18
      ]
    },
    {
      "title": "데이터와 IT 기초",
      "description": "데이터 해석, SQL, 그래프와 개발·보안의 기본 개념을 확인합니다.",
      "content_numbers": [
        8,
        9,
        10,
        12,
        23
      ]
    },
    {
      "title": "신입 온보딩 가이드",
      "description": "역할과 책임, 비즈니스 매너, 목표 관리와 첫 출근을 준비합니다.",
      "content_numbers": [
        11,
        13,
        21,
        24
      ]
    },
    {
      "title": "하루 업무 생산성",
      "description": "집중 시간, 우선순위, 화상회의 준비와 업무 환경을 점검합니다.",
      "content_numbers": [
        14,
        15,
        19,
        25
      ]
    }
  ],
  "learning_demo": {
    "username": "demo_dozone",
    "display_name": "데모 학습자",
    "last_content_number": 18,
    "likes": [
      1,
      2,
      3,
      5,
      7,
      9,
      12,
      16
    ],
    "saved": [
      1,
      4,
      6,
      8,
      10,
      14,
      17,
      20
    ],
    "watches": [
      {
        "content_number": 1,
        "visit_id": "af62fac8-da53-5ea4-8f56-baf7257ec804",
        "coverage": 1
      },
      {
        "content_number": 2,
        "visit_id": "d2ec201a-ba7b-59b3-a7bd-08ba14d0219b",
        "coverage": 1
      },
      {
        "content_number": 3,
        "visit_id": "6e67d1ee-f15a-5668-b313-eccc78a5a412",
        "coverage": 1
      },
      {
        "content_number": 4,
        "visit_id": "50648194-4c25-5367-a994-4789ee6ebb94",
        "coverage": 1
      },
      {
        "content_number": 5,
        "visit_id": "5c808fdb-efd8-56b3-a356-ae5fb5219fae",
        "coverage": 1
      },
      {
        "content_number": 6,
        "visit_id": "c95e06cf-2aca-5fb4-9f0c-20ecf53b488f",
        "coverage": 1
      },
      {
        "content_number": 7,
        "visit_id": "ca30c30a-a284-56ca-993a-4c84e53ef9e1",
        "coverage": 1
      },
      {
        "content_number": 8,
        "visit_id": "f0e21825-a75a-58e0-8135-d588e871ba9d",
        "coverage": 1
      },
      {
        "content_number": 9,
        "visit_id": "ad9f8356-2762-5c9f-bf47-43fd360dcfcc",
        "coverage": 1
      },
      {
        "content_number": 10,
        "visit_id": "0fa109b2-49f0-517e-b247-96872a3fcb21",
        "coverage": 1
      },
      {
        "content_number": 11,
        "visit_id": "60603e80-9c4b-5b75-8e5e-4a62b6a238c1",
        "coverage": 1
      },
      {
        "content_number": 12,
        "visit_id": "5d0a49ce-3872-5fb1-8022-0a7b4db981f3",
        "coverage": 1
      },
      {
        "content_number": 13,
        "visit_id": "e7a81a85-f2f5-5cb6-8286-a7f60816871e",
        "coverage": 0.55
      },
      {
        "content_number": 14,
        "visit_id": "2ae7a05f-0093-5514-8645-761035abc9aa",
        "coverage": 0.55
      },
      {
        "content_number": 15,
        "visit_id": "35a00bc2-a721-5269-991f-731b5a02831b",
        "coverage": 0.55
      },
      {
        "content_number": 16,
        "visit_id": "e2228f4a-93d4-5b3d-ba1f-9a6de92b667b",
        "coverage": 1
      },
      {
        "content_number": 17,
        "visit_id": "0d82af1a-4cdf-56f4-8c22-44ec60055f75",
        "coverage": 0.55
      },
      {
        "content_number": 18,
        "visit_id": "9ad6f24a-3078-5512-ab39-c6dd47d7ee18",
        "coverage": 0.55
      }
    ],
    "attempts": [
      {
        "content_number": 1,
        "version_no": 1,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "ee72964d-65cd-53bd-bfe2-9462c76f1380",
        "event_id": "0e904778-f808-5487-a206-817a6bcdb267"
      },
      {
        "content_number": 1,
        "context": "VIDEO_END",
        "result": "CORRECT",
        "attempt_id": "889b6b2a-4cd3-514c-bef9-0b639b162f62",
        "event_id": "abcaf6e5-3b93-58e9-9206-3c612c5c566e"
      },
      {
        "content_number": 2,
        "context": "VIDEO_END",
        "result": "CORRECT",
        "attempt_id": "a622340b-5b5b-5f39-acde-d7c35c7dba60",
        "event_id": "a0267d73-46b6-574e-b957-89f7edaf7cdd"
      },
      {
        "content_number": 3,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "b9382bad-8de8-5405-9b9c-88afac1b5129",
        "event_id": "1d763d6c-fe9d-5f9e-9fad-115d9ec6e703"
      },
      {
        "content_number": 4,
        "context": "VIDEO_END",
        "result": "SKIPPED",
        "attempt_id": "1e847864-942d-58af-9370-2a71b4aef6a7",
        "event_id": "904d97e9-e9af-597f-b070-175c214a50eb"
      },
      {
        "content_number": 5,
        "context": "FEED_REVIEW",
        "result": "CORRECT",
        "attempt_id": "23ced385-39b3-52be-bff2-205ba899d0dd",
        "event_id": "d0380418-2630-5d5b-82a3-f2a1c7732335"
      },
      {
        "content_number": 6,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "e5da1870-8322-5885-91da-96e73d6e3da3",
        "event_id": "88e5059f-6bbd-56f9-87e3-fadd6c6edaac"
      },
      {
        "content_number": 7,
        "context": "FEED_REVIEW",
        "result": "CORRECT",
        "attempt_id": "16353ed4-18a6-5373-a417-becda08bca96",
        "event_id": "81137414-9493-5315-8f38-6845f4901e52"
      },
      {
        "content_number": 8,
        "context": "VIDEO_END",
        "result": "SKIPPED",
        "attempt_id": "db9d154e-4bb9-5ee8-8901-f1321a0cd975",
        "event_id": "a5f61fc5-109b-5ef8-ba00-571c83d604f4"
      },
      {
        "content_number": 9,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "283a4ae2-89d4-5c9c-b053-70c0b24bad97",
        "event_id": "f770f0aa-febc-54b5-a5e0-7d65e1d89228"
      },
      {
        "content_number": 10,
        "context": "FEED_REVIEW",
        "result": "CORRECT",
        "attempt_id": "d3a66e08-faea-5ad6-a71a-4f96ff22309e",
        "event_id": "d3c505fa-1358-5002-a77c-3f18cf07c714"
      },
      {
        "content_number": 11,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "e18108d5-2d1b-5d42-ac19-9fd50d4ec4b5",
        "event_id": "9befad20-0e54-5cbc-9c5e-c39ee445afc5"
      },
      {
        "content_number": 12,
        "context": "VIDEO_END",
        "result": "CORRECT",
        "attempt_id": "0d44f5c1-25bd-54e0-a93d-5ef8a9650ae7",
        "event_id": "34f341f8-2764-5415-88cd-49e385fccfd5"
      },
      {
        "content_number": 13,
        "context": "VIDEO_END",
        "result": "SKIPPED",
        "attempt_id": "0bae2919-1244-55f5-96db-08769a816553",
        "event_id": "e29a3cdc-b4d6-5e11-b68c-dc69bcc6b54f"
      },
      {
        "content_number": 14,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "3e0bcbf5-5066-55ee-bb17-b9a5451a5091",
        "event_id": "bc874256-5145-5459-8a31-5a8b25edf51e"
      },
      {
        "content_number": 15,
        "context": "VIDEO_END",
        "result": "CORRECT",
        "attempt_id": "d6f2988c-48a1-5a54-b284-edb51009c8c6",
        "event_id": "bcf08a91-5398-55d6-bdf1-4ee8c344136c"
      },
      {
        "content_number": 16,
        "context": "VIDEO_END",
        "result": "CORRECT",
        "attempt_id": "556a82fa-8aff-5350-9a93-3a48dcee092c",
        "event_id": "fa872edd-51ed-59a9-99bf-3615049ff4f0"
      },
      {
        "content_number": 17,
        "context": "VIDEO_END",
        "result": "WRONG",
        "attempt_id": "db6d4b67-beb4-586f-ae22-f6947caf8b90",
        "event_id": "4c3e37f6-883a-5d83-a658-34cdd1bda042"
      },
      {
        "content_number": 18,
        "context": "VIDEO_END",
        "result": "SKIPPED",
        "attempt_id": "e6537794-7b27-5046-985e-83b35db87e76",
        "event_id": "64d41b0a-3c63-587a-bffb-261901a0c521"
      },
      {
        "content_number": 3,
        "context": "WRONG_REVIEW",
        "result": "CORRECT",
        "attempt_id": "129d69d9-f342-5812-a206-aea40df3c9c6",
        "event_id": "a3b67e2c-9eaf-512a-b84a-29545a1b9f95"
      },
      {
        "content_number": 6,
        "context": "WRONG_REVIEW",
        "result": "WRONG",
        "attempt_id": "b2a7ae77-0532-5996-b6e0-77b2bdce9636",
        "event_id": "df9f437f-4c36-531b-bb76-5dc0c2b71e41"
      },
      {
        "content_number": 19,
        "context": "VIDEO_END",
        "result": null,
        "attempt_id": "eadb26a6-ed05-5390-bb18-a1180c19a6e0",
        "event_id": "b3af22a9-01cc-5323-973a-b86e763cda48"
      }
    ],
    "cards": [
      {
        "content_number": 1,
        "opened_id": "eb131bd1-33e6-5604-9bb6-fad92c8547b9",
        "revealed_id": "e9c8629d-3a60-5991-a3dd-cdd76ccda5de"
      },
      {
        "content_number": 2,
        "opened_id": "0bac33f1-ee34-54b2-a84e-d866ae4761ce",
        "revealed_id": "3879302f-b41c-56aa-8ad4-29d2497393cf"
      },
      {
        "content_number": 3,
        "opened_id": "843f87cb-5fa7-5a8b-b54d-616e678255ba",
        "revealed_id": "93167354-1c79-5c19-83ed-e9f640ed77fa"
      },
      {
        "content_number": 4,
        "opened_id": "0ab5674c-6654-5708-aae9-1ef2d4ed4ee5",
        "revealed_id": "43c34528-9cce-5489-a45c-df2366627eed"
      },
      {
        "content_number": 5,
        "opened_id": "b7452350-ca1e-5d0b-b56d-5b98f4327620",
        "revealed_id": "dfc3fafc-773e-5fe9-ad39-0ca728decf10"
      },
      {
        "content_number": 6,
        "opened_id": "f707e4a2-4302-55f7-8e8b-26467ca1ffa0",
        "revealed_id": "f3fdce2e-59cc-5eae-bca0-d8c1f9df8ca2"
      },
      {
        "content_number": 7,
        "opened_id": "eed53841-5758-5b07-a9b6-cf3433c0597e",
        "revealed_id": "378b3126-85dc-5137-8f1c-b2bd4e9828dc"
      },
      {
        "content_number": 8,
        "opened_id": "4937349f-1e67-59c9-a6b0-29cd31def5a5",
        "revealed_id": "227d600c-10d2-572e-afa0-5d05565fd0d6"
      },
      {
        "content_number": 9,
        "opened_id": "6b18a691-96e4-5181-ba4b-c35d4a6d7b09",
        "revealed_id": null
      },
      {
        "content_number": 10,
        "opened_id": "358fe26c-fe58-5a9e-89bf-73b5616a8b9b",
        "revealed_id": null
      },
      {
        "content_number": 11,
        "opened_id": "13df492e-1b8d-5590-a727-91c3c1919b8e",
        "revealed_id": null
      },
      {
        "content_number": 12,
        "opened_id": "b5e402f3-1bc2-5a06-b588-b4fe9d7919a2",
        "revealed_id": null
      }
    ],
    "interest_content_numbers": [
      1,
      5
    ]
  }
}
$sasu_demo_data$::jsonb;
    item jsonb;
    account jsonb;
    category jsonb;
    tag_name text;
    selected_user_id bigint;
    admin_id bigint;
    selected_category_id bigint;
    selected_tag_id bigint;
    selected_content_id bigint;
    stored_role text;
    match_count integer;
    added_users integer := 0;
    added_categories integer := 0;
    added_tags integer := 0;
    profile jsonb;
    version jsonb;
    option_item jsonb;
    series jsonb;
    content_number integer;
    step_position integer;
    option_position integer;
    version_no integer;
    selected_quiz_id bigint;
    selected_version_id bigint;
    selected_option_id bigint;
    selected_curriculum_id bigint;
    demo_user_id bigint;
    selected_asset_id uuid;
    media_duration numeric;
    watched_seconds numeric;
    activity_time timestamptz;
    added_quizzes integer := 0;
    added_curricula integer := 0;
BEGIN
    PERFORM set_config('lock_timeout', '15s', true);
    PERFORM pg_advisory_xact_lock(2026102901);
    SET CONSTRAINTS ALL DEFERRED;
    IF to_regclass('sasu.contents') IS NULL THEN
        RAISE EXCEPTION '데모 seed 중단: 먼저 alembic upgrade head로 DB 구조를 준비하세요.';
    END IF;
    LOCK TABLE sasu.app_users, sasu.user_settings, sasu.categories, sasu.tags,
        sasu.video_assets, sasu.contents, sasu.content_tags, sasu.quizzes,
        sasu.quiz_versions, sasu.quiz_options, sasu.curricula, sasu.curriculum_items,
        sasu.user_interests, sasu.watch_visits, sasu.watch_records, sasu.content_likes,
        sasu.saved_contents, sasu.quiz_attempts, sasu.quiz_responses, sasu.wrong_answers,
        sasu.learning_events IN SHARE ROW EXCLUSIVE MODE;

    <<base_seed>>
    BEGIN
    SELECT count(*) INTO match_count
    FROM sasu.video_assets a
    JOIN jsonb_array_elements(dataset->'contents') d
        ON a.video_asset_id = (d->>'video_asset_id')::uuid;

    IF match_count = jsonb_array_length(dataset->'contents') THEN
        IF EXISTS (
            SELECT 1 FROM sasu.video_assets a
            JOIN jsonb_array_elements(dataset->'contents') d
                ON a.video_asset_id = (d->>'video_asset_id')::uuid
            WHERE a.storage_path <> d->>'storage_path'
        ) THEN
            RAISE EXCEPTION '데모 seed 중단: 같은 영상 UUID의 저장 경로가 다릅니다. 기존 데이터를 확인하세요.';
        END IF;
        RAISE NOTICE '기초·콘텐츠 데모가 이미 적용되어 있습니다. 기존 값을 유지하고 보강 단계로 진행합니다.';
        EXIT base_seed;
    ELSIF match_count > 0 THEN
        RAISE EXCEPTION '데모 seed 중단: 영상 %/25개만 존재합니다. 부분 데이터는 자동 복구·덮어쓰지 않습니다.', match_count;
    END IF;

    FOR account IN SELECT * FROM jsonb_array_elements(dataset->'users') LOOP
        SELECT user_id, role INTO selected_user_id, stored_role
        FROM sasu.app_users WHERE username = account->>'username';
        IF FOUND THEN
            IF stored_role <> account->>'role' THEN
                RAISE EXCEPTION '데모 seed 중단: 계정 %의 기존 역할이 다릅니다.', account->>'username';
            END IF;
        ELSE
            INSERT INTO sasu.app_users (username, display_name, role)
            VALUES (account->>'username', account->>'display_name', account->>'role')
            RETURNING user_id INTO selected_user_id;
            added_users := added_users + 1;
        END IF;
        IF account->>'role' = 'LEARNER' THEN
            INSERT INTO sasu.user_settings (user_id) VALUES (selected_user_id)
            ON CONFLICT (user_id) DO NOTHING;
        ELSE
            admin_id := selected_user_id;
        END IF;
    END LOOP;

    FOR category IN SELECT * FROM jsonb_array_elements(dataset->'categories') LOOP
        SELECT count(*), min(category_id) INTO match_count, selected_category_id
        FROM sasu.categories WHERE name = category->>'name';
        IF match_count > 1 THEN
            RAISE EXCEPTION '데모 seed 중단: 카테고리 %가 중복되어 있습니다.', category->>'name';
        ELSIF match_count = 0 THEN
            INSERT INTO sasu.categories (name, group_name, sort_order)
            VALUES (category->>'name', category->>'group_name', (category->>'sort_order')::integer);
            added_categories := added_categories + 1;
        END IF;
    END LOOP;

    FOR item IN SELECT * FROM jsonb_array_elements(dataset->'contents') LOOP
        SELECT category_id INTO STRICT selected_category_id
        FROM sasu.categories WHERE name = item->>'category';

        INSERT INTO sasu.video_assets
            (video_asset_id, storage_path, original_name, mime_type, size_bytes, duration_seconds)
        VALUES ((item->>'video_asset_id')::uuid, item->>'storage_path', item->>'original_name',
            'video/mp4', (item->>'size_bytes')::bigint, (item->>'duration_seconds')::numeric);

        INSERT INTO sasu.contents
            (created_by_user_id, video_asset_id, category_id, title, core_content, source, reviewed_on)
        VALUES (admin_id, (item->>'video_asset_id')::uuid, selected_category_id,
            item->>'title', item->>'core_content', item->>'source', (item->>'reviewed_on')::date)
        RETURNING content_id INTO selected_content_id;

        FOR tag_name IN SELECT jsonb_array_elements_text(item->'tags') LOOP
            SELECT count(*), min(tag_id) INTO match_count, selected_tag_id
            FROM sasu.tags WHERE name = tag_name;
            IF match_count > 1 THEN
                RAISE EXCEPTION '데모 seed 중단: 태그 %가 중복되어 있습니다.', tag_name;
            ELSIF match_count = 0 THEN
                INSERT INTO sasu.tags (name) VALUES (tag_name) RETURNING tag_id INTO selected_tag_id;
                added_tags := added_tags + 1;
            END IF;
            INSERT INTO sasu.content_tags (content_id, tag_id) VALUES (selected_content_id, selected_tag_id);
        END LOOP;
        UPDATE sasu.contents SET status = 'PUBLISHED', published_at = now()
        WHERE content_id = selected_content_id;
    END LOOP;

    RAISE NOTICE '더존 데모 적용 완료: 계정 %개, 분류 %개, 태그 %개 추가; 영상·공개 콘텐츠 각 25개. 기존 설정은 유지합니다.',
        added_users, added_categories, added_tags;
    END base_seed;

    -- 기초·콘텐츠만 넣었던 DB에도 아래 보강을 추가할 수 있다.
    -- 전용 계정을 포함한 보강 전체가 한 트랜잭션이다. 계정이 남아 있으면 재적용하지 않아
    -- 사용자가 수정한 문항·시리즈와 학습 기록 초기화 결과를 그대로 유지한다.
    profile := dataset->'learning_demo';
    IF profile IS NULL THEN RETURN; END IF;
    SELECT user_id, role INTO demo_user_id, stored_role FROM sasu.app_users
    WHERE username = profile->>'username';
    IF FOUND THEN
        IF stored_role <> 'LEARNER' THEN
            RAISE EXCEPTION '데모 seed 중단: 전용 데모 계정의 역할이 다릅니다.';
        END IF;
        RAISE NOTICE '학습 데모 계정이 이미 존재합니다. 문항·시리즈·기록은 재적용하지 않습니다.';
        RETURN;
    END IF;

    INSERT INTO sasu.app_users (username, display_name, role)
    VALUES (profile->>'username', profile->>'display_name', 'LEARNER')
    RETURNING user_id INTO demo_user_id;
    INSERT INTO sasu.user_settings (user_id, onboarding_status)
    VALUES (demo_user_id, 'DONE');

    FOR item IN SELECT * FROM jsonb_array_elements(dataset->'quizzes') LOOP
        SELECT c.content_id INTO STRICT selected_content_id
        FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = (item->>'content_number')::integer;
        -- 관리자가 이미 작성한 문항이 있으면 버전·보기·현재 버전을 모두 보존한다.
        IF EXISTS (SELECT 1 FROM sasu.quizzes WHERE content_id = selected_content_id) THEN
            CONTINUE;
        END IF;
        INSERT INTO sasu.quizzes (content_id) VALUES (selected_content_id)
        RETURNING quiz_id INTO selected_quiz_id;
        version_no := 0;
        FOR version IN SELECT * FROM jsonb_array_elements(item->'versions') LOOP
            version_no := version_no + 1;
            INSERT INTO sasu.quiz_versions
                (quiz_id, version_no, question_type, question_text, explanation)
            VALUES (selected_quiz_id, version_no, version->>'question_type',
                version->>'question_text', version->>'explanation')
            RETURNING quiz_version_id INTO selected_version_id;
            FOR option_item, option_position IN
                SELECT value, ordinality FROM jsonb_array_elements(version->'options') WITH ORDINALITY
            LOOP
                INSERT INTO sasu.quiz_options (quiz_version_id, position, option_text, is_correct)
                VALUES (selected_version_id, option_position, option_item->>'text',
                    (option_item->>'correct')::boolean);
            END LOOP;
        END LOOP;
        UPDATE sasu.quizzes SET current_version_id = selected_version_id
        WHERE quiz_id = selected_quiz_id;
        added_quizzes := added_quizzes + 1;
    END LOOP;

    FOR series IN SELECT * FROM jsonb_array_elements(dataset->'curricula') LOOP
        SELECT count(*) INTO match_count FROM sasu.curricula WHERE title = series->>'title';
        IF match_count > 1 THEN
            RAISE EXCEPTION '데모 seed 중단: 같은 이름의 시리즈가 여러 개입니다: %', series->>'title';
        ELSIF match_count = 1 THEN
            CONTINUE;
        END IF;
        INSERT INTO sasu.curricula (title, description)
        VALUES (series->>'title', series->>'description')
        RETURNING curriculum_id INTO selected_curriculum_id;
        FOR content_number, step_position IN
            SELECT value::integer, ordinality
            FROM jsonb_array_elements_text(series->'content_numbers') WITH ORDINALITY
        LOOP
            SELECT c.content_id INTO STRICT selected_content_id
            FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
                ON c.video_asset_id = (d->>'video_asset_id')::uuid
            WHERE (d->>'number')::integer = content_number;
            INSERT INTO sasu.curriculum_items (curriculum_id, content_id, position)
            VALUES (selected_curriculum_id, selected_content_id, step_position);
        END LOOP;
        added_curricula := added_curricula + 1;
    END LOOP;

    FOR content_number IN SELECT value::integer
        FROM jsonb_array_elements_text(profile->'interest_content_numbers')
    LOOP
        -- 분류 이름을 바꾼 기존 DB에서도 콘텐츠가 실제 참조하는 분야를 사용한다.
        SELECT c.category_id INTO STRICT selected_category_id
        FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = content_number;
        IF selected_category_id IS NOT NULL THEN
            INSERT INTO sasu.user_interests (user_id, category_id)
            VALUES (demo_user_id, selected_category_id) ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;

    FOR item IN SELECT * FROM jsonb_array_elements(profile->'watches') LOOP
        SELECT c.content_id, a.video_asset_id, a.duration_seconds
        INTO STRICT selected_content_id, selected_asset_id, media_duration
        FROM sasu.contents c JOIN sasu.video_assets a USING (video_asset_id)
        JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = (item->>'content_number')::integer;
        watched_seconds := round(media_duration * (item->>'coverage')::numeric, 3);
        activity_time := clock_timestamp();
        INSERT INTO sasu.watch_visits (visit_id, user_id, learning_epoch, content_id, video_asset_id,
            context, elapsed_seconds, watched_ranges, last_sequence, created_at)
        VALUES ((item->>'visit_id')::uuid, demo_user_id, 1, selected_content_id, selected_asset_id,
            'FEED', watched_seconds, jsonb_build_array(jsonb_build_array(0, watched_seconds)), 1,
            activity_time - watched_seconds * interval '1 second');
        INSERT INTO sasu.watch_records (user_id, learning_epoch, content_id, first_played_at,
            last_watched_at, view_counted_at, completed_at, max_coverage_ratio)
        VALUES (demo_user_id, 1, selected_content_id, activity_time - watched_seconds * interval '1 second',
            activity_time, activity_time - (watched_seconds - 3) * interval '1 second',
            CASE WHEN (item->>'coverage')::numeric >= 0.9 THEN activity_time END,
            (item->>'coverage')::numeric);
    END LOOP;

    FOR content_number IN SELECT value::integer FROM jsonb_array_elements_text(profile->'likes') LOOP
        SELECT c.content_id INTO STRICT selected_content_id
        FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = content_number;
        INSERT INTO sasu.content_likes (user_id, learning_epoch, content_id)
        VALUES (demo_user_id, 1, selected_content_id);
    END LOOP;
    FOR content_number IN SELECT value::integer FROM jsonb_array_elements_text(profile->'saved') LOOP
        SELECT c.content_id INTO STRICT selected_content_id
        FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = content_number;
        INSERT INTO sasu.saved_contents (user_id, learning_epoch, content_id)
        VALUES (demo_user_id, 1, selected_content_id);
    END LOOP;

    FOR item IN SELECT * FROM jsonb_array_elements(profile->'attempts') LOOP
        SELECT c.content_id, q.quiz_id, q.current_version_id
        INTO STRICT selected_content_id, selected_quiz_id, selected_version_id
        FROM sasu.contents c JOIN sasu.quizzes q USING (content_id)
        JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = (item->>'content_number')::integer;
        IF item ? 'version_no' THEN
            SELECT quiz_version_id INTO STRICT selected_version_id FROM sasu.quiz_versions
            WHERE quiz_id = selected_quiz_id AND quiz_versions.version_no = (item->>'version_no')::integer;
        END IF;
        activity_time := clock_timestamp();
        INSERT INTO sasu.quiz_attempts (attempt_id, user_id, learning_epoch, quiz_id,
            quiz_version_id, context, created_at)
        VALUES ((item->>'attempt_id')::uuid, demo_user_id, 1, selected_quiz_id,
            selected_version_id, item->>'context', activity_time);
        INSERT INTO sasu.learning_events (event_id, user_id, learning_epoch, event_type,
            content_id, quiz_version_id, attempt_id, occurred_at)
        VALUES ((item->>'event_id')::uuid, demo_user_id, 1, 'QUIZ_DISPLAYED', selected_content_id,
            selected_version_id, (item->>'attempt_id')::uuid, activity_time);
        IF item->>'result' IS NOT NULL THEN
            selected_option_id := NULL;
            IF item->>'result' <> 'SKIPPED' THEN
                SELECT option_id INTO STRICT selected_option_id FROM sasu.quiz_options
                WHERE quiz_version_id = selected_version_id
                  AND is_correct = (item->>'result' = 'CORRECT')
                ORDER BY position LIMIT 1;
            END IF;
            -- 응답 INSERT의 기존 트리거가 오답 생성·누적·해결을 처리한다.
            INSERT INTO sasu.quiz_responses (attempt_id, quiz_version_id, selected_option_id, result, submitted_at)
            VALUES ((item->>'attempt_id')::uuid, selected_version_id, selected_option_id,
                item->>'result', clock_timestamp());
        END IF;
    END LOOP;

    FOR item IN SELECT * FROM jsonb_array_elements(profile->'cards') LOOP
        SELECT c.content_id, q.current_version_id INTO STRICT selected_content_id, selected_version_id
        FROM sasu.contents c JOIN sasu.quizzes q USING (content_id)
        JOIN jsonb_array_elements(dataset->'contents') d
            ON c.video_asset_id = (d->>'video_asset_id')::uuid
        WHERE (d->>'number')::integer = (item->>'content_number')::integer;
        INSERT INTO sasu.learning_events (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id)
        VALUES ((item->>'opened_id')::uuid, demo_user_id, 1, 'CARD_OPENED', selected_content_id, selected_version_id);
        IF item->>'revealed_id' IS NOT NULL THEN
            INSERT INTO sasu.learning_events (event_id, user_id, learning_epoch, event_type, content_id, quiz_version_id)
            VALUES ((item->>'revealed_id')::uuid, demo_user_id, 1, 'CARD_REVEALED', selected_content_id, selected_version_id);
        END IF;
    END LOOP;
    SELECT c.content_id INTO STRICT selected_content_id
    FROM sasu.contents c JOIN jsonb_array_elements(dataset->'contents') d
        ON c.video_asset_id = (d->>'video_asset_id')::uuid
    WHERE (d->>'number')::integer = (profile->>'last_content_number')::integer;
    UPDATE sasu.user_settings SET last_content_id = selected_content_id WHERE user_id = demo_user_id;
    RAISE NOTICE '학습 데모 보강 완료: 새 퀴즈 %개, 시리즈 %개, 데모 학습자 %의 가상 학습 기록 추가.',
        added_quizzes, added_curricula, profile->>'username';
END
$sasu_seed$;
