from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_dependencies_include_self_contained_psycopg_binary() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "psycopg[binary]>=3.3.4,<4" in requirements
    assert '"psycopg[binary]>=3.3.4,<4"' in pyproject
    assert "\npsycopg>=3.3.4,<4\n" not in requirements
    assert '"psycopg>=3.3.4,<4"' not in pyproject


def test_container_build_proves_the_binary_driver_is_importable() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "import psycopg" in dockerfile
    assert "psycopg.pq.__impl__ == 'binary'" in dockerfile
    assert dockerfile.index("pip install --no-cache-dir -r requirements.txt") < dockerfile.index("import psycopg")
