from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_production_bootstrap_composes_exact_metadata_with_phase3_guard(
    tmp_path: Path,
) -> None:
    """Exercise the production wrapper order in an isolated interpreter.

    The same-run locale entrypoint installs the direct metadata binding after the
    Phase-3 engagement intake guard. Both boundaries must remain in the executable
    chain: the outer binding preserves literal values and the inner guard validates
    and enriches real-client delivery identity.
    """

    script = r'''
import json
import os
import sqlite3
from types import SimpleNamespace

import nico.api.same_run_locale_report_bootstrap  # noqa: F401
from nico import comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_engagement_metadata_v1 import verify_comprehensive_engagement_metadata
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore

database = os.environ["NICO_COMPOSITION_TEST_DATABASE"]

def connect():
    return sqlite3.connect(database)

store = ComprehensiveRunStore(connect)
store.ensure_schema()
service = ComprehensiveRunService(store, {})
controller = ComprehensiveApiController(service)
request = SimpleNamespace(
    app=SimpleNamespace(
        state=SimpleNamespace(
            comprehensive_api_controller=controller,
            comprehensive_runtime={
                "configured": True,
                "persistence_adapter": "sqlite",
                "durability_verified": True,
                "survives_container_replacement_verified": True,
            },
        )
    )
)

snapshot_calls = []

def snapshot(payload):
    snapshot_calls.append(dict(payload))
    return {"status": "attached", "commit_sha": "a" * 40}

routes.capture_repository_snapshot = snapshot
routes.expected_commit_sha = lambda _payload: ""

fixture = {
    "client_name": "Compañía  Águila, S.A. de C.V.",
    "project_name": "Proyecto Ñandú /  Release 2.0",
    "primary_technical_contact": "María-José  Pérez - CTO /\nIngeniería",
    "access_method": "GitHub Enterprise - acceso de  solo lectura",
    "authorized_scope": "organizacion/proyecto - rama release/2026.08;\ncódigo, configuración y CI/CD.",
}

payload = {
    "repository": "organizacion/proyecto",
    "customer_id": "customer_aguila",
    "project_id": "project_nandu",
    "client_name": fixture["client_name"],
    "project_name": fixture["project_name"],
    "authorized": True,
    "authorization_confirmed": True,
    "human_evidence": {
        "stakeholder_context": {
            "evidence": {
                "primary_technical_contact": [fixture["primary_technical_contact"]],
                "access_method": [fixture["access_method"]],
                "authorized_scope": [fixture["authorized_scope"]],
            }
        }
    },
}

response = routes._intake(request, payload)
record = store.load(response["run_id"])
engagement = record["engagement_metadata"]
stakeholder = record["human_evidence"]["modules"]["stakeholder_context"]["evidence"]

missing_context_rejected = False
try:
    routes._intake(
        request,
        {
            **payload,
            "client_name": "Second Client",
            "project_name": "Second Project",
            "human_evidence": {"stakeholder_context": {"evidence": {}}},
        },
    )
except ValueError as exc:
    missing_context_rejected = str(exc).startswith(
        "client_engagement_context_required:"
    )

chain = []
current = routes._intake
seen = set()
while callable(current) and id(current) not in seen:
    seen.add(id(current))
    chain.append(
        {
            "name": getattr(current, "__name__", ""),
            "direct": bool(getattr(current, "_nico_direct_display_metadata_v2", False)),
            "phase3": bool(getattr(current, "_nico_phase3_engagement_intake_v1", False)),
        }
    )
    current = getattr(current, "__wrapped__", None) or getattr(
        current, "_nico_previous", None
    )

print(json.dumps({
    "fixture": fixture,
    "engagement": engagement,
    "engagement_verified": verify_comprehensive_engagement_metadata(engagement),
    "stakeholder": stakeholder,
    "missing_context_rejected": missing_context_rejected,
    "snapshot_call_count": len(snapshot_calls),
    "chain": chain,
}, ensure_ascii=False))
'''

    environment = dict(os.environ)
    environment["NICO_COMPOSITION_TEST_DATABASE"] = str(
        tmp_path / "production-wrapper-order.sqlite3"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)

    assert result["engagement_verified"] is True
    assert {
        field: result["engagement"][field]
        for field in (
            "client_name",
            "project_name",
            "primary_technical_contact",
            "access_method",
            "authorized_scope",
        )
    } == result["fixture"]

    stakeholder = result["stakeholder"]
    assert stakeholder["engagement_mode"] == ["client"]
    assert stakeholder["client_identity"] == [result["fixture"]["client_name"]]
    assert stakeholder["project_identity"] == [result["fixture"]["project_name"]]
    assert stakeholder["primary_technical_contact"] == [
        result["fixture"]["primary_technical_contact"]
    ]
    assert stakeholder["access_method"] == [result["fixture"]["access_method"]]
    assert stakeholder["authorized_scope"] == [
        result["fixture"]["authorized_scope"]
    ]

    assert result["missing_context_rejected"] is True
    # The invalid second intake must fail before repository snapshot work.
    assert result["snapshot_call_count"] == 1
    assert any(item["direct"] for item in result["chain"])
