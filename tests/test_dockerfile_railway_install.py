from pathlib import Path


def test_dockerfile_uses_deterministic_npm_install_for_railway_web_dependencies():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "cd apps/web && npm ci --ignore-scripts --no-audit --no-fund" in dockerfile
    assert "npm install --legacy-peer-deps" not in dockerfile
