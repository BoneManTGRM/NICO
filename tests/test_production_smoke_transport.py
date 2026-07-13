from __future__ import annotations

import json
from typing import Any

import pytest

from nico.production_assessment_smoke import SmokeFailure, UrlLibTransport, verify_deployment_statuses

SHA = "a" * 40

def test_admin_secret_is_sent_only_to_the_read_only_delivery_check() -> None:
    observed: list[tuple[str, str | None]] = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    class Opener:
        def open(self, request, timeout):
            assert timeout == 120.0
            observed.append((request.full_url, request.get_header("X-nico-admin-token")))
            return Response()

    transport = UrlLibTransport("https://nico-production-690a.up.railway.app", "admin-secret")
    transport._opener = Opener()
    transport.request_json("GET", "/health")
    transport.request_json(
        "GET",
        "/assessment/full-run/fullrun_exact_1/approved-delivery/readiness?customer_id=a&project_id=b",
        admin=True,
    )

    assert observed[0][1] is None
    assert observed[1][1] == "admin-secret"
    with pytest.raises(SmokeFailure) as error:
        transport.request_json("GET", "/health?unexpected=true")
    assert error.value.code == "unsafe_request_path"


def test_deployment_status_verifier_requires_both_providers() -> None:
    class Response:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def opener(_request, timeout):
        assert timeout == 30.0
        return Response(
            {
                "statuses": [
                    {"context": "Vercel", "state": "success", "target_url": "https://vercel.com/example"},
                    {"context": "successful-cat - NICO", "state": "success", "target_url": "https://railway.com/example"},
                    {"context": "unrelated", "state": "failure", "target_url": "https://example.com"},
                ]
            }
        )

    result = verify_deployment_statuses("BoneManTGRM/NICO", SHA, "token", opener=opener)
    assert result["status"] == "passed"
    assert [item["provider"] for item in result["checks"]] == ["vercel", "railway"]


def test_deployment_status_verifier_does_not_accept_stale_success() -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "statuses": [
                        {"context": "Vercel", "state": "pending", "target_url": "https://vercel.com/new"},
                        {"context": "Vercel", "state": "success", "target_url": "https://vercel.com/old"},
                        {"context": "successful-cat - NICO", "state": "success", "target_url": "https://railway.com/current"},
                    ]
                }
            ).encode("utf-8")

    with pytest.raises(SmokeFailure) as error:
        verify_deployment_statuses("BoneManTGRM/NICO", SHA, "token", opener=lambda *_args, **_kwargs: Response())
    assert error.value.code == "deployment_not_verified"


