from __future__ import annotations

import base64
import hashlib
import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from nico import hosted_provider_comprehensive_runtime_v1 as runtime
from nico.admin_security import internal_admin_token
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import (
    HOSTED_PROVIDER_ORDER,
    STATE_KEY as ROLLOUT_STATE_KEY,
    ProviderRolloutConfig,
    ProviderRolloutRegistry,
    ProviderRolloutState,
)


class MemoryEvidenceStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict] = {}
        self.audits: list[tuple[str, dict, str, str]] = []

    def get(self, collection: str, item_id: str):
        return self.data.get((collection, item_id))

    def put(self, collection: str, item_id: str, value: dict):
        self.data[(collection, item_id)] = value
        return value

    def audit(
        self,
        action: str,
        payload: dict,
        *,
        customer_id: str = "",
        project_id: str = "",
    ) -> None:
        self.audits.append((action, payload, customer_id, project_id))


class FakeCollection:
    def __init__(self, provider: ProviderKind, revision: str, instance_url: str) -> None:
        self.provider = provider
        self.revision = revision
        self.collected_at = "2026-08-23T20:30:00+00:00"
        self.access_mode = "authenticated_read_only"
        self.credential_used = True
        self.pagination_complete = True
        self.rate_limit_state = {}
        self.collection_limitations = ()
        self.payload = {
            "revision": revision,
            "repository": {"id": f"{provider.value}-repo-id", "name": "repo"},
            "source_tree": [
                {"path": "src/app.py", "id": "f" * 40, "type": "blob"}
            ],
        }
        self._instance_url = instance_url

    def adapt(self):
        envelope = SimpleNamespace(
            access=SimpleNamespace(read_only=True),
            snapshot=SimpleNamespace(
                revision=self.revision,
                source_fingerprint="sha256:" + "a" * 64,
            ),
            identity=SimpleNamespace(
                repository_id=f"{self.provider.value}-repo-id",
                instance_url=self._instance_url,
                default_branch="main",
            ),
        )
        return SimpleNamespace(envelope=envelope, warnings=())


class FakeCollector:
    def __init__(self, provider: ProviderKind, revision: str, instance_url: str) -> None:
        self.provider = provider
        self.revision = revision
        self.instance_url = instance_url
        self.calls: list[tuple[str, str]] = []
        self.credential = SimpleNamespace(
            secret=SimpleNamespace(reveal=lambda: "fixture-provider-secret")
        )

    def collect(self, repository_id: str, *, revision: str = ""):
        selected = revision or self.revision
        self.calls.append((repository_id, selected))
        return FakeCollection(self.provider, selected, self.instance_url)

    def close(self) -> None:
        return None


def _rollout_registry() -> ProviderRolloutRegistry:
    configs = {
        provider: ProviderRolloutConfig(
            provider=provider,
            rollout_state=(
                ProviderRolloutState.CONTROLLED_PILOT
                if provider is ProviderKind.GITHUB
                else ProviderRolloutState.INTERNAL_TEST
            ),
            operational_enabled=True,
            credential_reference_id=f"server-only:{provider.value}",
            capability_evidence_reference=f"engineering:{provider.value}",
            repository_source_supported=True,
            native_ci_evidence_supported=True,
        )
        for provider in HOSTED_PROVIDER_ORDER
    }
    return ProviderRolloutRegistry(configs=configs)


