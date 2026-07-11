FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true
ENV NICO_ALLOW_PROJECT_COMMANDS=true
ENV NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=true
ENV NICO_SCANNER_INSTALL_STRICT=false
ENV NICO_REQUIRE_DURABLE_DELIVERY_STORAGE=true
ENV NICO_TRUST_PROXY_HEADERS=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        nodejs \
        npm \
        tar \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g eslint typescript --no-audit --no-fund \
    || echo "warning: optional eslint/typescript global install unavailable during Docker build"

COPY requirements.txt ./
COPY scripts/install_hosted_scanner_binaries.py ./scripts/install_hosted_scanner_binaries.py
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && (pip install --no-cache-dir pip-audit bandit semgrep coverage \
        || echo "warning: optional Python scanner package install unavailable during Docker build") \
    && (python scripts/install_hosted_scanner_binaries.py \
        || echo "warning: optional hosted scanner binary install unavailable during Docker build")

COPY . .
RUN if [ -f apps/web/package.json ]; then cd apps/web && npm install --legacy-peer-deps --ignore-scripts --no-audit --no-fund || echo "warning: optional frontend dependency install unavailable during backend Docker build"; fi

EXPOSE 8000

CMD ["sh", "-c", "uvicorn nico.api.production:app --host 0.0.0.0 --port ${PORT:-8000}"]
