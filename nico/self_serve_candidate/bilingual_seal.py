"""Dormant exact-edition persistence seam; neither runs migrations nor authorizes access."""
from dataclasses import dataclass
from hmac import compare_digest

from .run_identity import is_canonical_run_id
from .sealed_readback import SealedPdf, exact_pdf_bytes

_TABLE = "nico_self_serve_retained_editions"
_MAX_BYTES = 16 * 1024 * 1024
_LOCALES = frozenset(("en", "es-MX"))
_SCHEMA = f"""CREATE TABLE {_TABLE} (
    run_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK (revision > 0),
    locale TEXT NOT NULL CHECK (locale IN ('en', 'es-MX')),
    digest TEXT NOT NULL, size INTEGER NOT NULL, content {{binary_type}} NOT NULL,
    PRIMARY KEY (run_id, revision, locale)
)"""
SQLITE_SCHEMA = _SCHEMA.format(binary_type="BLOB")
POSTGRES_SCHEMA = _SCHEMA.format(binary_type="BYTEA")


@dataclass(frozen=True)
class RetainedEdition:
    locale: str
    binding: SealedPdf
    content: bytes


def _marker(dialect):
    if dialect == "sqlite":
        return "?"
    if dialect == "postgres":
        return "%s"
    raise ValueError("unknown storage dialect")


def _valid_revision(run_id, revision):
    return is_canonical_run_id(run_id) and type(revision) is int and 0 < revision < 2**31


def stage_bilingual(cursor, *, dialect, run_id, revision, editions):
    """Stage a complete immutable pair. The caller owns the run CAS and transaction."""
    p = _marker(dialect)
    if (
        not _valid_revision(run_id, revision)
        or type(editions) is not tuple or len(editions) != 2
        or any(type(item) is not RetainedEdition or type(item.locale) is not str
               or type(item.binding) is not SealedPdf for item in editions)
        or {item.locale for item in editions} != _LOCALES
        or editions[0].binding == editions[1].binding
    ):
        raise ValueError("exact bilingual edition pair required")
    rows = []
    for item in editions:
        if type(item.content) is not bytes or len(item.content) > _MAX_BYTES:
            raise ValueError("retained PDF invalid or exceeds supported size")
        raw = exact_pdf_bytes(item.content, binding=item.binding)
        rows.extend((run_id, revision, item.locale, item.binding.sha256_hex, item.binding.size, raw))
    record = "(" + ", ".join([p] * 6) + ")"
    cursor.execute(f"INSERT INTO {_TABLE} (run_id, revision, locale, digest, size, content) "
                   f"VALUES {record}, {record}", tuple(rows))


def read_edition(cursor, *, dialect, run_id, revision, locale, expected):
    """Read only the granted revision and independently bound original bytes."""
    p = _marker(dialect)
    if (not _valid_revision(run_id, revision) or type(locale) is not str or locale not in _LOCALES
            or type(expected) is not SealedPdf or type(expected.size) is not int
            or not 5 <= expected.size <= _MAX_BYTES):
        return None
    cursor.execute(f"SELECT digest, size, content FROM {_TABLE} "
                         f"WHERE run_id = {p} AND revision = {p} AND locale = {p}",
                         (run_id, revision, locale))
    # DB-API cursor.execute may return None; consume from the original cursor.
    row = cursor.fetchone()
    if (row is None or type(row[0]) is not str or type(expected.sha256_hex) is not str
            or not row[0].isascii() or not expected.sha256_hex.isascii()
            or not compare_digest(row[0], expected.sha256_hex)
            or row[1] != expected.size):
        return None
    raw = row[2]
    if type(raw) is memoryview:
        raw = raw.tobytes()
    try:
        return exact_pdf_bytes(raw, binding=expected)
    except ValueError:
        return None
