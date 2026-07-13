# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true
ENV NICO_ALLOW_PROJECT_COMMANDS=true
ENV NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=true
ENV NICO_SCANNER_INSTALL_STRICT=true
ENV NICO_REQUIRE_DURABLE_DELIVERY_STORAGE=true
ENV NICO_TRUST_PROXY_HEADERS=true
ENV NICO_TOOL_TIMEOUT_SECONDS=120
ENV NICO_TOTAL_SCAN_TIMEOUT_SECONDS=1500
ENV NICO_OSV_TIMEOUT_SECONDS=240
ENV NICO_HISTORY_TOOL_TIMEOUT_SECONDS=420

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        nodejs \
        npm \
        tar \
        unzip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin nico

RUN npm install -g eslint typescript --no-audit --no-fund

COPY requirements.txt ./
COPY scripts/install_hosted_scanner_binaries.py ./scripts/install_hosted_scanner_binaries.py
RUN --mount=type=secret,id=github_token \
    if [ -f /run/secrets/github_token ]; then export GITHUB_TOKEN="$(cat /run/secrets/github_token)"; fi \
    && python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pip-audit bandit semgrep coverage \
    && python scripts/install_hosted_scanner_binaries.py

COPY . .
RUN if [ -f apps/web/package-lock.json ]; then cd apps/web && npm ci --ignore-scripts --no-audit --no-fund; fi \
    && chown -R nico:nico /app

USER nico

EXPOSE 8000

CMD ["sh", "-c", "uvicorn nico.api.production:app --host 0.0.0.0 --port ${PORT:-8000}"]
