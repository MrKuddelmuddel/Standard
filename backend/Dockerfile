# API and worker image. The same image runs `uvicorn` (api) or `python -m app.workers.runner` (worker).
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY quant ./quant
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install ".[ai]" && useradd --system --uid 10001 nexus && mkdir -p /app/data && chown nexus /app/data
USER nexus

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
