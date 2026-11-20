"""Validate the authenticated inner tar receipt and an allowlisted OCI export.
Does not extract or run anything.
"""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import posixpath
import re
import tarfile

MAX_ARCHIVE = 340 * 1024 * 1024
MAX_LOGICAL = 340 * 1024 * 1024
MAX_MEMBERS = 18000
ROOTS = {"nico-python", "nico-reader"}

def clean(relative):
    parts = relative.split("/")
    if any(not p or p in {".",".."} for p in parts) or parts[0] not in ROOTS:
        raise ValueError("archive member outside prepared roots")
    if any(not re.fullmatch(r"[a-zA-Z0-9_.+-]+", p) for p in parts):
        raise ValueError("invalid archive path")
    return PurePosixPath(relative)

def verify(archive: Path, digest: str):
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("invalid archive extent")
    if re.fullmatch("[a-f0-9]{64}", digest) is None:
        raise ValueError("trusted receipt digest required")
    with archive.open("rb") as af:
        if hashlib.file_digest(af, "sha256").hexdigest() != digest:
            raise ValueError("tar receipt mismatch")
        af.seek(0)
        names, symlinks = set(), {}
        logical = 0
        with tarfile.open(fileobj=af, mode="r:*") as tar:
            for member in tar:
                p = clean(member.name)
                if p in names or len(names) >= MAX_MEMBERS or member.mode & 0o7000:
                    raise ValueError("duplicate, excessive or privileged archive entry")
                if p.name in {".env", ".git", ".aws", ".ssh", "credentials"}:
                    raise ValueError("ineligible content path")
                names.add(p)
                logical += member.size
                if logical > MAX_LOGICAL:
                    raise ValueError("archive logical size")
                if member.issym():
                    # Docker/CPython symlinks must be internal relative paths.
                    if member.linkname.startswith("/") or not member.linkname:
                        raise ValueError("absolute or empty symlink")
                    target = clean(posixpath.normpath(str(p.parent / member.linkname)))
                    if target.parts[0] != p.parts[0]:
                        raise ValueError("cross-root symlink")
                    symlinks[p] = target
                elif not (member.isdir() or member.isreg()):
                    raise ValueError("unsupported archive member")
        for p, target in symlinks.items():
            if target not in names or any(parent in symlinks for parent in p.parents):
                raise ValueError("dangling symlink or symlink ancestor")
            chain = {p}
            while target in symlinks:
                if target in chain:raise ValueError("symlink cycle")
                chain.add(target)
                target = symlinks[target]
        if any(any(parent in symlinks for parent in p.parents) for p in names):
            raise ValueError("archive write through symlink")
        if {p.parts[0] for p in names} != ROOTS:
            raise ValueError("required roots absent")
        return len(names), logical

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("archive",type=Path)
    parser.add_argument("receipt_sha256")
    result=verify(**{"archive":(a:=parser.parse_args()).archive,"digest":a.receipt_sha256})
    print(f"FAKE_RUNTIME_TAR_VERIFIED entries={result[0]} logical_bytes={result[1]}")
