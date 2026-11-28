"""Identity-bound retries for an already reserved automated run.

Construct and persist the binding together with the original reservation in
trusted authorization storage. This candidate does not mount an intake route.
"""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import json
import re
from typing import Protocol
from unicodedata import category, normalize

from .download_binding import Principal
from .github_requester_standing import Standing
from .run_identity import is_canonical_run_id

_REQUEST_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_SUBJECT = re.compile(r"[1-9][0-9]{0,20}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_TERMS = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


@dataclass(frozen=True)
class IntakeBinding:
    run_id: str
    requester: Principal
    repository_id: int
    request_sha256: str


class IntakeBindings(Protocol):
    def read_binding(self, run_id: str) -> IntakeBinding | None:
        """Return the active immutable authorization record, not a UI projection."""
        ...


def _valid(binding: IntakeBinding) -> bool:
    return (
        type(binding) is IntakeBinding
        and is_canonical_run_id(binding.run_id)
        and type(binding.requester) is Principal
        and binding.requester.issuer == "https://github.com"
        and type(binding.requester.subject) is str
        and _SUBJECT.fullmatch(binding.requester.subject) is not None
        and type(binding.repository_id) is int and binding.repository_id > 0
        and type(binding.request_sha256) is str
        and _REQUEST_HASH.fullmatch(binding.request_sha256) is not None
    )


def bind_verified_intake(run_id: str, *, authority: Standing, source_commit: str,
                         full_name: str, permission_attested: bool,
                         terms_revision: str) -> IntakeBinding:
    """Bind a reservation to exact intent after independently verifying authority.

    The caller supplies fresh verified commissioning authority, the resolved
    commit, and the version of the attestation shown; never hydrate those from
    the submitted form. This does not start an assessment or grant delivery.
    """
    if (
        type(authority) is not Standing
        or any(type(value) is not int or value <= 0 for value in (
            authority.actor_id, authority.app_id, authority.installation_id,
            authority.repository_id,
        ))
        or type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None
        or type(terms_revision) is not str or _TERMS.fullmatch(terms_revision) is None
        or permission_attested is not True
        or type(full_name) is not str or len(full_name) > 200
        or any(category(char) in {"Cc", "Cs"} for char in full_name)
    ):
        raise ValueError("invalid self-serve intake")
    name = " ".join(normalize("NFC", full_name).split())
    if not name:
        raise ValueError("invalid self-serve intake")
    encoded = json.dumps(
        ["nico-self-serve-intent-v1", authority.actor_id, authority.app_id,
         authority.installation_id, authority.repository_id, source_commit,
         name, True, terms_revision],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    binding = IntakeBinding(
        run_id, Principal("https://github.com", str(authority.actor_id)),
        authority.repository_id, "sha256:" + sha256(encoded).hexdigest(),
    )
    if not _valid(binding):
        raise ValueError("invalid self-serve intake")
    return binding


def bound_retry(candidate: IntakeBinding, *, store: IntakeBindings) -> bool:
    """A match only authorizes reusing the reservation, not delivery or new work."""
    if not _valid(candidate):
        return False
    original = store.read_binding(candidate.run_id)
    return (
        original is not None and _valid(original)
        and original.run_id == candidate.run_id
        and original.requester == candidate.requester
        and original.repository_id == candidate.repository_id
        and compare_digest(original.request_sha256, candidate.request_sha256)
    )
