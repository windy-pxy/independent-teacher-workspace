# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1

RUN pip install --no-cache-dir uv
WORKDIR /app
COPY apps/backend/pyproject.toml apps/backend/uv.lock ./apps/backend/
RUN uv sync --project apps/backend --frozen --no-dev --no-install-project
COPY apps/backend ./apps/backend

ENV PATH="/app/apps/backend/.venv/bin:$PATH" \
    PYTHONPATH="/app/apps/backend/src"
EXPOSE 8000
CMD ["uvicorn", "teacher_workspace.main:app", "--host", "0.0.0.0", "--port", "8000"]
