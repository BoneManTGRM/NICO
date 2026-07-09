from pathlib import Path


def test_dockerfile_uses_npm_install_for_railway_web_dependencies():
    dockerfile = Path("Dockerfile").read_text()

    assert "cd apps/web && npm install --legacy-peer-deps --ignore-scripts" in dockerfile
    assert "cd apps/web && npm ci" not in dockerfile
