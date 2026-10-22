"""임시 연동: 담당 파트의 정식 제공 방식이 준비되면 교체할 연결만 모은다.

실제 DB를 조회하며 임의 사용자·세대·시청 상태를 생성하지 않는다.
교체 담당·조건·검증 목록은 agent/saved_contents_integrations.md에 기록한다.
"""

from sqlalchemy.orm import Session

from app.modules.admin.repository import lock_learner_state
from app.modules.contents.models import Content
from app.modules.contents.repository import Presentation, load_presentations


def lock_current_epoch(session: Session, user_id: int) -> int | None:
    # 임시 연동 SAV-T01 / 파트 2·4: 사용자 세대 공통 함수 제공 후 교체한다.
    # 기존 초기화의 행 잠금을 그대로 사용하며 호출자의 트랜잭션을 끝내지 않는다.
    state = lock_learner_state(session, user_id)
    return state["learning_epoch"] if state is not None else None


def load_saved_presentations(
    session: Session, contents: list[Content], user_id: int
) -> list[Presentation]:
    # 임시 연동 SAV-T02 / 파트 2: 시청 완료 조회는 기존 read_tables.watch_records 경유.
    # 임시 연동 SAV-T03 / 파트 3: 문항 존재 조회는 기존 read_tables.quizzes 경유.
    # 임시 연동 SAV-T04 / 파트 4: 집계 조회는 기존 read_tables.content_metrics 경유.
    # 각 담당자의 정식 정의·일괄 조회가 제공되면 contents 조회와 이 연결을 함께 교체한다.
    return load_presentations(session, contents, user_id)
