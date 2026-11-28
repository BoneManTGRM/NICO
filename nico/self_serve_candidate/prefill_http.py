"""Dormant FastAPI adapter. No app mounts it without explicit trusted services."""
from dataclasses import dataclass
from typing import Annotated, Callable, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .oauth_callback import (
    ResumedIntake, begin_authorization, clear_binding_cookie, resume_intake,
)
from .oauth_state import GithubAppFlow, Pending
from .pending_intake import PendingIntake
from .provider_download import VerifiedSession

_PRIVATE = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}
_RECEIPT_COOKIE_NAME = "__Host-nico_requester_oauth"
_LIMIT = 4096
_PREFIX = "/requester/self-serve"


class IntakeForm(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: Annotated[str, Field(min_length=1, max_length=160)]
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    permission_attested: bool
    terms_shown: Annotated[str, Field(min_length=1, max_length=64)]
    locale: Literal["en", "es-MX"] = "en"


@dataclass(frozen=True)
class PrefillDependencies:
    browser_origin: str
    client_id: str
    flow: GithubAppFlow
    terms_revision: Callable[[], str]
    exchange: Callable[[str, Pending], VerifiedSession | None]
    # Must issue private, session-bound continuation via an app-owned response.
    # It must not authorize delivery or start a run.
    handoff: Callable[[ResumedIntake], Response]


def _error(status, reason):
    return JSONResponse({"reason": reason}, status_code=status, headers=_PRIVATE)


def _binding_values(request):
    matches = []
    for header in request.headers.getlist("cookie"):
        for item in header.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == _RECEIPT_COOKIE_NAME:
                matches.append(value)
    return matches


def requester_prefill_router(deps: PrefillDependencies) -> APIRouter:
    origin = urlsplit(deps.browser_origin)
    if (origin.scheme != "https" or not origin.hostname or origin.username is not None
            or origin.password is not None or origin.path or origin.fragment or origin.query
            or deps.browser_origin != f"https://{origin.netloc}"):
        raise ValueError("invalid configured requester origin")
    if deps.flow.registered_callback != deps.browser_origin + _PREFIX + "/callback":
        raise ValueError("configured requester callback does not match this route")
    router = APIRouter(prefix=_PREFIX)

    @router.post("/sign-in", include_in_schema=False)
    async def start(request: Request):
        if request.headers.getlist("origin") != [deps.browser_origin]:
            return _error(403, "origin_not_allowed")
        if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
            return _error(415, "json_required")
        data = bytearray()
        async for piece in request.stream():
            if len(piece) > _LIMIT - len(data):
                return _error(413, "intake_too_large")
            data.extend(piece)
        try:
            form = IntakeForm.model_validate_json(bytes(data))
        except ValidationError:
            return _error(400, "invalid_intake")
        terms = await run_in_threadpool(deps.terms_revision)
        if form.terms_shown != terms:
            return _error(409, "terms_changed")
        try:
            draft = PendingIntake(form.repository, form.full_name, form.permission_attested, terms, form.locale)
            if draft.permission_attested is not True:
                return _error(400, "attestation_required")
            start = await run_in_threadpool(begin_authorization, deps.flow, client_id=deps.client_id, intake=draft)
        except ValueError:
            return _error(400, "invalid_intake")
        return JSONResponse({"authorization_url": start.location}, status_code=200,
                            headers={**_PRIVATE, "Set-Cookie": start.cookie})

    @router.get("/callback", include_in_schema=False)
    def callback(request: Request):
        result = resume_intake(
            deps.flow, codes=request.query_params.getlist("code"),
            states=request.query_params.getlist("state"), binding_cookies=_binding_values(request),
            exchange_verified=deps.exchange, current_terms=deps.terms_revision(),
        )
        if result is None:
            # An invalid or old tab must not clear the current tab's binding.
            return _error(403, "sign_in_unavailable")
        response = deps.handoff(result)
        for name, value in _PRIVATE.items():
            response.headers[name] = value
        response.headers.append("Set-Cookie", clear_binding_cookie())
        return response

    return router
