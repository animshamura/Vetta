FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install "pytest==8.3.5" \
    && groupadd --system --gid 10001 sandbox \
    && useradd --system --uid 10001 --gid sandbox --no-create-home sandbox

USER 10001:10001
WORKDIR /workspace
