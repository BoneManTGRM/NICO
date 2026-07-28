from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from nico.phase7_release_gate_v1 import GateResult, evaluate_release_gate

VERSION = "nico.phase7_evidence_manifest.v1"


@dataclass(frozen=True)
class EvidenceItem:
    gate: str
    reference: str
    sha256: str
    commit_sha: str

    def validate(self, *, expected_commit_sha: str) -> None:
        if not self.reference.strip():
            raise RuntimeError(f"Evidence reference missing for gate {self.gate}")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256.lower()):
            raise RuntimeError(f"Invalid SHA-256 for gate {self.gate}")
        if self.commit_sha != expected_commit_sha:
            raise RuntimeError(f"Evidence revision mismatch for gate {self.gate}")


def build_phase7_manifest(
    *,
    commit_sha: str,
    gate_results: Sequence[GateResult],
    evidence_items: Sequence[EvidenceItem],
) -> dict:
    if not commit_sha.strip():
        raise RuntimeError("Integrated commit SHA is required")

    decision = evaluate_release_gate(gate_results)
    evidence_by_gate = {item.gate: item for item in evidence_items}
    missing_evidence = []
    for result in gate_results:
        if result.passed:
            item = evidence_by_gate.get(result.name)
            if item is None:
                missing_evidence.append(result.name)
                continue
            item.validate(expected_commit_sha=commit_sha)
            if result.evidence_reference != item.reference:
                raise RuntimeError(f"Gate evidence reference mismatch for {result.name}")

    if missing_evidence:
        raise RuntimeError(f"Integrated evidence manifest incomplete: {sorted(missing_evidence)}")

    canonical = {
        "version": VERSION,
        "commit_sha": commit_sha,
        "release_decision": decision,
        "evidence": [item.__dict__ for item in sorted(evidence_items, key=lambda value: value.gate)],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    canonical["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    canonical["ready_to_merge"] = bool(decision["ready_to_merge"])
    canonical["merge_performed"] = False
    return canonical


__all__ = ["EvidenceItem", "build_phase7_manifest"]
