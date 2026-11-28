"""Identity-bound retries for an already reserved automated run.

Construct and persist the binding together with the original reservation in
trusted authorization storage. This candidate does not mount an intake route.
"""
from dataclasses import dataclass
from hmac import compare_digest
import re
from typing import Protocol

from .download_binding import Principal
from .run_identity import is_canonical_run_id

_REQUEST_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_SUBJECT = re.compile(r"[1-9][0-9]{0,20}")


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
