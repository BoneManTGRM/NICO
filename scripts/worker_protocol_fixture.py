"""Synthetic transport fixture. No analyzer/build/target execution is claimed."""
from copy import deepcopy
from dataclasses import asdict
import hashlib

from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import CONFIGURATION


def contract():
    return {"profile": "cppcheck-standalone-v1", "tool_version": "2.17.1",
        "image_digest": "sha256:" + "d" * 64, "configuration": deepcopy(CONFIGURATION),
        "targets": {"src/control.cpp": hashlib.sha256(b"int value() {return 1;}\n").hexdigest()},
        "limits": {"max_attempts": 2, "wall_seconds": 120, "lease_seconds": 30},
        "max_receipt_bytes": 65536}


def identity(plan=None):
    return JobIdentity("synthetic-tenant", "synthetic-project", "synthetic-run", "synthetic-scan",
                       "example/owned-control", "a" * 40, _digest(plan or contract()), "c" * 40)


def receipt(job=None, lease="e" * 32, worker="github:123456:12345678:1", plan=None):
    plan = plan or contract()
    job = job or identity(plan)
    native = {"xml": '<results version="2"><cppcheck version="2.17.1"/><errors>'
        '<error id="syntheticDiagnostic" severity="warning" msg="Synthetic protocol fixture">'
        '<location file="src/control.cpp" line="1" column="1"/></error></errors></results>',
        "progress": "Checking src/control.cpp ...\n", "exit_code": 0, "timed_out": False,
        "output_truncated": False, "duration_ms": 12,
        "invocation": ["cppcheck", "--xml", "--enable=warning,style,performance,portability,information",
            "--check-level=normal", "--max-configs=12", "--std=c++20", "--std=c11", "--platform=unix64",
            "-j2", "--file-list=/work/cppcheck-inputs.txt", "--output-file=/work/cppcheck.xml"]}
    return {"schema": "nico.worker-native-receipt.v1", "identity": asdict(job), "lease_id": lease,
        "worker_id": worker, "image_digest": plan["image_digest"], "tool_version": plan["tool_version"],
        "configuration_sha256": _digest(plan["configuration"]), "target_hashes": deepcopy(plan["targets"]),
        "native": native, "native_sha256": _digest(native)}
