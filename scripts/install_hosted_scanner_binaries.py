from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from urllib.parse import urlparse

INSTALL_DIR = Path(os.getenv("NICO_SCANNER_INSTALL_DIR", "/usr/local/bin"))
STRICT_INSTALL = os.getenv("NICO_SCANNER_INSTALL_STRICT", "false").lower() == "true"
USER_AGENT = "NICO-hosted-scanner-tool-installer"
MAX_DOWNLOAD_BYTES = int(os.getenv("NICO_SCANNER_MAX_DOWNLOAD_BYTES", str(250 * 1024 * 1024)))
ALLOWED_DOWNLOAD_HOSTS = {
    "api.github.com",
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
SAFE_RELEASE_TAG = re.compile(r"^v?[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
TOOLS = (
    {
        "name": "osv-scanner",
        "repository": "google/osv-scanner",
        "version_env": "NICO_OSV_SCANNER_VERSION",
        "default_tag": "v2.4.0",
        "asset_markers": ("osv-scanner_linux_amd64", "linux_amd64"),
        "binary": "osv-scanner",
    },
    {
        "name": "gitleaks",
        "repository": "gitleaks/gitleaks",
        "version_env": "NICO_GITLEAKS_VERSION",
        "default_tag": "v8.30.1",
        "asset_markers": ("linux_x64.tar.gz", "linux_amd64.tar.gz", "linux_x64", "linux_amd64"),
        "binary": "gitleaks",
    },
    {
        "name": "trufflehog",
        "repository": "trufflesecurity/trufflehog",
        "version_env": "NICO_TRUFFLEHOG_VERSION",
        "default_tag": "v3.95.9",
        "asset_markers": ("linux_amd64.tar.gz", "linux_amd64"),
        "binary": "trufflehog",
    },
)


def _validated_https_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_DOWNLOAD_HOSTS or parsed.username or parsed.password:
        raise RuntimeError("Scanner downloads require an allowlisted GitHub HTTPS URL.")
    return parsed.geturl()


def _request(url: str) -> urllib.request.Request:
    request = urllib.request.Request(_validated_https_url(url))
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/vnd.github+json")
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return request


def _read_bounded(response: BinaryIO, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise RuntimeError(f"Scanner release asset exceeds maximum download size of {limit} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)


def _release_tag(tool: dict[str, Any]) -> str:
    environment_name = str(tool.get("version_env") or "").strip()
    configured = os.getenv(environment_name, "").strip() if environment_name else ""
    tag = configured or str(tool.get("default_tag") or "").strip()
    if not SAFE_RELEASE_TAG.fullmatch(tag):
        raise RuntimeError(f"Invalid pinned release tag for {tool.get('name')}: {tag!r}")
    return tag


def _release(repository: str, tag: str) -> dict[str, Any]:
    if not repository or repository.count("/") != 1:
        raise RuntimeError("Invalid GitHub repository identifier for scanner release lookup.")
    if not SAFE_RELEASE_TAG.fullmatch(tag):
        raise RuntimeError("Invalid scanner release tag.")
    url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
    # URL validation and host allowlisting happen inside _request before this network call.
    with urllib.request.urlopen(_request(url), timeout=45) as response:  # nosec B310
        release = json.loads(_read_bounded(response, 5 * 1024 * 1024).decode("utf-8"))
    actual_tag = str(release.get("tag_name") or "") if isinstance(release, dict) else ""
    if actual_tag != tag:
        raise RuntimeError(f"Scanner release tag mismatch: requested {tag}, received {actual_tag or 'missing'}")
    return release


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
    url = _validated_https_url(str(asset.get("browser_download_url") or ""))
    if not url:
        raise RuntimeError("Release asset missing browser_download_url")
    # URL validation and host allowlisting happen before this network call.
    with urllib.request.urlopen(_request(url), timeout=120) as response:  # nosec B310
        destination.write_bytes(_read_bounded(response))


def _copy_executable(source: Path, binary: str) -> None:
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    target = INSTALL_DIR / binary
    shutil.copy2(source, target)
    mode = target.stat().st_mode
    target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _find_binary(root: Path, binary: str) -> Path:
    candidates = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink() and path.name == binary]
    if not candidates:
        raise RuntimeError(f"Extracted archive did not contain {binary}")
    return candidates[0]


def _safe_member_path(root: Path, name: str) -> Path:
    normalized = PurePosixPath(str(name or "").replace("\\", "/"))
    if normalized.is_absolute() or not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        raise RuntimeError(f"Unsafe archive path blocked: {name}")
    target = root.joinpath(*normalized.parts)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Unsafe archive path blocked: {name}") from exc
    return target


def _safe_extract_zip(archive: Path, root: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = _safe_member_path(root, member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == stat.S_IFLNK:
                raise RuntimeError(f"Archive symlink blocked: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)


def _safe_extract_tar(archive: Path, root: Path) -> None:
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = _safe_member_path(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"Non-regular archive member blocked: {member.name}")
            source = tf.extractfile(member)
            if source is None:
                raise RuntimeError(f"Archive member could not be read: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)


def _install_archive(archive: Path, asset_name: str, binary: str) -> None:
    with tempfile.TemporaryDirectory(prefix="nico-scanner-install-") as temp:
        root = Path(temp)
        if asset_name.endswith(".zip"):
            _safe_extract_zip(archive, root)
            _copy_executable(_find_binary(root, binary), binary)
            return
        if asset_name.endswith(".tar.gz") or asset_name.endswith(".tgz"):
            _safe_extract_tar(archive, root)
            _copy_executable(_find_binary(root, binary), binary)
            return
        _copy_executable(archive, binary)


def install_tool(tool: dict[str, Any]) -> str:
    binary = str(tool["binary"])
    tag = _release_tag(tool)
    release = _release(str(tool["repository"]), tag)
    asset = _select_asset(release, tuple(tool["asset_markers"]))
    asset_name = str(asset.get("name") or binary)
    with tempfile.TemporaryDirectory(prefix="nico-scanner-download-") as temp:
        archive = Path(temp) / asset_name
        _download(asset, archive)
        _install_archive(archive, asset_name, binary)
    installed = INSTALL_DIR / binary
    if not installed.is_file() or not os.access(installed, os.X_OK):
        raise RuntimeError(f"{binary} was installed but is not executable at {installed}")
    print(f"installed {binary}@{tag}: {installed}")
    return tag


def main() -> None:
    failures: list[str] = []
    installed: list[str] = []
    for tool in TOOLS:
        name = str(tool["name"])
        try:
            tag = install_tool(tool)
            installed.append(f"{name}@{tag}")
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
