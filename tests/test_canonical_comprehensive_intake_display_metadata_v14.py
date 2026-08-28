from __future__ import annotations

from types import SimpleNamespace

from nico import comprehensive_api_routes as routes
from nico.comprehensive_report_worker_runtime_v90 import _report_identity
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


class _CapturingController:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        self.payload = payload
        return {
            "status": "ready",
            "client_delivery_allowed": False,
            "human_review_required": True,
        }


def _request() -> SimpleNamespace:
    state = SimpleNamespace(
        comprehensive_runtime={
            "configured": True,
            "persistence_adapter": "postgres",
            "durability_verified": True,
            "survives_container_replacement_verified": True,
        }
    )
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_canonical_intake_retains_exact_display_metadata_without_runtime_wrapper(monkeypatch) -> None:
    controller = _CapturingController()
    monkeypatch.setattr(routes, "_controller", lambda _request: controller)
    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda _payload: {
            "status": "attached",
            "commit_sha": "a" * 40,
        },
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda _payload: "")

    response = routes._intake(
        _request(),
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_acme",
            "project_id": "project_apollo",
            "client_name": "  Acme   Holdings  ",
            "project_name": "  Apollo   Modernization  ",
            "assessment_depth": "strategic",
            "report_language": "en",
            "authorized": True,
            "authorization_confirmed": True,
            "human_evidence": {
                "stakeholder_context": {
                    "evidence": {
                        "primary_technical_contact": "Nora Engineer",
                        "access_method": "GitHub HTTPS/API - read-only",
                        "authorized_scope": "Exact assessed repository SHA - read-only",
                    }
                }
            },
        },
    )

    assert controller.payload is not None
    assert controller.payload["client_name"] == "  Acme   Holdings  "
    assert controller.payload["project_name"] == "  Apollo   Modernization  "

    raw_human_evidence = controller.payload["human_evidence"]
    assert isinstance(raw_human_evidence, dict)
    stakeholder = raw_human_evidence["stakeholder_context"]
    assert isinstance(stakeholder, dict)
    evidence = stakeholder["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["customer_name"] == "  Acme   Holdings  "
    assert evidence["project_name"] == "  Apollo   Modernization  "
    assert evidence["primary_technical_contact"] == "Nora Engineer"

    retained = normalize_strategic_human_evidence(raw_human_evidence)
    report_identity = _report_identity(
        {
            "run_id": str(controller.payload["run_id"]),
            "repository": str(controller.payload["repository"]),
            "commit_sha": str(controller.payload["commit_sha"]),
            "evidence_ledger_id": str(controller.payload["evidence_ledger_id"]),
            "customer_id": str(controller.payload["customer_id"]),
            "project_id": str(controller.payload["project_id"]),
            "assessment_depth": "strategic",
            "report_language": "en",
            "human_evidence": retained,
        }
    )
    assert report_identity["customer_name"] == "  Acme   Holdings  "
    assert report_identity["project_name"] == "  Apollo   Modernization  "
    assert report_identity["primary_technical_contact"] == "Nora Engineer"

    assert response["client_name"] == "  Acme   Holdings  "
    assert response["project_name"] == "  Apollo   Modernization  "
    assert response["client_delivery_allowed"] is False
    assert response["human_review_required"] is True
