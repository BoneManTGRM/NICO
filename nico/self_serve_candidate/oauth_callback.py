"""Dormant HTTP boundary for requester OAuth; no live routes or provider exchange."""
from dataclasses import dataclass
import re
from secrets import token_urlsafe
from typing import Callable
from urllib.parse import urlencode

from .oauth_state import GithubAppFlow, Pending, TOKEN, TTL_SECONDS
from .provider_download import VerifiedSession

_COOKIE = "__Host-nico_requester_oauth"
_COOKIE_ATTRIBUTES = "Path=/; Secure; HttpOnly; SameSite=Lax"
_CLIENT_ID = re.compile(r"[A-Za-z0-9_]{5,128}")
_CODE = re.compile(r"[A-Za-z0-9._~-]{1,256}")


@dataclass(frozen=True)
class AuthorizationStart:
    location: str
    cookie: str


def begin_authorization(flow: GithubAppFlow, *, client_id: str) -> AuthorizationStart:
    if type(client_id) is not str or _CLIENT_ID.fullmatch(client_id) is None:
        raise ValueError("invalid GitHub App client ID")
    # Mint at the trusted app origin, never take binding from a form or query.
    binding = token_urlsafe(32)
    params = flow.begin(trusted_browser_binding=binding)
    params["client_id"] = client_id
    return AuthorizationStart(
        "https://github.com/login/oauth/authorize?" + urlencode(params),
        f"{_COOKIE}={binding}; Max-Age={TTL_SECONDS}; {_COOKIE_ATTRIBUTES}",
    )


def complete_authorization(
    flow: GithubAppFlow, *, codes: list[str], states: list[str], binding_cookies: list[str],
    exchange_verified: Callable[[str, Pending], VerifiedSession | None],
) -> VerifiedSession | None:
    """Accept only one value per input; the exchanger must attest the GitHub actor."""
    if (len(codes) != 1 or len(states) != 1 or len(binding_cookies) != 1
            or type(codes[0]) is not str or _CODE.fullmatch(codes[0]) is None
            or type(binding_cookies[0]) is not str or TOKEN.fullmatch(binding_cookies[0]) is None):
        return None
    pending = flow.consume(state=states[0], trusted_browser_binding=binding_cookies[0])
    if pending is None:
        return None
    session = exchange_verified(codes[0], pending)
    if (type(session) is not VerifiedSession or type(session.actor_id) is not int
            or session.actor_id <= 0 or type(session.token) is not str or not session.token):
        return None
    return session


def clear_binding_cookie() -> str:
    return f"{_COOKIE}=; Max-Age=0; {_COOKIE_ATTRIBUTES}"
