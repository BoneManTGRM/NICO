"""Backend reconstruction of configure-first C/C++ native artifacts.

No assessed code executes here. Exact retained native bytes are read back from
the immutable PostgreSQL artifact store and passed through the same controller
validators that qualified the worker output.
"""
from __future__ import annotations

from nico.assessment_cpp_fileapi_membership import runtime_cmake_path
from copy import deepcopy
import base64
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
    if (not isinstance(compressed, bytes) or not 0 < len(compressed) <= MAX_COMPRESSED
            or len(compressed) != reference.get("gzip_bytes")
            or hashlib.sha256(compressed).hexdigest() != reference.get("gzip_sha256")):
        raise ValueError("worker_configure_first_artifact_digest_invalid")
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
              "project-static-environment","project-static-evidence","project-baseline-evidence"}
    from nico.assessment_cpp_configure_first_contract import (runtime_required, membership_required,
        native_commands_required, generation_required, compiler_collection_required)
    runtime_contract=runtime_required(contract['configuration'])
    membership_contract=membership_required(contract['configuration'])
    native_command_contract=native_commands_required(contract['configuration'])
    generation_contract=generation_required(contract['configuration'])
    collection_contract=compiler_collection_required(contract['configuration'])
    if collection_contract and native.get('schema') != (
            'nico.cpp-configure-first-native.v10' if runtime_contract else 'nico.cpp-configure-first-native.v9'):
        raise ValueError('worker_configure_first_collection_schema_invalid')
    if runtime_contract:
        required.add("project-runtime-evidence")
    if membership_contract:
        required.add('project-enabled-targets')
    if native_command_contract:
        required |= {'project-native-commands','project-native-commands-post-build','project-enabled-targets-post-build'}
    if generation_contract:
        required.add('project-generation-evidence')
    if not required<=set(refs):
        raise ValueError("worker_configure_first_artifact_population_invalid")
    from nico.assessment_cpp_baseline_evidence import validate_retained_baseline
    baseline_raw = _read_artifact(store, identity, refs["project-baseline-evidence"], "project-baseline-evidence")
    membership_raw=(_read_artifact(store,identity,refs['project-enabled-targets'],'project-enabled-targets')
                    if membership_contract else None)
    native_raw=(_read_artifact(store,identity,refs['project-native-commands'],'project-native-commands')
                    if native_command_contract else None)
    native_post_raw=(_read_artifact(store,identity,refs['project-native-commands-post-build'],'project-native-commands-post-build')
                    if native_command_contract else None)
    if native_command_contract:
        for key,expected in [('project-enabled-targets-post-build',membership_raw)]:
            if _read_artifact(store,identity,refs[key],key)!=expected:
                raise ValueError('worker_configure_first_native_plan_changed')
    baseline = validate_retained_baseline(
        baseline_raw, targets, contract["configuration"], contract["image_digest"], native,
        membership_raw=membership_raw,native_raw=native_raw,native_post_raw=native_post_raw,
        generation_raw=(_read_artifact(store,identity,refs['project-generation-evidence'],'project-generation-evidence')
            if generation_contract else None))
    database=_read_artifact(store,identity,refs["project-compilation-database"],"project-compilation-database")
    if hashlib.sha256(database).hexdigest()!=native["compilation_database_sha256"]:
        raise ValueError("worker_configure_first_database_mismatch")
    contexts=_database(database,None,"/work/build",nested=True,source_targets=targets)
    membership=None
    if membership_contract:
        from nico.assessment_cpp_fileapi_membership import configured_target_membership
        from nico.assessment_cpp_configuration import COMPILER_VERSION
        capsule_raw=membership_raw
        capsule=_json(capsule_raw)
        cache=base64.b64decode(_json(baseline_raw)['probe']['configuration_cache'],validate=True)
        membership=configured_target_membership(capsule_raw,database,targets,
            source_root='/work/source',build_root='/work/build',client=capsule['client'],
            cache_sha256=hashlib.sha256(cache).hexdigest(),
            compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
                compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(native_command_contract))
        if (native['enabled_target_capture_sha256']!=hashlib.sha256(capsule_raw).hexdigest()
                or native['enabled_target_membership_verified'] is not True
                or native['enabled_target_contexts_count']!=membership['configured_context_count']
                or native['enabled_target_contexts_sha256']!=_population(membership['contexts'])[1]
                or native['missing_database_contexts_count']!=len(membership['missing_database_contexts'])
                or native['missing_database_contexts_sha256']!=_population(membership['missing_database_contexts'])[1]
                or native['database_source_membership_complete'] is not membership['database_membership_complete']
                or not native_command_contract and native['context_argv_binding_verified'] is not membership['context_argv_binding_verified']):
            raise ValueError('worker_configure_first_summary_mismatch')
    plan=None
    if native_command_contract:
        from nico.assessment_cpp_native_commands import configured_native_commands, validate_native_plan_freeze
        plan=configured_native_commands(native_raw,membership_raw,database,targets,
            source_root='/work/source',build_root='/work/build',client=capsule['client'],
            cache_sha256=hashlib.sha256(cache).hexdigest(),
            compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
            compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(native_command_contract))
        freeze=validate_native_plan_freeze(native_raw,native_post_raw,membership_raw,database,targets,
            source_root='/work/source',build_root='/work/build',client=capsule['client'],
            cache_sha256=hashlib.sha256(cache).hexdigest(),
            compiler_versions={'C':COMPILER_VERSION,'CXX':COMPILER_VERSION},
            compiler_paths={'C':'/usr/local/bin/gcc','CXX':'/usr/local/bin/g++'},
                cmake_path=runtime_cmake_path(native_command_contract))
        if (native['native_command_capture_sha256']!=hashlib.sha256(native_raw).hexdigest()
            or native['native_command_post_capture_sha256']!=hashlib.sha256(native_post_raw).hexdigest()
            or native['native_command_freeze_sha256']!=hashlib.sha256(canonical_bytes(freeze)).hexdigest()
            or native['native_command_plan_sha256']!=hashlib.sha256(canonical_bytes(plan)).hexdigest()
            or native['native_contexts_count']!=len(plan['contexts'])
            or native['native_contexts_sha256']!=_population(plan['contexts'])[1]
            or native['analysis_compilation_database_sha256']!=plan['analysis_database_sha256']
            or native['analysis_invocations']!=plan['context_count']
            or native['context_argv_binding_verified'] is not True):
            raise ValueError('worker_configure_first_native_plan_mismatch')
        database=base64.b64decode(plan['analysis_database'],validate=True)
        contexts=_database(database,None,'/work/build',nested=True,source_targets=targets)
    snapshot_raw=_read_artifact(store,identity,refs["project-generated-context"],"project-generated-context")
    snapshot=validate_project_snapshot(_json(snapshot_raw),contexts)
    compiler_raw=_read_artifact(store,identity,refs["project-compiler-evidence"],"project-compiler-evidence")
    compiler_request=project_compiler_request(database,targets,snapshot,extended_budget=True)
    compiler=validate_project_compiler(compiler_raw,compiler_request)
    compiler_collection = None
    if collection_contract:
        from nico.assessment_cpp_compiler_collection import validate_project_compiler_collection, collection_summary
        compiler_collection = validate_project_compiler_collection(compiler_raw,compiler_request,snapshot)
        if native.get('project_compiler_collection') != collection_summary(compiler_collection):
            raise ValueError('worker_configure_first_compiler_collection_mismatch')
    env_raw=_read_artifact(store,identity,refs["project-static-environment"],"project-static-environment")
    env_request=environment_request(compiler_request,compiler_raw,contract["image_digest"],
        collect_completed_compiler_failures=collection_contract,snapshot=snapshot,
        physical_header_inputs=_json(env_raw).get('physical_header_inputs') is True)
    environment=validate_environment(env_raw,env_request)
    static_raw=_read_artifact(store,identity,refs["project-static-evidence"],"project-static-evidence")
    static_request=project_static_request(database,targets,snapshot,compiler_raw,
        extended_compiler_budget=True,environment=environment,header_provenance=native_command_contract,
        collect_completed_compiler_failures=collection_contract)
    primary=validate_project_static(static_raw,static_request)
    analysis=primary
    fallback_raw = None
    if "project-static-clang-fallback" in refs:
        fallback_raw=_read_artifact(store,identity,refs["project-static-clang-fallback"],"project-static-clang-fallback")
        fallback_schema=_json(fallback_raw).get('schema')
        fallback_request=clang_fallback_request(static_request,primary,
            extended_budget=native_command_contract or fallback_schema in ('nico.cpp-clang-fallback-evidence.v2',
                                               'nico.cpp-clang-fallback-evidence.v4','nico.cpp-clang-fallback-evidence.v6'),
            contention_aware=native_command_contract or fallback_schema in ('nico.cpp-clang-fallback-evidence.v4','nico.cpp-clang-fallback-evidence.v6'),
            multi_file_diagnostics=collection_contract or fallback_schema in ('nico.cpp-clang-fallback-evidence.v5','nico.cpp-clang-fallback-evidence.v6'))
        fallback=validate_clang_fallback(fallback_raw,fallback_request,static_request)
        analysis=merge_static_analysis(primary,fallback)
    static_collection = None
    if collection_contract:
        from nico.assessment_cpp_static_collection import validate_project_static_collection
        static_collection = validate_project_static_collection(static_raw,static_request,
            compiler_collection,fallback_raw=fallback_raw)
        if (static_collection['analysis'] != analysis
                or native.get('project_static_collection') != collection_summary(static_collection)):
            raise ValueError('worker_configure_first_static_collection_mismatch')
    if native_command_contract:
        from nico.assessment_cpp_header_evidence import header_summary
        if any(native[key]!=value for key,value in header_summary(analysis).items()):
            raise ValueError('worker_configure_first_header_summary_mismatch')
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
    if (native['analysis_invocations' if native_command_contract else "configured_invocations"]!=contexts["context_count"]
            or native["project_compiler_complete"] is not compiler["complete"]
            or native["project_static_complete"] is not analysis["complete"]):
        raise ValueError("worker_configure_first_summary_mismatch")
    runtime=None
    runtime_collection = None
    if runtime_contract:
        from nico.assessment_cpp_runtime_scope import validate_retained_runtime
        runtime_raw=_read_artifact(store,identity,refs["project-runtime-evidence"],"project-runtime-evidence")
        runtime=validate_retained_runtime(runtime_raw,targets,native["project_options"],contract["configuration"]["runtime_scope"])
        if (native.get("runtime_complete") is not runtime["summary"]["complete"]
                or native.get("runtime_plan_sha256")!=hashlib.sha256(canonical_bytes(runtime["plan"])).hexdigest()
                or native.get("runtime_summary_sha256")!=hashlib.sha256(canonical_bytes(runtime["summary"])).hexdigest()
                or native.get("runtime_duration_ms")!=runtime["duration_ms"]):
            raise ValueError("worker_configure_first_summary_mismatch")
        if collection_contract:
            from nico.assessment_cpp_runtime_collection import validate_runtime_collection
            runtime_collection = validate_runtime_collection(runtime_raw,targets,native['project_options'],
                contract['configuration']['runtime_scope'])
    if collection_contract:
        collection_complete = bool(compiler_collection['collection_complete']
            and static_collection['collection_complete'] and baseline['collection_complete']
            and (not runtime_contract or runtime_collection['collection_complete'])
            and native.get('independent_collection_error') is None)
        if native.get('collection_complete') is not collection_complete:
            raise ValueError('worker_configure_first_collection_summary_mismatch')
    return {"contexts":contexts,"snapshot":snapshot,"compiler":compiler,
            "environment":environment,"analysis":analysis,"runtime":runtime,"baseline":baseline,
            **({'compiler_collection':compiler_collection,'static_collection':static_collection,
                'runtime_collection':runtime_collection,'collection_complete':collection_complete}
                if collection_contract else {}),
            **({'native_command_plan':plan} if native_command_contract else {}),
            **({'generated_input_materialization':_json(baseline_raw)['probe']['generated_input_materialization']}
                if generation_contract else {}),
            **({'enabled_target_membership':membership} if membership_contract else {})}


