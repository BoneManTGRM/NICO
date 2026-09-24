from copy import deepcopy
import hashlib
from nico.assessment_worker_receipts import canonical_bytes
from nico.assessment_cpp_configure_first_execution import summarize_probe

def ref(key, raw=b"x"):
    return {"artifact_id":"scanartifact_"+"a"*64,"key":key,"sha256":hashlib.sha256(raw).hexdigest(),
        "gzip_sha256":"b"*64,"retained_bytes":len(raw),"gzip_bytes":1,"storage_backend":"postgres"}

def proof():
    ids=["c1","c2"]
    return {"status":"BASELINE_EXECUTED","error":None,"compiled":True,"tests_executed":True,"tests_passed":True,
        "tests_discovered":["a","b"],"tests_result":{"executed":["a","b"],"passed":["a","b"],"skipped":[]},
        "generated_context_verified":True,"boundary_verified":True,"cleanup_verified":True,"scratch_capacity_verified":True,
        "memory_peak_bytes":123,"duration_ms":10,"aggregate_duration_ms":20,
        "compilation_database_sha256":"c"*64,"configured_invocations":2,
        "baseline_execution_frozen":{"schema":"nico.cpp-baseline-execution-freeze.v1"},
        "project_compiler":{"required_contexts":ids,"checked_contexts":ids,"complete":True},
        "project_static":{"required_contexts":ids,"analyzed_contexts":ids,"complete":True,
            "findings":[{"id":"f1"}],"limitations":[],"modeled_inputs":[]},
        "project_static_stage":{"complete":True,"memory_peak_bytes":456}}

def test_summary_is_hash_bound_and_keeps_canonical_projection_pending():
    targets={"CMakeLists.txt":"d"*64,"src/a.cpp":"e"*64}
    artifacts={k:ref(k) for k in ("project-generated-context","project-compiler-evidence",
        "project-static-environment","project-static-evidence")}
    result=summarize_probe(proof(),targets,artifacts)
    assert result["complete_execution"] is True
    assert result["canonical_findings_projected"] is False
    assert result["source_population_sha256"]==hashlib.sha256(canonical_bytes(targets)).hexdigest()
    assert result["project_static_findings_count"]==1
    assert result["project_compiler_required_count"]==result["project_compiler_checked_count"]==2

def test_summary_never_claims_complete_without_every_required_artifact():
    targets={"CMakeLists.txt":"d"*64}
    artifacts={k:ref(k) for k in ("project-generated-context","project-compiler-evidence","project-static-evidence")}
    result=summarize_probe(proof(),targets,artifacts)
    assert result["complete_execution"] is False

def test_summary_rejects_artifact_identity_substitution():
    targets={"CMakeLists.txt":"d"*64}
    artifacts={k:ref(k) for k in ("project-generated-context","project-compiler-evidence",
        "project-static-environment","project-static-evidence")}
    artifacts["project-static-evidence"]={**artifacts["project-static-evidence"],"key":"project-static-environment"}
    import pytest
    with pytest.raises(ValueError,match="artifact_reference"):
        summarize_probe(proof(),targets,artifacts)
