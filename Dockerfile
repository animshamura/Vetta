FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data && chown app:app /app/data
USER app

EXPOSE 8000
CMD ["uvicorn", "hernness.api:app", "--host", "0.0.0.0", "--port", "8000"]
