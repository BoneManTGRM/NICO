"""Inactive GitHub App initiation model. Browser binding comes from trusted session middleware."""
from base64 import urlsafe_b64encode
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
import re
from secrets import token_urlsafe
from typing import Protocol
from urllib.parse import urlsplit

from .pending_intake import PendingIntake

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")
TTL_SECONDS = 300


@dataclass(frozen=True)
class Pending:
    browser_hash: bytes
    redirect_uri: str
    expires_at: float
    verifier: str = field(repr=False)
    intake: PendingIntake | None = field(default=None, repr=False)


class Store(Protocol):
    def insert_unique(self, state_hash: bytes, pending: Pending) -> None: ...
    def consume_matching(self, state_hash: bytes, browser_hash: bytes,
                         redirect_uri: str, now: float) -> Pending | None:
        """Atomically delete/return exactly one matching, unexpired record."""
        ...


def _digest(value: str) -> bytes:
    return sha256(value.encode("ascii")).digest()


def _binding(value: str) -> bytes:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise ValueError("invalid_browser_binding")
    return _digest(value)


def _now(clock):
    stamp = clock()
    if type(stamp) not in {int, float} or not isfinite(stamp) or stamp < 0:
        raise ValueError("invalid_trusted_clock")
    return stamp


class GithubAppFlow:
    def __init__(self, store: Store, *, configured_redirect: str, clock):
        if (not isinstance(configured_redirect, str)
                or re.fullmatch(r"https://[a-z0-9.-]+/[A-Za-z0-9/_-]+", configured_redirect) is None
                or not urlsplit(configured_redirect).hostname
                or "//" in urlsplit(configured_redirect).path):
            raise ValueError("invalid_configured_redirect")
        self._store = store
        self._redirect = configured_redirect
        self._clock = clock

    def begin(self, *, trusted_browser_binding: str,
              intake: PendingIntake | None = None) -> dict[str, str]:
        if intake is not None and type(intake) is not PendingIntake:
            raise ValueError("invalid pending intake")
        state, verifier = token_urlsafe(32), token_urlsafe(32)
        pending = Pending(_binding(trusted_browser_binding), self._redirect,
                          _now(self._clock) + TTL_SECONDS, verifier, intake)
        self._store.insert_unique(_digest(state), pending)
        challenge = urlsafe_b64encode(_digest(verifier)).decode("ascii").rstrip("=")
        return dict(state=state, redirect_uri=self._redirect,
                    code_challenge=challenge, code_challenge_method="S256")

    def consume(self, *, state: str, trusted_browser_binding: str) -> Pending | None:
        if not isinstance(state, str) or TOKEN.fullmatch(state) is None:
            return None
        try:
            browser_hash = _binding(trusted_browser_binding)
        except ValueError:
            return None
        return self._store.consume_matching(_digest(state), browser_hash,
                                            self._redirect, _now(self._clock))
