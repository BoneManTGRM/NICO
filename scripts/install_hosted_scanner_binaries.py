from __future__ import annotations

import hashlib
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
from urllib.parse import quote, urlparse

INSTALL_DIR = Path(os.getenv("NICO_SCANNER_INSTALL_DIR", "/usr/local/bin"))
STRICT_INSTALL = os.getenv("NICO_SCANNER_INSTALL_STRICT", "false").lower() == "true"
USER_AGENT = "NICO-hosted-scanner-tool-installer"
MAX_DOWNLOAD_BYTES = int(os.getenv("NICO_SCANNER_MAX_DOWNLOAD_BYTES", str(250 * 1024 * 1024)))
ALLOWED_DOWNLOAD_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
SAFE_RELEASE_TAG = re.compile(r"^v?[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAFE_ASSET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
SHA256_VALUE = re.compile(r"^[0-9a-f]{64}$")
TOOLS = (
    {
        "name": "osv-scanner",
        "repository": "google/osv-scanner",
        "version_env": "NICO_OSV_SCANNER_VERSION",
        "default_tag": "v2.3.8",
        "asset_name_template": "osv-scanner_linux_amd64",
        "asset_sha256": "bc98e15319ed0d515e3f9235287ba53cdc5535d576d24fd573978ecfe9ab92dc",
        "checksum_name_template": "osv-scanner_SHA256SUMS",
        "binary": "osv-scanner",
    },
    {
        "name": "gitleaks",
        "repository": "gitleaks/gitleaks",
        "version_env": "NICO_GITLEAKS_VERSION",
        "default_tag": "v8.30.1",
        "asset_name_template": "gitleaks_{version}_linux_x64.tar.gz",
        "asset_sha256": "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
        "checksum_name_template": "gitleaks_{version}_checksums.txt",
        "binary": "gitleaks",
    },
    {
        "name": "trufflehog",
        "repository": "trufflesecurity/trufflehog",
        "version_env": "NICO_TRUFFLEHOG_VERSION",
        "default_tag": "v3.95.0",
        "asset_name_template": "trufflehog_{version}_linux_amd64.tar.gz",
        "checksum_name_template": "trufflehog_{version}_checksums.txt",
        "binary": "trufflehog",
    },
)


def _validated_https_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_DOWNLOAD_HOSTS or parsed.username or parsed.password:
        raise RuntimeError("Scanner downloads require an allowlisted GitHub HTTPS URL.")
    return parsed.geturl()


def _request(url: str, *, accept: str = "application/octet-stream") -> urllib.request.Request:
    request = urllib.request.Request(_validated_https_url(url))
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", accept)
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


def _version(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def _asset_name(tool: dict[str, Any], tag: str, field: str) -> str:
    template = str(tool.get(field) or "").strip()
    if not template:
        raise RuntimeError(f"Pinned scanner metadata is missing {field} for {tool.get('name')}.")
    name = template.format(tag=tag, version=_version(tag))
    if not SAFE_ASSET_NAME.fullmatch(name):
        raise RuntimeError(f"Invalid pinned scanner asset name for {tool.get('name')}: {name!r}")
    return name


def _asset_url(repository: str, tag: str, asset_name: str) -> str:
    if not repository or repository.count("/") != 1:
        raise RuntimeError("Invalid GitHub repository identifier for scanner release download.")
    if not SAFE_RELEASE_TAG.fullmatch(tag) or not SAFE_ASSET_NAME.fullmatch(asset_name):
        raise RuntimeError("Invalid pinned scanner release identity.")
    owner, name = repository.split("/", 1)
    return _validated_https_url(
        "https://github.com/"
        f"{quote(owner, safe='')}/{quote(name, safe='')}/releases/download/"
        f"{quote(tag, safe='._-')}/{quote(asset_name, safe='._-')}"
    )


def _download_bytes(url: str, *, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    with urllib.request.urlopen(_request(url), timeout=120) as response:  # nosec B310
        _validated_https_url(str(response.geturl() or url))
        return _read_bounded(response, limit)


def _download(url: str, destination: Path) -> None:
    destination.write_bytes(_download_bytes(url))


def _checksum_from_manifest(manifest: bytes, asset_name: str) -> str:
    try:
        text = manifest.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Scanner checksum manifest was not valid UTF-8.") from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.fullmatch(r"([0-9A-Fa-f]{64})\s+\*?(.+)", line)
        if not match:
            continue
        candidate = PurePosixPath(match.group(2).strip().replace("\\", "/")).name
        if candidate == asset_name:
            return match.group(1).lower()
    raise RuntimeError(f"Scanner checksum manifest did not contain {asset_name}.")


def _expected_sha256(tool: dict[str, Any], tag: str, asset_name: str) -> str:
    pinned = str(tool.get("asset_sha256") or "").strip().lower()
    if pinned:
        if not SHA256_VALUE.fullmatch(pinned):
            raise RuntimeError(f"Invalid pinned SHA-256 for {tool.get('name')}.")
        return pinned
    checksum_name = _asset_name(tool, tag, "checksum_name_template")
    checksum_url = _asset_url(str(tool.get("repository") or ""), tag, checksum_name)
    manifest = _download_bytes(checksum_url, limit=1024 * 1024)
    return _checksum_from_manifest(manifest, asset_name)


def _verify_sha256(path: Path, expected: str) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise RuntimeError(
            f"Scanner release asset SHA-256 mismatch: expected {expected}, observed {digest}."
        )
    return digest


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
    asset_name = _asset_name(tool, tag, "asset_name_template")
    asset_url = _asset_url(str(tool["repository"]), tag, asset_name)
    expected_sha256 = _expected_sha256(tool, tag, asset_name)
    with tempfile.TemporaryDirectory(prefix="nico-scanner-download-") as temp:
        archive = Path(temp) / asset_name
        _download(asset_url, archive)
        observed_sha256 = _verify_sha256(archive, expected_sha256)
        _install_archive(archive, asset_name, binary)
    installed = INSTALL_DIR / binary
    if not installed.is_file() or not os.access(installed, os.X_OK):
        raise RuntimeError(f"{binary} was installed but is not executable at {installed}")
    print(f"installed {binary}@{tag} sha256:{observed_sha256}: {installed}")
    return tag


def main() -> None:
    failures: list[str] = []
    installed: list[str] = []
    for tool in TOOLS:
        name = str(tool["name"])
        try:
            tag = install_tool(tool)
            installed.append(f"{name}@{tag}")
        except Exception as exc:  # pragma: no cover
            failures.append(f"{name}: {exc}")
            print(f"warning: could not install {name}: {exc}")
    print("hosted scanner binary installer summary: installed=" + ", ".join(installed or ["none"]))
    if failures:
        print("hosted scanner binary installer warnings: " + "; ".join(failures))
        if STRICT_INSTALL:
            raise SystemExit("Failed to install hosted scanner binaries: " + "; ".join(failures))


if __name__ == "__main__":
    main()
