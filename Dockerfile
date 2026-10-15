# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
# requirements 변경 시에만 설치 레이어를 다시 만들고 다운로드 캐시를 재사용한다.
# 설치나 의존성 검사 실패는 빌드를 실패시킨다.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    python -m pip install --disable-pip-version-check --no-input -r requirements.txt \
    && python -m pip check

COPY app/ ./app/
COPY pyproject.toml ./
COPY tests/ ./tests/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/

RUN mkdir -p /app/storage/videos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
