from types import SimpleNamespace

import pytest

from scripts import postgres_run_storage_capacity_proof as proof


@pytest.mark.parametrize(("field", "value", "code"), [
    ("human_review_required", False, "capacity_review_gate_weakened"),
    ("client_delivery_allowed", True, "capacity_delivery_gate_weakened"),
    ("synthetic_capacity_evidence", ["altered"], "capacity_alias_content_mismatch"),
    ("synthetic_capacity_evidence", [], "capacity_alias_count_mismatch"),
])
def test_fresh_process_proof_rejects_weakened_gates_or_lost_evidence(monkeypatch, field, value, code):
    restored = {"identity": {"run_id": "comprun_test"}, "revision": 2,
                "integrity_sha256": "a" * 64, "human_review_required": True,
                "client_delivery_allowed": False, "synthetic_capacity_evidence": ["original"]}
    expected = {"identity": restored["identity"], "revision": 2,
                "integrity_sha256": "a" * 64, "alias_count": 1,
                "alias_sha256": proof.canonical_hash("original")}
    restored[field] = value
    monkeypatch.setattr(proof, "store", lambda: SimpleNamespace(load=lambda run_id: restored))
    with pytest.raises(ValueError, match=code):
        proof.fresh_reader("comprun_test", expected)
