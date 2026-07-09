FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true
ENV NICO_ALLOW_PROJECT_COMMANDS=true
ENV NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=true

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g eslint typescript

COPY requirements.txt ./
COPY scripts/install_hosted_scanner_binaries.py ./scripts/install_hosted_scanner_binaries.py
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pip-audit bandit semgrep coverage \
    && python scripts/install_hosted_scanner_binaries.py

COPY . .
RUN if [ -f apps/web/package.json ]; then cd apps/web && npm install --legacy-peer-deps --ignore-scripts; fi

EXPOSE 8000

CMD ["sh", "-c", "uvicorn nico.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
