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
    assert "NICO_API_HOST" in runner
    assert "NICO_API_PORT" in runner


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

    assert "nico.api.production_bootstrap:app" in compose
    assert "nico.api.production:app" not in compose
    assert "NEXT_PUBLIC_NICO_API_URL: http://localhost:8000" in compose
    assert "NICO_CORS_ORIGINS: http://localhost:3000" in compose
    assert "NICO_SQLITE_PATH: /data/nico-runtime.sqlite3" in compose
    assert 'NICO_SQLITE_DURABLE_MOUNT_VERIFIED: "true"' in compose
    assert 'NICO_WEB_WORKERS: "1"' in compose
    assert "nico-data:/data" in compose
    assert "NICO_ADMIN_TOKEN" not in compose


def test_docker_context_excludes_local_state_and_env_files() -> None:
    ignore = _read(".dockerignore")

    for item in (".git", ".nico", ".env", "node_modules", "apps/web/.next", "*.sqlite3"):
        assert item in ignore


def test_runtime_image_installs_package_and_owns_persistent_data_path() -> None:
    dockerfile = _read("Dockerfile")

    assert "mkdir -p /data/reports" in dockerfile
    assert "chown -R nico:nico /data" in dockerfile
    assert "python -m pip install --no-cache-dir --no-deps ." in dockerfile
    assert "chown -R nico:nico /app /data" in dockerfile
    assert dockerfile.index("chown -R nico:nico /app /data") < dockerfile.index("USER nico")


def test_ci_executes_installed_entry_points_and_runtime_storage_probe() -> None:
    workflow = _read(".github/workflows/nico-ci.yml")

    assert "pip install --no-deps -e ." in workflow
    assert "Verify package entry points" in workflow
    assert "nico --help" in workflow
    assert 'scripts.get("nico") == "nico.__main__:main"' in workflow
    assert 'scripts.get("nico-api") == "nico.api_runner:main"' in workflow
    assert "test -w /data" in workflow
    assert "command -v nico" in workflow
    assert "command -v nico-api" in workflow
