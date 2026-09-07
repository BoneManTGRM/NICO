"""CI proof contract and safe failure reporting; native PostgreSQL runs in CI."""
import json

import pytest

from scripts import postgres_scanner_artifact_proof as proof


@pytest.mark.parametrize("url", ["", "postgresql://u:secret@production.example/nico", "postgresql://u:secret@127.0.0.1/customer", "postgresql://u:secret@127.0.0.1/nico?host=production.example", "postgresql://u:secret@127.0.0.1:5444/nico"])
def test_refuses_non_ci_database_before_adapter_creation(url, monkeypatch):
    monkeypatch.setattr(proof, "_new_adapter", lambda *_: pytest.fail("must reject before connecting"))
    with pytest.raises(proof.ProofFailure, match="test_database_required"):
        proof.run_proof(url)


def test_cli_failure_never_emits_exception_or_dsn(tmp_path, monkeypatch, capsys):
    secret = "postgresql://nico:DO-NOT-DISCLOSE@127.0.0.1:5432/nico"
    monkeypatch.setenv("NICO_TEST_DATABASE_URL", secret)
    def fail(url):
        assert url == secret
        raise RuntimeError("driver echoed " + secret)
    monkeypatch.setattr(proof, "run_proof", fail)
    output = tmp_path / "failed.json"
    assert proof.main(["--output", str(output)]) == 1
    artifact = json.loads(output.read_text())
    assert artifact["status"] == "failed"
    assert artifact["error_code"] == "scanner_artifact_proof_failed"
    assert artifact["synthetic"] is True
    assert artifact["live_production_claim"] is False
    rendered = output.read_text() + capsys.readouterr().out
    assert "postgresql://" not in rendered and "DO-NOT-DISCLOSE" not in rendered
    assert "driver echoed" not in rendered


def test_cli_writes_only_bounded_success_evidence(tmp_path, monkeypatch, capsys):
    payload = {"schema_version": 1, "evidence_kind": "synthetic_postgres_scanner_artifact_proof", "synthetic": True, "live_production_claim": False, "status": "passed", "proof": {"original_bytes_preserved": True}}
    monkeypatch.setattr(proof, "run_proof", lambda _: payload)
    output = tmp_path / "passed.json"
    assert proof.main(["--output", str(output)]) == 0
    assert json.loads(output.read_text()) == payload
    assert json.loads(capsys.readouterr().out) == {"status": "passed"}


def test_proof_control_flow_with_local_sql_boundary_is_explicitly_not_native_pg_evidence(tmp_path, monkeypatch):
    # Reuse the regression's SQL translation boundary; CI executes without it.
    from test_scanner_retention_survives_runtime_replacement_v1 import _Connection
    from nico.storage import PostgresAdapter, STORE
    database = tmp_path / "local-proof.sqlite3"
    instances = []
    def reopen(_):
        adapter = PostgresAdapter.__new__(PostgresAdapter)
        adapter._connect = lambda: _Connection(database)
        adapter._jsonb = json.dumps
        adapter._init_schema()
        instances.append(adapter)
        return adapter
    monkeypatch.setattr(proof, "_new_adapter", reopen)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    previous = STORE.adapter
    evidence = proof.run_proof("postgresql://nico:synthetic@127.0.0.1:5432/nico")
    assert STORE.adapter is previous
    assert len(instances) == 2 and instances[0] is not instances[1]
    assert evidence["application_commit"] == "b" * 40
    assert evidence["proof"]["original_bytes_preserved"] is True
    assert evidence["proof"]["conflicting_overwrite_rejected"] is True
    assert evidence["proof"]["human_approval"] is False
    serialized = json.dumps(evidence)
    assert "postgresql://" not in serialized and "original scanner bytes" not in serialized
    assert "gzip_blob" not in serialized and "storage_key" not in serialized


def test_refuses_ambient_application_database_before_import_or_connection(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://owner:DO-NOT-DISCLOSE@production.example/nico")
    monkeypatch.setattr(proof, "_new_adapter", lambda *_: pytest.fail("must not connect"))
    with pytest.raises(proof.ProofFailure, match="test_database_required"):
        proof.run_proof("postgresql://nico:synthetic@127.0.0.1:5432/nico")
