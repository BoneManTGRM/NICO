from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_run_local_uses_packaged_complete_api_runner() -> None:
    launcher = _read("run_local.py")
    runner = _read("nico/api_runner.py")

    assert "from nico.api_runner import main" in launcher
    assert "from nico.api.main import start" not in launcher
    assert 'uvicorn.run("nico.api.production:app"' in runner
    assert 'NICO_API_HOST' in runner
    assert 'NICO_API_PORT' in runner


def test_python_module_and_console_script_share_one_dispatcher() -> None:
    module = _read("nico/__main__.py")
    project = _read("pyproject.toml")

    assert "def main() -> None:" in module
    assert 'sys.argv[1] == "assess"' in module
    assert 'nico = "nico.__main__:main"' in project
    assert 'nico-api = "nico.api_runner:main"' in project


def test_environment_example_uses_the_real_cors_variable() -> None:
    env = _read(".env.example")

    assert "NICO_CORS_ORIGINS=http://localhost:3000" in env
    assert "NICO_ALLOWED_ORIGINS" not in env
    assert "NICO_ADMIN_TOKEN=generate-a-long-random-secret" in env


def test_compose_starts_complete_api_and_frontend_without_embedding_secrets() -> None:
    compose = _read("docker-compose.yml")

    assert "nico.api.production:app" in compose
    assert "NEXT_PUBLIC_NICO_API_URL: http://localhost:8000" in compose
    assert "NICO_CORS_ORIGINS: http://localhost:3000" in compose
    assert "nico-data:/data" in compose
    assert "NICO_ADMIN_TOKEN" not in compose


def test_docker_context_excludes_local_state_and_env_files() -> None:
    ignore = _read(".dockerignore")

    for item in (".git", ".nico", ".env", "node_modules", "apps/web/.next", "*.sqlite3"):
        assert item in ignore
