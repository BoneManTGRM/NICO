"""Deterministic baseline CMake option policy for configure-first C/C++ execution.

The policy is selected by trusted release code, then derived from the exact
root CMakeLists.txt bytes after source materialization and before CMake runs.
It never branches on repository identity and never accepts caller-supplied
option names or values.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

POLICY = "conservative-cmake-v1"
MAX_CMAKE_BYTES = 2 * 1024 * 1024

_ON = frozenset({"BUILD_TESTS", "ENABLE_WALLET", "ENABLE_IPC"})
_OFF = frozenset({
    "BUILD_GUI", "BUILD_GUI_TESTS", "BUILD_BENCH", "BUILD_FUZZ_BINARY",
    "BUILD_FOR_FUZZING", "WITH_ZMQ",
})


def _declared_options(text: str) -> set[str]:
    text = re.sub(r"#\[\[.*?\]\]", "", text, flags=re.DOTALL)
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return set(re.findall(
        r"(?is)(?:^|\n)\s*(?:option|cmake_dependent_option)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\b",
        text,
    ))


def validate_project_options(value: dict[str, str]) -> dict[str, str]:
    if (not isinstance(value, dict) or len(value) > len(_ON | _OFF)
            or any(name not in _ON | _OFF for name in value)
            or any(value[name] != ("ON" if name in _ON else "OFF") for name in value)):
        raise ValueError("worker_cmake_policy_options_invalid")
    return dict(sorted(value.items()))


def derive_project_options(source: Path, targets: dict[str, str], policy: str) -> dict[str, str]:
    if policy != POLICY or not isinstance(targets, dict) or "CMakeLists.txt" not in targets:
        raise ValueError("worker_cmake_policy_invalid")
    expected = targets["CMakeLists.txt"]
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError("worker_cmake_policy_invalid")
    source = Path(source)
    if source.is_symlink() or not source.is_dir() or source.absolute() != source.resolve(strict=True):
        raise ValueError("worker_cmake_policy_source_invalid")
    root = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            fd = os.open("CMakeLists.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        except OSError as exc:
            raise ValueError("worker_cmake_policy_source_invalid") from exc
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(MAX_CMAKE_BYTES + 1)
    finally:
        os.close(root)
    if not raw or len(raw) > MAX_CMAKE_BYTES or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("worker_cmake_policy_source_invalid")
    try:
        declared = _declared_options(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("worker_cmake_policy_source_invalid") from exc
    result = {name: "ON" for name in sorted(declared & _ON)}
    result.update({name: "OFF" for name in sorted(declared & _OFF)})
    return validate_project_options(result)
