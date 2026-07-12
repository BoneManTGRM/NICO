from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected repair target was not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def repair_no_server_archives() -> None:
    path = Path("nico/no_server_assessment.py")
    replace_once(path, "import ssl\nimport tarfile", "import ssl\nimport stat\nimport tarfile")
    replace_once(path, "from pathlib import Path\n", "from pathlib import Path, PurePosixPath\n")
    replace_once(
        path,
        '''def safe_extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = destination / member.filename
            if not is_within(destination, target):
                raise RuntimeError(f"Unsafe archive path blocked: {member.filename}")
        zf.extractall(destination)


def safe_extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            target = destination / member.name
            if not is_within(destination, target):
                raise RuntimeError(f"Unsafe archive path blocked: {member.name}")
        tf.extractall(destination)
''',
        '''def _safe_archive_target(destination: Path, member_name: str) -> Path:
    normalized = PurePosixPath(str(member_name or "").replace("\\\\", "/"))
    if normalized.is_absolute() or not normalized.parts or any(part in {"", ".", ".."} for part in normalized.parts):
        raise RuntimeError(f"Unsafe archive path blocked: {member_name}")
    target = destination.joinpath(*normalized.parts)
    if not is_within(destination, target):
        raise RuntimeError(f"Unsafe archive path blocked: {member_name}")
    return target


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = _safe_archive_target(destination, member.filename)
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == stat.S_IFLNK:
                raise RuntimeError(f"Archive symlink blocked: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            target = _safe_archive_target(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"Non-regular archive member blocked: {member.name}")
            source = tf.extractfile(member)
            if source is None:
                raise RuntimeError(f"Archive member could not be read: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
''',
    )


def repair_cli_query_selection() -> None:
    path = Path("nico/cli.py")
    replace_once(
        path,
        '''    def rows(self, table: str) -> list[dict[str, Any]]:
        if table not in {"scans", "findings", "drift_events", "repairs", "memory", "reports", "audit_log", "verification"}:
            raise ValueError(f"unsupported table: {table}")
        with self.db() as db:
            rows = db.execute(f"SELECT * FROM {table} ORDER BY rowid DESC").fetchall()
        return [dict(row) for row in rows]
''',
        '''    def rows(self, table: str) -> list[dict[str, Any]]:
        queries = {
            "scans": "SELECT * FROM scans ORDER BY rowid DESC",
            "findings": "SELECT * FROM findings ORDER BY rowid DESC",
            "drift_events": "SELECT * FROM drift_events ORDER BY rowid DESC",
            "repairs": "SELECT * FROM repairs ORDER BY rowid DESC",
            "memory": "SELECT * FROM memory ORDER BY rowid DESC",
            "reports": "SELECT * FROM reports ORDER BY rowid DESC",
            "audit_log": "SELECT * FROM audit_log ORDER BY rowid DESC",
            "verification": "SELECT * FROM verification ORDER BY rowid DESC",
        }
        query = queries.get(table)
        if query is None:
            raise ValueError(f"unsupported table: {table}")
        with self.db() as db:
            rows = db.execute(query).fetchall()
        return [dict(row) for row in rows]
''',
    )


def main() -> None:
    repair_no_server_archives()
    repair_cli_query_selection()
    Path("scripts/apply_issue_296_static_repairs.py").unlink(missing_ok=True)
    Path(".github/workflows/apply-issue-296-static-repairs.yml").unlink(missing_ok=True)


if __name__ == "__main__":
    main()
