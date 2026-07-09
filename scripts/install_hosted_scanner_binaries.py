from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

INSTALL_DIR = Path(os.getenv("NICO_SCANNER_INSTALL_DIR", "/usr/local/bin"))
STRICT_INSTALL = os.getenv("NICO_SCANNER_INSTALL_STRICT", "false").lower() == "true"
USER_AGENT = "NICO-hosted-scanner-tool-installer"

TOOLS = (
    {
        "name": "osv-scanner",
        "repository": "google/osv-scanner",
        "asset_markers": ("osv-scanner_linux_amd64", "linux_amd64"),
        "binary": "osv-scanner",
    },
    {
        "name": "gitleaks",
        "repository": "gitleaks/gitleaks",
        "asset_markers": ("linux_x64.tar.gz", "linux_amd64.tar.gz", "linux_x64", "linux_amd64"),
        "binary": "gitleaks",
    },
    {
        "name": "trufflehog",
        "repository": "trufflesecurity/trufflehog",
        "asset_markers": ("linux_amd64.tar.gz", "linux_amd64"),
        "binary": "trufflehog",
    },
)


def _request(url: str) -> urllib.request.Request:
    request = urllib.request.Request(url)
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/vnd.github+json")
    return request


def _latest_release(repository: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    with urllib.request.urlopen(_request(url), timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def _select_asset(release: dict[str, Any], markers: tuple[str, ...]) -> dict[str, Any]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise RuntimeError("GitHub release did not include assets")
    for marker in markers:
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "")
            if marker in name:
                return asset
    available = ", ".join(str(asset.get("name")) for asset in assets if isinstance(asset, dict))
    raise RuntimeError(f"No matching release asset found. Available assets: {available}")


def _download(asset: dict[str, Any], destination: Path) -> None:
    url = str(asset.get("browser_download_url") or "")
    if not url:
        raise RuntimeError("Release asset missing browser_download_url")
    with urllib.request.urlopen(_request(url), timeout=120) as response:
        destination.write_bytes(response.read())


def _copy_executable(source: Path, binary: str) -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = INSTALL_DIR / binary
    shutil.copy2(source, target)
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_binary(root: Path, binary: str) -> Path:
    candidates = [path for path in root.rglob("*") if path.is_file() and path.name == binary]
    if not candidates:
        raise RuntimeError(f"Extracted archive did not contain {binary}")
    return candidates[0]


def _install_archive(archive: Path, asset_name: str, binary: str) -> None:
    with tempfile.TemporaryDirectory(prefix="nico-scanner-install-") as temp:
        root = Path(temp)
        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(root)
            _copy_executable(_find_binary(root, binary), binary)
            return
        if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(root)
            _copy_executable(_find_binary(root, binary), binary)
            return
        _copy_executable(archive, binary)


def install_tool(tool: dict[str, Any]) -> None:
    binary = str(tool["binary"])
    release = _latest_release(str(tool["repository"]))
    asset = _select_asset(release, tuple(tool["asset_markers"]))
    asset_name = str(asset.get("name") or binary)
    with tempfile.TemporaryDirectory(prefix="nico-scanner-download-") as temp:
        archive = Path(temp) / asset_name
        _download(asset, archive)
        _install_archive(archive, asset_name, binary)
    installed = shutil.which(binary)
    if not installed:
        raise RuntimeError(f"{binary} was installed but is not available on PATH")
    print(f"installed {binary}: {installed}")


def main() -> None:
    failures: list[str] = []
    installed: list[str] = []
    for tool in TOOLS:
        name = str(tool["name"])
        try:
            install_tool(tool)
            installed.append(name)
        except Exception as exc:  # pragma: no cover - exercised during Docker build
            failures.append(f"{name}: {exc}")
            print(f"warning: could not install {name}: {exc}")
    print("hosted scanner binary installer summary: installed=" + ", ".join(installed or ["none"]))
    if failures:
        print("hosted scanner binary installer warnings: " + "; ".join(failures))
        if STRICT_INSTALL:
            raise SystemExit("Failed to install hosted scanner binaries: " + "; ".join(failures))


if __name__ == "__main__":
    main()
