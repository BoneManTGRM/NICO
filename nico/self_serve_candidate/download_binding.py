"""Offline consumer design. Not an identity provider, issuance policy, or route."""
from dataclasses import dataclass
import re
from typing import Protocol

from .sealed_readback import SealedPdf, exact_pdf_bytes


@dataclass(frozen=True)
class Principal:
    # Both values must come from a validated server-side session, not the form.
    issuer: str
    subject: str


@dataclass(frozen=True)
class Edition:
    run_id: str
    locale: str


@dataclass(frozen=True)
class Grant:
    recipient: Principal
    edition: Edition
    repository_id: str
    source_commit: str
    pdf: SealedPdf


@dataclass(frozen=True)
class DownloadSnapshot:
    # The store must derive these in one fresh, consistent read: an active grant,
    # current provider access, the authoritative run and its retained artifact.
    grant: Grant
    repository_id: str
    source_commit: str
    access_confirmed: bool
    pdf_bytes: bytes


class SnapshotStore(Protocol):
    def read_active(self, principal: Principal, edition: Edition) -> DownloadSnapshot | None:
        """Recheck revocation and current access; never return a cache hit instead."""
        ...


class DownloadUnavailable(Exception):
    """Same result for missing, mismatch, unauthorized, and corrupt records."""


@dataclass(frozen=True)
class Download:
    content: bytes
    headers: dict[str, str]


def private_download(
    principal: Principal | None, edition: Edition, *, store: SnapshotStore
) -> Download:
    if (
        principal is None
        or not principal.issuer
        or not principal.subject
        or edition.locale not in ("en", "es-MX")
        or re.fullmatch(r"comprun_[a-z0-9]{1,64}", edition.run_id) is None
    ):
        raise DownloadUnavailable()
    snapshot = store.read_active(principal, edition)
    if (
        snapshot is None
        or snapshot.access_confirmed is not True
        or snapshot.grant.recipient != principal
        or snapshot.grant.edition != edition
        or not snapshot.repository_id
        or snapshot.grant.repository_id != snapshot.repository_id
        or re.fullmatch(r"[a-f0-9]{40}", snapshot.source_commit) is None
        or snapshot.grant.source_commit != snapshot.source_commit
    ):
        raise DownloadUnavailable()
    try:
        data = exact_pdf_bytes(snapshot.pdf_bytes, binding=snapshot.grant.pdf)
    except ValueError:
        raise DownloadUnavailable() from None
    return Download(data, {
        "Content-Type": "application/pdf",
        "Content-Disposition": f'attachment; filename="nico-{edition.run_id}-{edition.locale}.pdf"',
        "Content-Language": edition.locale,
        "Cache-Control": "private, no-store, max-age=0",
        "X-Content-Type-Options": "nosniff",
    })