def _controller(path: Path, evidence_store: MemoryEvidenceStore) -> ComprehensiveApiController:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    executors = {}

    for item in execution_plan():
        capability = item["capability"]

        def execute(context, *, _capability=capability):
            result = {
                "status": "complete",
                "capability": _capability,
                "run_id": context["run_id"],
                "repository": context["repository"],
                "commit_sha": context["commit_sha"],
                "evidence_ledger_id": context["evidence_ledger_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            if _capability == "repository_evidence":
                snapshots = [
                    record["evidence"]
                    for (collection, _), record in evidence_store.data.items()
                    if collection == "evidence_items"
                    and record.get("run_id") == context["run_id"]
                    and record.get("filename") == "provider-repository-snapshot.json"
                ]
                assert len(snapshots) == 1
                snapshot = snapshots[0]
                assert snapshot["repository"] == context["repository"]
                assert snapshot["commit_sha"] == context["commit_sha"]
                assert snapshot["exact_commit_verified"] is True
                assert snapshot["human_review_required"] is True
                assert snapshot["client_delivery_allowed"] is False
                result["repository_provider"] = snapshot["provider"]
                result["provider_repository_id"] = snapshot["provider_repository_id"]
                result["snapshot_id"] = snapshot["snapshot_id"]
            if _capability == "final_report_generation":
                pdf_bytes = b"%PDF-1.4\n%%EOF\n"
                identity = {
                    key: context[key]
                    for key in (
                        "run_id",
                        "repository",
                        "commit_sha",
                        "evidence_ledger_id",
                    )
                }
                canonical = {
                    "identity": identity,
                    "report_language": context["report_language"],
                    "locale": context["report_language"],
                }
                result["report_package"] = {
                    "report_id": f"report_{context['run_id']}",
                    "markdown": (
                        "# NICO Comprehensive Technical Assessment\n"
                        "CLIENT DELIVERY NOT AUTHORIZED"
                    ),
                    "html": (
                        "<html><body>NICO Comprehensive Technical Assessment</body></html>"
                    ),
                    "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                    "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                    "pdf_page_count": 1,
                    "json": canonical,
                    "canonical_truth_sha256": canonical_sha256(canonical),
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }
            return result

        executors[capability] = execute

    return ComprehensiveApiController(ComprehensiveRunService(store, executors))


def _request(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": runtime.OPERATOR_INTAKE_ROUTE,
            "raw_path": runtime.OPERATOR_INTAKE_ROUTE.encode("ascii"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
            "app": app,
        }
    )


def _continue_to_review(
    controller: ComprehensiveApiController,
    run_id: str,
    *,
    timeout: float = 4.0,
) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        last = controller.continue_run(run_id)
        if last.get("status") == "review_required":
            return last
        assert last.get("status") == "running"
        assert last.get("client_delivery_allowed") is False
        time.sleep(0.02)
    raise AssertionError(f"run did not reach human review before timeout: {last}")


@pytest.mark.parametrize(
    "provider,provider_token,provider_repository,organization,project,instance_url,expected_repository",
    (
        (
            ProviderKind.GITLAB,
            "gitlab",
            "group/subgroup/repo",
            "",
            "",
            "https://gitlab.com",
            "gitlab.com/group/subgroup/repo",
        ),
        (
            ProviderKind.BITBUCKET_CLOUD,
            "bitbucket_cloud",
            "workspace/repo",
            "",
            "",
            "https://bitbucket.org",
            "bitbucket.org/workspace/repo",
        ),
        (
            ProviderKind.AZURE_DEVOPS,
            "azure_devops",
            "repo",
            "Org",
            "Project",
            "https://dev.azure.com",
            "dev.azure.com/Org/Project/_git/repo",
        ),
    ),
)
def test_authorized_hosted_provider_intake_reaches_same_comprehensive_orchestration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: ProviderKind,
    provider_token: str,
    provider_repository: str,
    organization: str,
    project: str,
    instance_url: str,
    expected_repository: str,
) -> None:
    revision = {
        ProviderKind.GITLAB: "a" * 40,
        ProviderKind.BITBUCKET_CLOUD: "b" * 40,
        ProviderKind.AZURE_DEVOPS: "c" * 40,
    }[provider]
    evidence_store = MemoryEvidenceStore()
    collectors: list[FakeCollector] = []

    def build_client(selected_provider, context, *, environ=None):
        assert selected_provider is provider
        collector = FakeCollector(provider, revision, instance_url)
        collectors.append(collector)
        return collector

    monkeypatch.setattr(runtime, "STORE", evidence_store)
    monkeypatch.setattr(runtime, "build_hosted_provider_client", build_client)

    app = FastAPI()
    controller = _controller(tmp_path / f"{provider.value}.db", evidence_store)
    app.state.comprehensive_api_controller = controller
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "sqlite",
        "storage_source": "test",
        "durability_verified": True,
        "survives_container_replacement_verified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    setattr(app.state, ROLLOUT_STATE_KEY, _rollout_registry())

    payload = {
        "provider": provider_token,
        "repository": provider_repository,
        "provider_organization": organization,
        "provider_project": project,
        "customer_id": "customer-provider-parity",
        "project_id": "project-provider-parity",
        "session_id": "operator-provider-parity-session",
        "commit_sha": revision,
        "assessment_depth": "strategic",
        "report_language": "en-US",
        "execution_mode": "internal_test",
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": "nico_operator_fixture",
        "authorization_scope": "authorized defensive repository assessment",
    }

    started = runtime._operator_intake(
        _request(app),
        payload,
        internal_admin_token(),
    )

    assert started["operation"] == "operator_provider_intake_started"
    assert started["service_id"] == "comprehensive"
    assert started["repository"] == expected_repository
    assert started["repository_provider"] == provider.value
    assert started["provider_repository"] == provider_repository
    assert started["repository_snapshot"]["repository"] == expected_repository
    assert started["repository_snapshot"]["commit_sha"] == revision
    assert started["repository_snapshot"]["exact_commit_verified"] is True
    assert started["operator_run_only"] is True
    assert started["customer_self_service"] is False
    assert started["human_review_required"] is True
    assert started["client_delivery_allowed"] is False
    assert collectors and collectors[0].calls == [(provider_repository, revision)]

    final = _continue_to_review(controller, started["run_id"])
    assert final["completed_stages"] == list(COMPREHENSIVE_STAGES)
    repository_stage = final["record"]["stage_results"][
        "repository_and_delivery_evidence"
    ]
    assert repository_stage["repository_provider"] == provider.value
    assert repository_stage["repository"] == expected_repository
    assert repository_stage["commit_sha"] == revision
    assert repository_stage["snapshot_id"].startswith("snapshot_")
    assert final["human_review_required"] is True
    assert final["client_delivery_allowed"] is False
    assert final["status"] == "review_required"

    serialized = repr(evidence_store.data)
    assert "fixture-provider-secret" not in serialized


def test_operator_provider_intake_rejects_raw_credentials_before_acquisition(
    tmp_path: Path,
) -> None:
    app = FastAPI()
    evidence_store = MemoryEvidenceStore()
    app.state.comprehensive_api_controller = _controller(
        tmp_path / "credentials.db", evidence_store
    )
    setattr(app.state, ROLLOUT_STATE_KEY, _rollout_registry())

    with pytest.raises(ValueError, match="raw_provider_credentials_prohibited"):
        runtime._operator_intake(
            _request(app),
            {
                "provider": "gitlab",
                "repository": "group/repo",
                "customer_id": "customer-provider-parity",
                "project_id": "project-provider-parity",
                "commit_sha": "d" * 40,
                "authorized": True,
                "authorization_confirmed": True,
                "token": "must-not-enter-runtime",
            },
            internal_admin_token(),
        )
