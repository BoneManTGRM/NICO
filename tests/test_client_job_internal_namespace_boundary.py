"""Public draft operations must not borrow authority over internal persisted jobs."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from nico import client_job_mode as mode


class IsolatedJobStore:
    def __init__(self, job_id, workflow="comprehensive_background_stage"):
        self.records = {
            ("client_jobs", job_id): {
                "job_id": job_id,
                "status": "complete",
                "workflow": workflow,
                "result": {"report": {"marker": "SYNTHETIC_PRIVATE_BACKGROUND_REPORT"}},
            }
        }
        self.reads = []
        self.writes = []
        self.lists = []
        self.audits = []

    def get(self, collection, key):
        self.reads.append((collection, key))
        return deepcopy(self.records.get((collection, key)))

    def put(self, collection, key, value):
        self.writes.append((collection, key))
        self.records[(collection, key)] = deepcopy(value)

    def list(self, collection):
        self.lists.append(collection)
        return [deepcopy(value) for (name, _), value in self.records.items() if name == collection]

    def audit(self, *args, **kwargs):
        self.audits.append((args, kwargs))


OPERATIONS = {
    "build": (lambda job: mode.build_client_job_package({"job_id": job}), "blocked"),
    "create": (lambda job: mode.create_client_job_package({"job_id": job}), "blocked"),
    "get": (mode.get_client_job_package, "not_found"),
    "export": (mode.export_client_job_package, "not_found"),
    "list": (mode.list_client_job_exports, "not_found"),
}


@pytest.mark.parametrize("job_id", ["workerjob_isolated_boundary", "comprehensive_stage_isolated_boundary"])
@pytest.mark.parametrize("operation", OPERATIONS)
def test_reserved_internal_namespace_rejects_before_storage(monkeypatch, job_id, operation):
    store = IsolatedJobStore(job_id)
    monkeypatch.setattr(mode, "STORE", store)
    invoke, expected = OPERATIONS[operation]
    assert invoke(job_id) == (
        {"status": "blocked", "code": "reserved_job_namespace", "job_id": job_id}
        if expected == "blocked"
        else {"status": "not_found", "job_id": job_id}
    )
    assert not (store.reads or store.writes or store.lists or store.audits)


@pytest.mark.parametrize("workflow", ["assessment_worker_job.v1", "comprehensive_background_stage"])
@pytest.mark.parametrize("operation", ["create", "get", "export", "list"])
def test_legacy_internal_workflow_rejects_without_disclosure_or_overwrite(monkeypatch, workflow, operation):
    job_id = "legacy_isolated_job"
    store = IsolatedJobStore(job_id, workflow)
    original = deepcopy(store.records)
    monkeypatch.setattr(mode, "STORE", store)
    invoke, expected = OPERATIONS[operation]
    result = invoke(job_id)
    assert result["status"] == expected
    assert set(result) <= {"status", "code", "job_id"}
    assert store.records == original
    assert not (store.writes or store.lists or store.audits)


@pytest.mark.parametrize("workflow", ["assessment_worker_job.v1", "comprehensive_background_stage"])
@pytest.mark.parametrize("export_format", ["json", "markdown", "html", "pdf", "invalid"])
def test_internal_workflow_cannot_enter_any_export_renderer(monkeypatch, workflow, export_format):
    store = IsolatedJobStore("legacy_isolated_job", workflow)
    monkeypatch.setattr(mode, "STORE", store)
    def unexpected_renderer(*args, **kwargs):
        pytest.fail("internal package entered a public draft renderer")
    monkeypatch.setattr(mode, "client_job_markdown", unexpected_renderer)
    monkeypatch.setattr(mode, "client_job_html", unexpected_renderer)
    monkeypatch.setattr(mode, "client_job_pdf_base64", unexpected_renderer)
    result = mode.render_client_job_export(
        {"job_id": "legacy_isolated_job", "workflow": workflow}, export_format
    )
    assert result["status"] == "blocked"
    assert result["code"] == "reserved_job_namespace"
    assert not (store.reads or store.writes or store.lists or store.audits)


def test_public_draft_create_retrieve_and_export_preserve_human_review(monkeypatch):
    store = IsolatedJobStore("comprehensive_stage_unrelated")
    monkeypatch.setattr(mode, "STORE", store)
    created = mode.create_client_job_package({"job_id": "client_job_public_isolated"})
    assert created["status"] == "ok"
    assert mode.get_client_job_package(created["job_id"]) == created
    exported = mode.export_client_job_package(created["job_id"], "json")
    assert exported["status"] == "complete"
    assert exported["human_review_required"] is True
    assert mode.list_client_job_exports(created["job_id"])["exports"] == [exported]


@pytest.mark.parametrize("workflow,job_id", [
    ("comprehensive_background_stage", "comprehensive_stage_isolated_boundary"),
    ("comprehensive_background_stage", "legacy_isolated_job"),
    ("assessment_worker_job.v1", "workerjob_isolated_boundary"),
    ("assessment_worker_job.v1", "legacy_isolated_job"),
])
def test_mounted_public_package_routes_never_disclose_or_write_internal_jobs(monkeypatch, workflow, job_id):
    from nico.api.specialist_ship_ready_bootstrap import app

    store = IsolatedJobStore(job_id, workflow)
    original = deepcopy(store.records)
    monkeypatch.setattr(mode, "STORE", store)
    with TestClient(app) as client:
        responses = [
            client.get(f"/client-job/{job_id}"),
            client.get(f"/client-job/{job_id}/exports"),
            client.post("/client-job/export", json={"job_id": job_id, "format": "json"}),
            client.post("/client-job/package", json={"job_id": job_id}),
        ]
    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] in {"not_found", "blocked"}
        assert set(payload) <= {"status", "code", "job_id"}
        assert "SYNTHETIC_PRIVATE_BACKGROUND_REPORT" not in response.text
    assert store.records == original
    assert not (store.writes or store.lists or store.audits)
