FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true
ENV NICO_ALLOW_PROJECT_COMMANDS=true
ENV NICO_ENABLE_FULL_HISTORY_SECRET_SCAN=true
ARG NICO_SCANNER_INSTALL_STRICT=false
ARG NICO_SEMGREP_VERSION=1.170.0
ENV NICO_SCANNER_INSTALL_STRICT=${NICO_SCANNER_INSTALL_STRICT}
ENV NICO_REQUIRE_DURABLE_DELIVERY_STORAGE=true
ENV NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE=true
ENV NICO_ENABLE_SQLITE_DURABLE_STORAGE=true
ENV NICO_SQLITE_PATH=/data/nico-runtime.sqlite3
ENV NICO_TRUST_PROXY_HEADERS=true
ENV NICO_TOOL_TIMEOUT_SECONDS=120
ENV NICO_TOTAL_SCAN_TIMEOUT_SECONDS=1500
ENV NICO_OSV_TIMEOUT_SECONDS=240
ENV NICO_HISTORY_TOOL_TIMEOUT_SECONDS=420
ENV NICO_WEB_WORKERS=1
ENV NICO_SEMGREP_HOME=/opt/nico-tools/semgrep

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
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin nico \
    && mkdir -p /data/reports /opt/nico-tools \
    && chown -R nico:nico /data

RUN npm install -g eslint typescript --no-audit --no-fund

COPY requirements.txt ./
COPY scripts/install_hosted_scanner_binaries.py ./scripts/install_hosted_scanner_binaries.py
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir coverage \
    && python -m venv "$NICO_SEMGREP_HOME" \
    && "$NICO_SEMGREP_HOME/bin/python" -m pip install --upgrade pip \
    && "$NICO_SEMGREP_HOME/bin/pip" install --no-cache-dir "semgrep==${NICO_SEMGREP_VERSION}" \
    && ln -s "$NICO_SEMGREP_HOME/bin/semgrep" /usr/local/bin/semgrep \
    && command -v semgrep \
    && python scripts/install_hosted_scanner_binaries.py

COPY . .
RUN python -m pip install --no-cache-dir --no-deps . \
    && if [ -f apps/web/package-lock.json ]; then cd apps/web && npm ci --ignore-scripts --no-audit --no-fund; fi \
    && chown -R nico:nico /app /data /opt/nico-tools

USER nico

EXPOSE 8000

CMD ["sh", "-c", "workers=${NICO_WEB_WORKERS:-1}; case \"$workers\" in ''|*[!0-9]*) echo 'NICO_WEB_WORKERS must be a positive integer' >&2; exit 1;; esac; if [ \"$workers\" -lt 1 ]; then echo 'NICO_WEB_WORKERS must be at least 1' >&2; exit 1; fi; exec uvicorn nico.api.comprehensive_production_bootstrap:app --host 0.0.0.0 --port ${PORT:-8000} --workers $workers"]
