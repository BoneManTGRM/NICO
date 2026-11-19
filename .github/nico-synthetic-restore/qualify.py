"""Build-time checks only: no network, SQL, process daemon or credentials."""
import ctypes
import hashlib
import importlib.metadata
import json
from pathlib import Path
import ssl
import subprocess
import sys
import zlib

root = Path("/opt/nico-reader")
runtime = Path("/opt/nico-python")
manifest = json.loads((root / "native-source-manifest.json").read_text())
tree = root / "native-source"
entries = list(tree.rglob("*"))
if (manifest["revision"] != "5eb768b5776f88bae86e972c76267915cc874c85"
    or len(manifest["files"]) != 39 or any(p.is_symlink() for p in entries)
    or set(manifest["files"]) != {str(p.relative_to(tree)) for p in entries if p.is_file()}):
    raise SystemExit("fixture source set")
for relative, expected in manifest["files"].items():
    if hashlib.sha256((tree / relative).read_bytes()).hexdigest() != expected:
        raise SystemExit("fixture source digest")
if sys.version_info[:2] != (3, 13) or sys.prefix != str(runtime):
    raise SystemExit("relocated CPython")
for path in [Path(sys.executable), *runtime.glob("lib/python3.13/lib-dynload/*.so"),
             *runtime.glob("lib/python3.13/site-packages/psycopg_binary/*.so")]:
    link = subprocess.run(["/usr/bin/ldd", str(path)], check=True, capture_output=True,
                          timeout=8)
    if b"not found" in link.stdout + link.stderr:
        raise SystemExit("missing shared library")
import psycopg
if (psycopg.pq.__impl__ != "binary"
    or importlib.metadata.version("psycopg") != "3.3.4"
    or importlib.metadata.version("psycopg-binary") != "3.3.4"):
    raise SystemExit("psycopg provenance")
pg = subprocess.run(["/usr/lib/postgresql/18/bin/postgres", "--version"],
                    check=True, capture_output=True, timeout=8).stdout.split()
if len(pg) < 3 or pg[2] != b"18.6":
    raise SystemExit("expected PostgreSQL 18.6")
import native_import_probe
print("SYNTHETIC_BUILD_IMPORT_CHECK_PASSED gate_eligible=false")
