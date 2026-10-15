"""모델 등록 진입점. 새 모듈에 테이블 모델을 작성하면 이 목록에 추가한다."""

from importlib import import_module

MODEL_MODULES = (
    "app.modules.contents.models",
    "app.modules.users.models",
)


def load_models() -> None:
    for module_name in MODEL_MODULES:
        import_module(module_name)
