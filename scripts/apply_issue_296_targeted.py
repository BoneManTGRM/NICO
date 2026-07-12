from __future__ import annotations

from pathlib import Path

# One-time deterministic repair script. Safe to rerun after the target changes land.


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected repair target was not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def repair_archive_extraction() -> None:
    path = Path("nico/no_server_assessment.py")
    replace_once(path, "import shutil\nimport socket\n", "import shutil\nimport socket\nimport stat\n")
    replace_once(
        path,
        '''def safe_extract_zip(archive: Path, destination: Path) -> None:\n    with zipfile.ZipFile(archive) as zf:\n        for member in zf.infolist():\n            target = destination / member.filename\n            if not is_within(destination, target):\n                raise RuntimeError(f"Unsafe archive path blocked: {member.filename}")\n        zf.extractall(destination)\n\n\ndef safe_extract_tar(archive: Path, destination: Path) -> None:\n    with tarfile.open(archive) as tf:\n        for member in tf.getmembers():\n            target = destination / member.name\n            if not is_within(destination, target):\n                raise RuntimeError(f"Unsafe archive path blocked: {member.name}")\n        tf.extractall(destination)\n''',
        '''def safe_extract_zip(archive: Path, destination: Path) -> None:\n    destination.mkdir(parents=True, exist_ok=True)\n    with zipfile.ZipFile(archive) as zf:\n        for member in zf.infolist():\n            target = destination / member.filename\n            if not is_within(destination, target):\n                raise RuntimeError(f"Unsafe archive path blocked: {member.filename}")\n            file_type = (member.external_attr >> 16) & 0o170000\n            if file_type == stat.S_IFLNK:\n                raise RuntimeError(f"Archive symlink blocked: {member.filename}")\n            if member.is_dir():\n                target.mkdir(parents=True, exist_ok=True)\n                continue\n            target.parent.mkdir(parents=True, exist_ok=True)\n            with zf.open(member, "r") as source, target.open("wb") as output:\n                shutil.copyfileobj(source, output, length=1024 * 1024)\n\n\ndef safe_extract_tar(archive: Path, destination: Path) -> None:\n    destination.mkdir(parents=True, exist_ok=True)\n    with tarfile.open(archive) as tf:\n        for member in tf.getmembers():\n            target = destination / member.name\n            if not is_within(destination, target):\n                raise RuntimeError(f"Unsafe archive path blocked: {member.name}")\n            if member.isdir():\n                target.mkdir(parents=True, exist_ok=True)\n                continue\n            if not member.isfile():\n                raise RuntimeError(f"Non-regular archive member blocked: {member.name}")\n            source = tf.extractfile(member)\n            if source is None:\n                raise RuntimeError(f"Archive member could not be read: {member.name}")\n            target.parent.mkdir(parents=True, exist_ok=True)\n            with source, target.open("wb") as output:\n                shutil.copyfileobj(source, output, length=1024 * 1024)\n''',
    )


def repair_static_sql_dispatch() -> None:
    path = Path("nico/cli.py")
    replace_once(
        path,
        '''    def rows(self, table: str) -> list[dict[str, Any]]:\n        if table not in {"scans", "findings", "drift_events", "repairs", "memory", "reports", "audit_log", "verification"}:\n            raise ValueError(f"unsupported table: {table}")\n        with self.db() as db:\n            rows = db.execute(f"SELECT * FROM {table} ORDER BY rowid DESC").fetchall()\n        return [dict(row) for row in rows]\n''',
        '''    def rows(self, table: str) -> list[dict[str, Any]]:\n        queries = {\n            "scans": "SELECT * FROM scans ORDER BY rowid DESC",\n            "findings": "SELECT * FROM findings ORDER BY rowid DESC",\n            "drift_events": "SELECT * FROM drift_events ORDER BY rowid DESC",\n            "repairs": "SELECT * FROM repairs ORDER BY rowid DESC",\n            "memory": "SELECT * FROM memory ORDER BY rowid DESC",\n            "reports": "SELECT * FROM reports ORDER BY rowid DESC",\n            "audit_log": "SELECT * FROM audit_log ORDER BY rowid DESC",\n            "verification": "SELECT * FROM verification ORDER BY rowid DESC",\n        }\n        query = queries.get(table)\n        if query is None:\n            raise ValueError(f"unsupported table: {table}")\n        with self.db() as db:\n            rows = db.execute(query).fetchall()\n        return [dict(row) for row in rows]\n''',
    )


def main() -> None:
    repair_archive_extraction()
    repair_static_sql_dispatch()


if __name__ == "__main__":
    main()
