"""Backend reconstruction of configure-first C/C++ native artifacts.

No assessed code executes here. Exact retained native bytes are read back from
the immutable PostgreSQL artifact store and passed through the same controller
validators that qualified the worker output.
"""
from __future__ import annotations
from copy import deepcopy
import gzip
import hashlib
import io

from nico.assessment_worker_jobs import _digest
from nico.assessment_worker_receipts import canonical_bytes

MAX_COMPRESSED = 8 * 1024 * 1024
MAX_RAW = 64 * 1024 * 1024


def _read_artifact(store, identity, reference, key):
    if (not isinstance(reference,dict) or reference.get("key")!=key
            or reference.get("storage_backend")!="postgres"
            or not isinstance(reference.get("artifact_id"),str)
            or not reference["artifact_id"].startswith("scanartifact_")):
        raise ValueError("worker_configure_first_artifact_reference_invalid")
    stored=store.get(reference["artifact_id"],limit=MAX_COMPRESSED)
    expected={"run_id":identity.run_id,"scan_id":identity.scan_id,"customer_id":identity.customer_id,
        "project_id":identity.project_id,"repository":identity.repository_id,"commit_sha":identity.revision,
        "scanner_name":"cppcheck:"+key}
    if (not isinstance(stored,dict) or stored.get("binding")!=expected or stored.get("compressed") is None
            or stored.get("sha256")!=reference.get("sha256")
            or stored.get("gzip_sha256")!=reference.get("gzip_sha256")
            or stored.get("compressed_bytes")!=reference.get("gzip_bytes")):
        raise ValueError("worker_configure_first_artifact_binding_invalid")
    compressed=stored["compressed"]
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed),mode="rb") as stream:
            raw=stream.read(min(MAX_RAW,reference.get("retained_bytes",0))+1)
    except (gzip.BadGzipFile,EOFError,OSError) as exc:
        raise ValueError("worker_configure_first_artifact_gzip_invalid") from exc
    if (len(raw)!=reference.get("retained_bytes") or len(raw)>MAX_RAW
            or hashlib.sha256(raw).hexdigest()!=reference.get("sha256")):
        raise ValueError("worker_configure_first_artifact_digest_invalid")
    return raw


def _population(values):
    return len(values),hashlib.sha256(canonical_bytes(values)).hexdigest()


def reconstruct_configure_first(identity, contract, receipt, store):
    from nico.assessment_cpp_full_project import _database,_json
    from nico.assessment_cpp_project_snapshot import validate_project_snapshot
    from nico.assessment_cpp_project_compiler import project_compiler_request,validate_project_compiler
    from nico.assessment_cpp_static_environment import environment_request,validate_environment
    from nico.assessment_cpp_project_static import project_static_request,validate_project_static
    from nico.assessment_cpp_clang_fallback import clang_fallback_request,validate_clang_fallback,merge_static_analysis
    native=receipt["native"]; refs=native["artifacts"]; targets=receipt["target_hashes"]
    required={"project-compilation-database","project-generated-context","project-compiler-evidence",
              "project-static-environment","project-static-evidence"}
    runtime_contract=contract["configuration"].get("schema")=="nico.cpp-configure-first-contract.v3"
    if runtime_contract:
        required.add("project-runtime-evidence")
    if not required<=set(refs):
        raise ValueError("worker_configure_first_artifact_population_invalid")
    database=_read_artifact(store,identity,refs["project-compilation-database"],"project-compilation-database")
    if hashlib.sha256(database).hexdigest()!=native["compilation_database_sha256"]:
        raise ValueError("worker_configure_first_database_mismatch")
    contexts=_database(database,None,"/work/build",nested=True,source_targets=targets)
    snapshot_raw=_read_artifact(store,identity,refs["project-generated-context"],"project-generated-context")
    snapshot=validate_project_snapshot(_json(snapshot_raw),contexts)
    compiler_raw=_read_artifact(store,identity,refs["project-compiler-evidence"],"project-compiler-evidence")
    compiler_request=project_compiler_request(database,targets,snapshot,extended_budget=True)
    compiler=validate_project_compiler(compiler_raw,compiler_request)
    env_raw=_read_artifact(store,identity,refs["project-static-environment"],"project-static-environment")
    env_request=environment_request(compiler_request,compiler_raw,contract["image_digest"])
    environment=validate_environment(env_raw,env_request)
    static_raw=_read_artifact(store,identity,refs["project-static-evidence"],"project-static-evidence")
    static_request=project_static_request(database,targets,snapshot,compiler_raw,
        extended_compiler_budget=True,environment=environment)
    primary=validate_project_static(static_raw,static_request)
    analysis=primary
    if "project-static-clang-fallback" in refs:
        fallback_raw=_read_artifact(store,identity,refs["project-static-clang-fallback"],"project-static-clang-fallback")
        fallback_request=clang_fallback_request(static_request,primary,
            extended_budget=_json(fallback_raw).get('schema')=='nico.cpp-clang-fallback-evidence.v2')
        fallback=validate_clang_fallback(fallback_raw,fallback_request,static_request)
        analysis=merge_static_analysis(primary,fallback)
    checks=[
        ("project_compiler_required",compiler["required_contexts"]),
        ("project_compiler_checked",compiler["checked_contexts"]),
        ("project_static_required",analysis["required_contexts"]),
        ("project_static_analyzed",analysis["analyzed_contexts"]),
        ("project_static_findings",analysis["findings"]),
        ("project_static_limitations",analysis["limitations"]),
        ("project_static_modeled_inputs",analysis.get("modeled_inputs") or []),
    ]
    fallback=analysis.get("clang_fallback") or {}
    checks += [("clang_fallback_required",fallback.get("required_contexts") or []),
               ("clang_fallback_analyzed",fallback.get("analyzed_contexts") or [])]
    for prefix,values in checks:
        count,digest=_population(values)
        if native[prefix+"_count"]!=count or native[prefix+"_sha256"]!=digest:
            raise ValueError("worker_configure_first_summary_mismatch")
    if (native["configured_invocations"]!=contexts["context_count"]
            or native["project_compiler_complete"] is not compiler["complete"]
            or native["project_static_complete"] is not analysis["complete"]):
        raise ValueError("worker_configure_first_summary_mismatch")
    runtime=None
    if runtime_contract:
        from nico.assessment_cpp_runtime_scope import validate_retained_runtime
        runtime_raw=_read_artifact(store,identity,refs["project-runtime-evidence"],"project-runtime-evidence")
        runtime=validate_retained_runtime(runtime_raw,targets,native["project_options"],contract["configuration"]["runtime_scope"])
        if (native.get("runtime_complete") is not runtime["summary"]["complete"]
                or native.get("runtime_plan_sha256")!=hashlib.sha256(canonical_bytes(runtime["plan"])).hexdigest()
                or native.get("runtime_summary_sha256")!=hashlib.sha256(canonical_bytes(runtime["summary"])).hexdigest()
                or native.get("runtime_duration_ms")!=runtime["duration_ms"]):
            raise ValueError("worker_configure_first_summary_mismatch")
    return {"contexts":contexts,"snapshot":snapshot,"compiler":compiler,
            "environment":environment,"analysis":analysis,"runtime":runtime}