def project_configure_first_record(record, identity, contract, receipt, reconstruction):
    native=receipt["native"]; analysis=reconstruction["analysis"]; runtime=reconstruction.get("runtime")
    # Reconstruction is source/receipt-bound even when required execution failed.
    # Runtime failure must not erase independently verified static observations.
    if runtime is not None:
        record=deepcopy(record)
        record.setdefault("cpp_build_evidence", {})["runtime_scope"]=deepcopy(runtime["summary"])
    membership=reconstruction.get('enabled_target_membership')
    plan=reconstruction.get('native_command_plan')
    generation=reconstruction.get('generated_input_materialization')
    if generation is not None:
        record=deepcopy(record)
        record.setdefault('cpp_build_evidence',{})['generated_input_materialization']={
            'schema':generation['schema'],'required_units_count':len(generation['plan']['required_units']),
            'missing_before_count':len(generation['plan']['missing_units']),
            'selected_targets_count':len(generation['plan']['selected_targets']),
            'complete':generation['complete'],'artifact_sha256':generation['artifact']['sha256'],
            'build_elapsed_ms':generation['build_elapsed_ms'],'compiler_execution_inferred':False,
            'analyzer_header_coverage_inferred':False}
    if plan is not None:
        record=deepcopy(record)
        record.setdefault('cpp_build_evidence',{})['header_evidence'] = {
            'contexts':deepcopy(analysis.get('header_context_evidence',[])),
            'population':deepcopy(analysis.get('header_population',{})),
            'unvisited_files':deepcopy(analysis.get('header_unvisited_files',[])),
            'context_evidence_complete':analysis.get('header_context_evidence_complete') is True,
            'population_complete':analysis.get('header_population_complete') is True,
            'tool_manifest_sha256':analysis.get('header_tool_manifest_sha256'),
            'line_or_branch_coverage_verified':False,'full_project_qualified':False}
    if reconstruction.get('compiler_collection') is not None:
        from nico.assessment_cpp_compiler_collection import collection_summary
        record=deepcopy(record)
        record.setdefault('cpp_build_evidence',{})['project_compiler_collection'] = collection_summary(
            reconstruction['compiler_collection'])
        record['cpp_build_evidence']['project_static_collection'] = collection_summary(reconstruction['static_collection'])
        record['cpp_build_evidence']['collection_complete'] = reconstruction['collection_complete']
        record['cpp_build_evidence']['target_compiler_complete'] = reconstruction['compiler']['complete']
        record['cpp_build_evidence']['target_static_complete'] = analysis['complete']
        record['cpp_build_evidence']['compiler_failures'] = deepcopy(reconstruction['compiler_collection']['failures'])
        record['cpp_build_evidence']['static_target_outcomes'] = deepcopy(reconstruction['static_collection']['target_outcomes'])
    if analysis["complete"] is not True and reconstruction.get('collection_complete') is not True:
        return record
    execution_complete = (native["complete_execution"] is True
        and (runtime is None or runtime["summary"]["complete"] is True)
        and (membership is None or plan is not None and plan['context_argv_binding_verified'] is True))
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
    if plan is not None:
        output.setdefault('cpp_build_evidence',{})['native_command_plan'] = {
            'schema':plan['schema'],'binding_scope':plan['binding_scope'],
            'native_capture_sha256':plan['native_capture_sha256'],
            'original_database_sha256':plan['original_database_sha256'],
            'analysis_database_sha256':plan['analysis_database_sha256'],
            'context_count':plan['context_count'],
            'original_database_context_count':plan['original_database_context_count'],
            'omitted_database_context_count':plan['omitted_database_context_count'],
            'context_membership_sha256':plan['context_membership_sha256'],
            'context_argv_binding_verified':True,
            'compiler_execution_verified':reconstruction['compiler']['complete'] is True,
            'analyzer_header_coverage_verified':analysis['analyzer_header_coverage_verified'],
            'full_project_qualified':False}
    output.update(execution_observed_for_this_report=True,findings=findings,
        finding_count=len(findings),canonical_findings_projected=True)
    if reconstruction.get("baseline") is not None:
        output.setdefault("cpp_build_evidence", {})["baseline_native_evidence"] = deepcopy(reconstruction["baseline"])
    if execution_complete and reconstruction.get("baseline", {}).get("collection_complete") is True:
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
        all_repository_configurations_analyzed=analysis["complete"] and (membership is None
            or plan is not None and plan['context_argv_binding_verified'] is True),
        analyzer_header_coverage_verified=analysis.get("analyzer_header_coverage_verified") is True)
    if runtime is not None:
        output["cpp_build_evidence"]["runtime_scope"]=deepcopy(runtime["summary"])
    if membership is not None:
        output.setdefault('cpp_build_evidence',{})['enabled_target_membership'] = {
            'schema':membership['schema'],'comparison_scope':membership['comparison_scope'],
            'configured_context_count':membership['configured_context_count'],
            'configured_contexts_sha256':_population(membership['contexts'])[1],
            'missing_database_context_count':len(membership['missing_database_contexts']),
            'missing_database_contexts_sha256':_population(membership['missing_database_contexts'])[1],
            'database_source_membership_complete':membership['database_membership_complete'],
            'context_argv_binding_verified':False,'analyzer_header_coverage_verified':False,
            'capture_sha256':membership['capture_sha256'],
            'evidence_reference':'worker_artifact:'+native['artifacts']['project-enabled-targets']['artifact_id']}
    output["worker_provenance"]["canonical_projection"]={
        "compilation_database_sha256":native["compilation_database_sha256"],
        "compiler_native_sha256":reconstruction["compiler"]["native_evidence_sha256"],
        "static_native_sha256":analysis["native_evidence_sha256"],
        **({"baseline_native_sha256":reconstruction["baseline"]["native_evidence_sha256"]}
           if reconstruction.get("baseline") is not None else {}),
        **({"runtime_native_sha256":runtime["native_evidence_sha256"]} if runtime is not None else {}),
        "finding_population_sha256":hashlib.sha256(canonical_bytes(findings)).hexdigest(),
    }
    return output