def project_configure_first_record(record, identity, contract, receipt, reconstruction):
    native=receipt["native"]; analysis=reconstruction["analysis"]; runtime=reconstruction.get("runtime")
    # Reconstruction is source/receipt-bound even when required execution failed.
    # Runtime failure must not erase independently verified static observations.
    if runtime is not None:
        record=deepcopy(record)
        record.setdefault("cpp_build_evidence", {})["runtime_scope"]=deepcopy(runtime["summary"])
    if analysis["complete"] is not True:
        return record
    execution_complete = (native["complete_execution"] is True
        and (runtime is None or runtime["summary"]["complete"] is True))
    findings=[]
    primary_ref=native["artifacts"]["project-static-evidence"]["artifact_id"]
    fallback_ref=(native["artifacts"].get("project-static-clang-fallback") or {}).get("artifact_id")
    for value in analysis["findings"]:
        finding=deepcopy(value)
        finding.update(commit_sha=identity.revision,configuration_sha256=receipt["configuration_sha256"])
        ref=fallback_ref if finding.get("analyzer")=="clang-static-analyzer" and fallback_ref else primary_ref
        finding["evidence_reference"]="worker_artifact:"+ref
        finding["observation_id"]="cppcheck_"+_digest({k:finding.get(k) for k in
            ("rule_id","path","line","column","context_id","source_sha256","commit_sha","configuration_sha256")})
        findings.append(finding)
    output=deepcopy(record)
    output.update(execution_observed_for_this_report=True,findings=findings,
        finding_count=len(findings),canonical_findings_projected=True)
    if execution_complete:
        output.update(status="completed",completed=True,verified_complete=True,
            verified_for_this_report=True,returncode_valid=True,reason="")
    # Otherwise retain the producer's failure and incomplete/invalid-exit flags.
    # Canonical projection proves observation identity, not whole-scope success.
    output["cppcheck_source_coverage"].update(
        requested_target_count=len(receipt["target_hashes"]),
        observed_target_count=len(receipt["target_hashes"]),
        required_context_count=len(analysis["required_contexts"]),
        analyzed_context_count=len(analysis["analyzed_contexts"]),
        limitations=deepcopy(analysis["limitations"]),
        limitations_count=len(analysis["limitations"]),
        all_repository_configurations_analyzed=analysis["complete"],
        analyzer_header_coverage_verified=analysis.get("analyzer_header_coverage_verified") is True)
    if runtime is not None:
        output["cpp_build_evidence"]["runtime_scope"]=deepcopy(runtime["summary"])
    output["worker_provenance"]["canonical_projection"]={
        "compilation_database_sha256":native["compilation_database_sha256"],
        "compiler_native_sha256":reconstruction["compiler"]["native_evidence_sha256"],
        "static_native_sha256":analysis["native_evidence_sha256"],
        **({"runtime_native_sha256":runtime["native_evidence_sha256"]} if runtime is not None else {}),
        "finding_population_sha256":hashlib.sha256(canonical_bytes(findings)).hexdigest(),
    }
    return output
