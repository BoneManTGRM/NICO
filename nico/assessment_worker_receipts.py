"""Verified remote native receipts published under the durable job's lease lock.

The initial profile is the existing prepared standalone Cppcheck pass. It makes
no compilation-database, build, header-context, runtime or qualification claim.
No profile is selected automatically or enabled by public intake parameters.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import base64
import binascii
import gzip
import hashlib
import html
import json
import os
import re
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET

from nico.assessment_worker_jobs import JobConflict, JobIdentity, JobLimits, WorkerJobs, _digest
from nico.cppcheck_native_output import NativeOutputRedactionRequired, parse_native
from nico.scanner_raw_artifact_storage_v1 import ScannerArtifactStore

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
CONFIGURATION = {"platform": "unix64", "c_standard": "c11", "cpp_standard": "c++20",
                 "max_configs": 12, "checks": ["warning", "style", "performance", "portability", "information"]}


def prepare_snapshot_scan(scan: dict, contract: dict):
    """Build a validated internal identity without dispatching external work."""
    from nico.github_actions_proof_auth_v1 import expected_release_sha
    contract = validate_contract(contract)
    if (scan.get("provider_access_mode") != "anonymous_public"
            or scan.get("provider_credential_used") is not False):
        raise ValueError("worker_source_access_unsupported")
    release = expected_release_sha()
    contract_sha = _digest(contract)
    scan = deepcopy(scan)
    requested = sorted(set([*(scan.get("tools_requested") or []), "cppcheck"]))
    binding = {key: scan[key] for key in (
        "customer_id", "project_id", "run_id", "repository", "snapshot_commit_sha")}
    if scan.get('parent_scan_id'):
        binding['parent_scan_id'] = scan['parent_scan_id']
    scan["scan_id"] = "scan_worker_" + _digest(binding | {
        "contract_sha256": contract_sha, "release_revision": release,
        "tools_requested": requested})[:40]
    identity = JobIdentity(scan["customer_id"], scan["project_id"], scan["run_id"], scan["scan_id"],
                           scan["repository"], scan["snapshot_commit_sha"], contract_sha, release)
    scan.update(worker_job_id=identity.job_id, tools_requested=requested)
    return scan, contract, identity


def enqueue_snapshot_scan(scan: dict, contract: dict, adapter):
    """Internal typed dispatch, never selected from a public request's dictionary."""
    scan, contract, identity = prepare_snapshot_scan(scan, contract)
    WorkerJobs(adapter).enqueue(identity, JobLimits(**contract["limits"]), contract=contract, scan=scan)
    from nico.assessment_worker_dispatch import dispatch_if_enabled
    return dispatch_if_enabled(adapter.get("scanner_runs", identity.scan_id), adapter)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_contract(contract: dict) -> dict:
    required = {"profile", "tool_version", "image_digest", "configuration", "targets", "limits", "max_receipt_bytes"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("worker_contract_invalid")
    if (not isinstance(contract["tool_version"], str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", contract["tool_version"])
            or not isinstance(contract["image_digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", contract["image_digest"])):
        raise ValueError("worker_contract_tool_invalid")
    targets = contract["targets"]
    configure_first = contract.get("profile") == "cpp-configure-first-v2"
    if (not isinstance(targets, dict) or len(targets) > 20000
            or (not configure_first and not targets) or (configure_first and targets)):
        raise ValueError("worker_contract_targets_invalid")
    for path, digest in targets.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or any(ord(char) < 32 or char == "\\" for char in path)
                or path.startswith("/") or ":" in path or PurePosixPath(path).as_posix() != path
                or any(part in {".", ".."} for part in path.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("worker_contract_path_or_digest_invalid")
    if configure_first:
        from nico.assessment_cpp_configure_first_contract import validate_configuration
        validate_configuration(contract['configuration'])
        from nico.assessment_cpp_configure_first_contract import runtime_required
        runtime = runtime_required(contract['configuration'])
        maximum_wall = 9000 if runtime else 2420
        if (not isinstance(contract['limits'], dict) or type(contract['limits'].get('wall_seconds')) is not int
                or not 1 <= contract['limits']['wall_seconds'] <= maximum_wall
                or contract['limits'].get('max_attempts') != 1):
            raise ValueError('worker_configure_first_budget_invalid')
    elif contract['profile'] == 'cpp-full-project-v1':
        from nico.assessment_cpp_full_project import validate_configuration
        validate_configuration(contract['configuration'], targets)
        if (not isinstance(contract['limits'], dict) or type(contract['limits'].get('wall_seconds')) is not int
                or not 1 <= contract['limits']['wall_seconds'] <= 300
                or contract['limits'].get('max_attempts') != 1):
            raise ValueError('worker_full_project_budget_invalid')
    elif contract['profile'] in {'cpp-configured-v1', 'cpp-sanitized-v1', 'cpp-runtime-cases-v1'}:
        from nico.assessment_cpp_configuration import validate_configuration
        validate_configuration(contract['configuration'], targets,
            sanitized=contract['profile'] == 'cpp-sanitized-v1',
            runtime=contract['profile'] == 'cpp-runtime-cases-v1')
    elif contract['profile'] != 'cppcheck-standalone-v1' or contract['configuration'] != CONFIGURATION:
        raise ValueError('worker_contract_tool_invalid')
    JobLimits(**contract["limits"])
    if (type(contract["max_receipt_bytes"]) is not int
            or not 1024 <= contract["max_receipt_bytes"] <= MAX_RECEIPT_BYTES
            or len(canonical_bytes(contract)) > 4 * 1024 * 1024):
        raise ValueError("worker_contract_size_invalid")
    return deepcopy(contract)


def _validate_provisioning(identity, contract, value, target_hashes=None):
    target_hashes = contract['targets'] if target_hashes is None else target_hashes
    count = len(target_hashes)
    if contract['profile'] == 'cpp-configure-first-v2':
        required={'schema','source_method','commit_sha','tree_sha','population_sha256','required_count',
            'materialized_count','source_bytes','freeze_point','excluded_count','excluded_sha256',
            'image_manifest','image_config_id'}
        repository = os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY', 'BoneManTGRM/NICO')
        image_prefix = 'ghcr.io/' + repository.lower() + '/assessment-cppcheck@sha256:'
        if (not isinstance(value,dict) or set(value)!=required or value['schema']!='nico.worker-provisioning.v2'
                or value['source_method']!='nico.github_https_tree_materialization.v2'
                or value['commit_sha']!=identity.revision or value['tree_sha']!=contract['configuration']['expected_tree_sha']
                or value['population_sha256']!=_digest(target_hashes)
                or type(value['required_count']) is not int or value['required_count']!=count
                or type(value['materialized_count']) is not int or value['materialized_count']!=count
                or type(value['source_bytes']) is not int or not 0<=value['source_bytes']<=contract['configuration']['source_byte_limit']
                or value['freeze_point']!='after_materialization_before_configuration'
                or type(value['excluded_count']) is not int or value['excluded_count']<0
                or not isinstance(value['excluded_sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['excluded_sha256']) is None
                or value['image_config_id']!=contract['image_digest']
                or not isinstance(value['image_manifest'],str)
                or re.fullmatch(re.escape(image_prefix)+r'[0-9a-f]{64}',value['image_manifest']) is None):
            raise ValueError('worker_provisioning_binding_invalid')
        return
    required = {'schema', 'source_method', 'commit_sha', 'tree_sha', 'population_sha256',
        'required_count', 'materialized_count', 'source_bytes', 'image_manifest', 'image_config_id'}
    repository = os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY', 'BoneManTGRM/NICO')
    image_prefix = 'ghcr.io/' + repository.lower() + '/assessment-cppcheck@sha256:'
    if (not isinstance(value, dict) or set(value) != required
            or value['schema'] != 'nico.worker-provisioning.v1'
            or value['source_method'] != 'nico.github_https_input_materialization.v1'
            or value['commit_sha'] != identity.revision
            or not isinstance(value['tree_sha'], str) or not re.fullmatch(r'[0-9a-f]{40}', value['tree_sha'])
            or value['population_sha256'] != _digest(target_hashes)
            or type(value['required_count']) is not int or value['required_count'] != count
            or type(value['materialized_count']) is not int or value['materialized_count'] != count
            or type(value['source_bytes']) is not int or not 0 <= value['source_bytes'] <= (
                contract['configuration']['source_byte_limit'] if contract['profile'] == 'cpp-full-project-v1'
                else 16 * 1024 * 1024)
            or value['image_config_id'] != contract['image_digest']
            or not isinstance(value['image_manifest'], str)
            or not re.fullmatch(re.escape(image_prefix) + r'[0-9a-f]{64}', value['image_manifest'])):
        raise ValueError('worker_provisioning_binding_invalid')


def validate_receipt(identity: JobIdentity, contract: dict, lease: str, worker: str, receipt: dict):
    contract = validate_contract(contract)
    if _digest(contract) != identity.contract_sha256:
        raise ValueError("worker_contract_digest_mismatch")
    required = {"schema", "identity", "lease_id", "worker_id", "image_digest", "tool_version",
                "configuration_sha256", "target_hashes", "native", "native_sha256"}
    if not isinstance(receipt, dict) or set(receipt) not in (required, required | {'provisioning'}):
        raise ValueError("worker_receipt_schema_invalid")
    if 'provisioning' in receipt:
        _validate_provisioning(identity, contract, receipt['provisioning'], receipt.get('target_hashes'))
    if receipt["schema"] not in {"nico.worker-native-receipt.v1", "nico.worker-native-receipt.v2", "nico.worker-native-receipt.v3", "nico.worker-native-receipt.v4", "nico.worker-native-receipt.v5", "nico.worker-native-receipt.v6", "nico.worker-native-receipt.v7"}:
        raise ValueError("worker_receipt_schema_invalid")
    if (receipt['schema'].endswith('.v3')) != (contract['profile'] == 'cpp-configured-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v4')) != (contract['profile'] == 'cpp-sanitized-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v5')) != (contract['profile'] == 'cpp-runtime-cases-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v6')) != (contract['profile'] == 'cpp-full-project-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v7')) != (contract['profile'] == 'cpp-configure-first-v2'):
        raise ValueError('worker_receipt_profile_mismatch')
    expected = {"identity": asdict(identity),
        "lease_id": lease, "worker_id": worker, "image_digest": contract["image_digest"],
        "tool_version": contract["tool_version"], "configuration_sha256": _digest(contract["configuration"])}
    if contract['profile'] != 'cpp-configure-first-v2':
        expected["target_hashes"] = contract["targets"]
    elif (not isinstance(receipt.get("target_hashes"),dict) or not receipt["target_hashes"]
            or any(not isinstance(k,str) or not isinstance(v,str) or re.fullmatch(r'[0-9a-f]{64}',v) is None
                   for k,v in receipt["target_hashes"].items())):
        raise ValueError("worker_receipt_binding_mismatch")
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("worker_receipt_binding_mismatch")
    encoded = canonical_bytes(receipt)
    if len(encoded) > contract["max_receipt_bytes"]:
        raise ValueError("worker_receipt_size_invalid")
    native = receipt["native"]
    if receipt['schema'].endswith('.v7'):
        if _digest(native) != receipt['native_sha256']:
            raise ValueError('worker_native_digest_or_schema_invalid')
        return _configure_first_record(identity, contract, receipt, encoded)
    if receipt['schema'].endswith(('.v3', '.v4', '.v5', '.v6')):
        if _digest(native) != receipt['native_sha256']:
            raise ValueError('worker_native_digest_or_schema_invalid')
        return _configured_record(identity, contract, receipt, encoded)
    execution_keys = {"exit_code", "timed_out", "output_truncated", "duration_ms", "invocation"}
    streams = ({"xml", "progress"} if receipt["schema"].endswith(".v1")
               else {"xml", "stdout", "stderr", "encoding"})
    if (not isinstance(native, dict) or set(native) != execution_keys | streams
            or _digest(native) != receipt["native_sha256"]):
        raise ValueError("worker_native_digest_or_schema_invalid")
    decoding_failed = False
    if receipt["schema"].endswith(".v2"):
        if native["encoding"] != "base64":
            raise ValueError("worker_native_encoding_invalid")
        decoded = {}
        from nico.scanner_tool_runners import redact_text
        for key in ("xml", "stdout", "stderr"):
            if not isinstance(native[key], str):
                raise ValueError("worker_native_encoding_invalid")
            try:
                raw_stream = base64.b64decode(native[key], validate=True)
                text = raw_stream.decode("utf-8")
            except (binascii.Error, ValueError) as error:
                if not isinstance(error, UnicodeDecodeError):
                    raise ValueError("worker_native_encoding_invalid") from None
                text = raw_stream.decode("utf-8", errors="replace")
                decoding_failed = True
            if redact_text(text) != text or redact_text(html.unescape(text)) != html.unescape(text):
                raise ValueError("worker_native_redaction_required")
            decoded[key] = text
        native = {**{key: native[key] for key in execution_keys}, "xml": decoded["xml"],
                  "progress": decoded["stdout"] + decoded["stderr"]}
    invocation = ["cppcheck", "--xml", "--enable=warning,style,performance,portability,information",
        "--check-level=normal", "--max-configs=12", "--std=c++20", "--std=c11", "--platform=unix64",
        "-j2", "--file-list=/work/cppcheck-inputs.txt", "--output-file=/work/cppcheck.xml"]
    if (not isinstance(native["xml"], str) or not isinstance(native["progress"], str)
            or type(native["exit_code"]) is not int or not -255 <= native["exit_code"] <= 255
            or type(native["timed_out"]) is not bool or type(native["output_truncated"]) is not bool
            or type(native["duration_ms"]) is not int
            or not 0 <= native["duration_ms"] <= contract["limits"]["wall_seconds"] * 1000
            or native["invocation"] != invocation):
        raise ValueError("worker_native_execution_invalid")
    from nico.scanner_tool_runners import redact_text
    if any(redact_text(native[key]) != native[key] for key in ("xml", "progress")):
        raise ValueError("worker_native_redaction_required")
    paths = sorted(contract["targets"])
    findings, limitations, observed = [], [], []
    parsed = False
    try:
        if decoding_failed:
            raise ValueError("native_output_encoding_invalid")
        findings, limitations, observed = parse_native(native["xml"], native["progress"], paths,
                                                       version=contract["tool_version"])
        parsed = True
    except NativeOutputRedactionRequired:
        raise ValueError("worker_native_redaction_required") from None
    except (ValueError, ET.ParseError):
        limitations = [{"rule_id": "native_output_invalid", "message": "Native XML was not completely parsed."}]
    complete = (parsed and native["exit_code"] == 0 and not native["timed_out"]
                and not native["output_truncated"] and observed == paths
                and not any(row["rule_id"] != "checkersReport" for row in limitations))
    status = ("completed" if complete else "timed_out" if native["timed_out"] else
              "failed" if not parsed or native["exit_code"] != 0 else "partial")
    receipt_sha = hashlib.sha256(encoded).hexdigest()
    binding = {"run_id": identity.run_id, "scan_id": identity.scan_id, "customer_id": identity.customer_id,
        "project_id": identity.project_id, "repository": identity.repository_id,
        "commit_sha": identity.revision, "scanner_name": "cppcheck"}
    for finding in findings:
        finding.update(commit_sha=identity.revision, configuration_sha256=receipt["configuration_sha256"],
                       evidence_reference="worker_receipt:" + receipt_sha)
        finding["observation_id"] = "cppcheck_" + _digest({key: finding[key] for key in (
            "rule_id", "path", "line", "column", "commit_sha", "configuration_sha256")})
    record = {**binding, "tool": "cppcheck", "category": "static", "status": status,
        "completed": complete, "verified_complete": complete, "verified_for_this_report": complete,
        "current_run": True, "execution_observed_for_this_report": True,
        "exact_commit_match": True, "snapshot_commit_sha": identity.revision,
        "output_capture_complete": parsed and not native["output_truncated"], "raw_artifact_capture_complete": True,
        "returncode_valid": native["exit_code"] == 0, "exit_code": native["exit_code"],
        "timed_out": native["timed_out"], "output_truncated": native["output_truncated"],
        "duration_seconds": native["duration_ms"] / 1000, "findings": findings, "finding_count": len(findings),
        "scanner_tool_version": contract["tool_version"], "applicable": True, "evidence_required": True,
        "reason": "" if complete else "Native target execution or parsing is incomplete; retained observations require review.",
        "worker_provenance": {"job_id": identity.job_id, "worker_id": worker,
            "release_revision": identity.release_revision, "image_digest": contract["image_digest"],
            "contract_sha256": identity.contract_sha256, "configuration_sha256": receipt["configuration_sha256"],
            "receipt_sha256": receipt_sha, "profile": contract["profile"],
            **({'provisioning': deepcopy(receipt['provisioning'])} if 'provisioning' in receipt else {})},
        "cppcheck_source_coverage": {"requested_targets": paths, "requested_target_count": len(paths),
            "observed_targets": observed, "observed_target_count": len(observed),
            "unobserved_targets": sorted(set(paths) - set(observed)), "limitations": limitations,
            "population_sha256": _digest(contract["targets"]), "configuration_aware": False,
            "header_context_verified": False, "repository_build_executed": False,
            "all_repository_configurations_analyzed": False},
        "human_review_required": True, "client_delivery_allowed": False}
    return encoded, record, binding


def _validate_configure_first_collection_summary(value, native, kind):
    """Validate a bounded projection; raw proof reconstruction remains required."""
    if value is None:
        return
    fields={'schema','collection_complete','proof_sha256','native_evidence_sha256',
            'secondary_native_evidence_sha256'}
    populations=('required_contexts','attempted_contexts','completed_contexts',
                 'failed_contexts','unparsed_contexts')
    fields |= {name+suffix for name in populations for suffix in ('_count','_sha256')}
    error='worker_configure_first_native_invalid'
    if (not isinstance(value,dict) or set(value)!=fields
            or value['schema']!='nico.cpp-project-'+kind+'-collection.v1'
            or type(value['collection_complete']) is not bool
            or any(type(value[name+'_count']) is not int or not 0<=value[name+'_count']<=20000
                   for name in populations)
            or any(not isinstance(value[name],str) or re.fullmatch(r'[0-9a-f]{64}',value[name]) is None
                   for name in ('proof_sha256','native_evidence_sha256',
                                *(p+'_sha256' for p in populations)))):
        raise ValueError(error)
    refs=native.get('artifacts') or {}
    primary=refs.get('project-'+kind+'-evidence') or {}
    secondary=refs.get('project-static-clang-fallback') or {}
    expected_secondary=secondary.get('sha256') if kind=='static' else None
    if (value['native_evidence_sha256']!=primary.get('sha256')
            or value['secondary_native_evidence_sha256']!=expected_secondary
            or expected_secondary is not None and (not isinstance(expected_secondary,str)
                or re.fullmatch(r'[0-9a-f]{64}',expected_secondary) is None)):
        raise ValueError(error)
    required=value['required_contexts_count']
    completed=value['completed_contexts_count']
    failed=value['failed_contexts_count']
    prefix='project_'+kind
    completed_prefix=prefix+('_checked' if kind=='compiler' else '_analyzed')
    if (required<1 or required!=value['attempted_contexts_count'] or required!=completed+failed
            or value['required_contexts_sha256']!=value['attempted_contexts_sha256']
            or failed!=value['unparsed_contexts_count']
            or value['failed_contexts_sha256']!=value['unparsed_contexts_sha256']
            or required!=native[prefix+'_required_count']
            or value['required_contexts_sha256']!=native[prefix+'_required_sha256']
            or completed!=native[completed_prefix+'_count']
            or value['completed_contexts_sha256']!=native[completed_prefix+'_sha256']
            or native[prefix+'_complete'] is not (failed==0)
            or not failed and value['completed_contexts_sha256']!=value['required_contexts_sha256']
            or any(value[p+'_count']==0 and value[p+'_sha256']!=_digest([]) for p in populations)):
        raise ValueError(error)


def _validate_configure_first_collection(native, *, runtime_contract=False):
    """Current envelope checks cannot themselves grant canonical completion."""
    error='worker_configure_first_native_invalid'
    if (type(native.get('collection_complete')) is not bool
            or native.get('independent_collection_error') is not None and (
                not isinstance(native['independent_collection_error'],str)
                or re.fullmatch(r'worker_configuration_probe_[a-z_]{1,80}',
                                native['independent_collection_error']) is None)):
        raise ValueError(error)
    compiler=native['project_compiler_collection']
    static=native['project_static_collection']
    _validate_configure_first_collection_summary(compiler,native,'compiler')
    _validate_configure_first_collection_summary(static,native,'static')
    if compiler is not None and static is not None:
        for population in ('required_contexts','failed_contexts','unparsed_contexts'):
            if any(compiler[population+suffix]!=static[population+suffix] for suffix in ('_count','_sha256')):
                raise ValueError(error)
    if compiler is not None and compiler['failed_contexts_count'] and (
            native['complete_execution'] is not False or native['header_context_evidence_complete'] is not False
            or native['header_population_complete'] is not False
            or native['status']!='UNPROVEN'
            or native['error']!='worker_configuration_probe_compiler_incomplete'):
        raise ValueError(error)
    if not native['collection_complete']:
        return
    required={'project-compilation-database','project-generated-context','project-compiler-evidence',
        'project-static-environment','project-static-evidence','project-baseline-evidence',
        'project-enabled-targets','project-native-commands','project-native-commands-post-build',
        'project-enabled-targets-post-build','project-generation-evidence'}
    if runtime_contract:
        required.add('project-runtime-evidence')
    if static is not None and static['failed_contexts_count']:
        required.add('project-static-clang-fallback')
    discovered=native['tests_discovered_count']
    passed=native['tests_passed_count']
    if (compiler is None or static is None
            or compiler['collection_complete'] is not True or static['collection_complete'] is not True
            or native['independent_collection_error'] is not None
            or native['error'] not in (None,'worker_configuration_probe_compiler_incomplete',
                                      'worker_configuration_probe_runtime_incomplete')
            or not required<=set(native['artifacts'])
            or any(native.get(k) is not True for k in ('compiled','tests_executed','generated_context_verified',
                'boundary_verified','cleanup_verified','scratch_capacity_verified',
                'enabled_target_membership_verified','context_argv_binding_verified','generated_input_materialization_complete'))
            or any(native.get(k) is None for k in ('native_command_capture_sha256','native_command_post_capture_sha256',
                'native_command_freeze_sha256','native_command_plan_sha256','analysis_compilation_database_sha256'))
            or native['analysis_invocations']!=compiler['required_contexts_count']
            or discovered<1 or native['tests_executed_count']!=discovered
            or native['tests_executed_sha256']!=native['tests_discovered_sha256']
            or native['tests_skipped_count']!=0 or native['tests_skipped_sha256']!=_digest([])
            or passed>discovered or native['tests_passed'] is not (passed==discovered)
            or passed==discovered and native['tests_passed_sha256']!=native['tests_discovered_sha256']):
        raise ValueError(error)


def _configure_first_record(identity, contract, receipt, encoded):
    native=receipt['native']; config=contract['configuration']
    from nico.assessment_cpp_configure_first_contract import runtime_required, membership_required, native_commands_required, generation_required, compiler_collection_required
    runtime_contract=runtime_required(config)
    membership_contract=membership_required(config)
    native_command_contract=native_commands_required(config)
    generation_contract=generation_required(config)
    collection_contract=compiler_collection_required(config)
    required={'schema','status','complete_execution','error','source_population_sha256',
        'source_count','compilation_database_sha256','configured_invocations','baseline_execution_frozen','compiled',
        'tests_executed','tests_passed','tests_discovered_count','tests_discovered_sha256','tests_executed_count',
        'tests_executed_sha256','tests_passed_count','tests_passed_sha256','tests_skipped_count','tests_skipped_sha256',
        'generated_context_verified','project_compiler_complete','project_compiler_required_count',
        'project_compiler_required_sha256','project_compiler_checked_count','project_compiler_checked_sha256',
        'project_static_complete','project_static_required_count','project_static_required_sha256',
        'project_static_analyzed_count','project_static_analyzed_sha256','project_static_findings_count',
        'project_static_findings_sha256','project_static_limitations_count','project_static_limitations_sha256',
        'project_static_modeled_inputs_count','project_static_modeled_inputs_sha256','clang_fallback_complete',
        'clang_fallback_required_count','clang_fallback_required_sha256','clang_fallback_analyzed_count',
        'clang_fallback_analyzed_sha256','boundary_verified','cleanup_verified','scratch_capacity_verified',
        'memory_peak_bytes','static_memory_peak_bytes','duration_ms','aggregate_duration_ms','artifacts',
        'canonical_findings_projected','project_option_policy','project_options','project_options_sha256'}
    if runtime_contract:
        required |= {'runtime_complete','runtime_plan_sha256','runtime_summary_sha256','runtime_duration_ms'}
    if membership_contract:
        required |= {'enabled_target_capture_sha256','enabled_target_membership_verified',
            'enabled_target_contexts_count','enabled_target_contexts_sha256',
            'missing_database_contexts_count','missing_database_contexts_sha256',
            'database_source_membership_complete','context_argv_binding_verified'}
    if native_command_contract:
        required |= {'native_command_capture_sha256','native_command_post_capture_sha256',
            'native_command_freeze_sha256','native_command_plan_sha256',
            'native_contexts_count','native_contexts_sha256','analysis_compilation_database_sha256','analysis_invocations'}
        required |= {'header_context_evidence_count','header_context_evidence_sha256','header_population_count',
            'header_population_sha256','header_unvisited_files_count','header_unvisited_files_sha256',
            'header_context_evidence_complete','header_population_complete','header_tool_manifest_sha256'}
    if generation_contract:
        required |= {'generated_input_materialization_complete','generation_evidence_sha256','generation_selected_targets_count'}
    if collection_contract:
        required |= {'project_compiler_collection','project_static_collection','collection_complete','independent_collection_error'}
    expected_schema=(('nico.cpp-configure-first-native.v8' if runtime_contract else 'nico.cpp-configure-first-native.v7')
        if generation_contract else ('nico.cpp-configure-first-native.v6' if runtime_contract else 'nico.cpp-configure-first-native.v5')
        if native_command_contract else ('nico.cpp-configure-first-native.v4' if runtime_contract else 'nico.cpp-configure-first-native.v3')
        if membership_contract else ('nico.cpp-configure-first-native.v2' if runtime_contract else 'nico.cpp-configure-first-native.v1'))
    if collection_contract:
        expected_schema='nico.cpp-configure-first-native.v10' if runtime_contract else 'nico.cpp-configure-first-native.v9'
    if (not isinstance(native,dict) or set(native)!=required or native.get('schema')!=expected_schema
            or native.get('status') not in {'UNPROVEN','BASELINE_EXECUTED'}
            or (native.get('error') is not None
                and (not isinstance(native.get('error'),str)
                     or re.fullmatch(r'worker_configuration_probe_[a-z_]+',native['error']) is None))
            or native.get('source_population_sha256')!=_digest(receipt['target_hashes'])
            or type(native.get('source_count')) is not int or native['source_count']!=len(receipt['target_hashes'])
            or native.get('canonical_findings_projected') is not False
            or native.get('project_option_policy') not in {'explicit-v1','conservative-cmake-v1'}
            or not isinstance(native.get('project_options'),dict) or len(native['project_options'])>64
            or any(not isinstance(k,str) or re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',k) is None
                or not isinstance(v,str) or re.fullmatch(r'[A-Za-z0-9_./+-]{1,120}',v) is None
                for k,v in native['project_options'].items())
            or native.get('project_options_sha256') != _digest(native['project_options'])):
        raise ValueError('worker_configure_first_native_invalid')
    if config['schema']=='nico.cpp-configure-first-contract.v1':
        if native['project_option_policy']!='explicit-v1' or native['project_options']!=config['project_options']:
            raise ValueError('worker_configure_first_native_invalid')
    else:
        from nico.assessment_cpp_cmake_policy import validate_project_options
        if (native['project_option_policy']!=config['project_option_policy']
                or validate_project_options(native['project_options'])!=native['project_options']):
            raise ValueError('worker_configure_first_native_invalid')
    for key in ('compilation_database_sha256','tests_discovered_sha256','tests_executed_sha256','tests_passed_sha256',
                'tests_skipped_sha256','project_compiler_required_sha256','project_compiler_checked_sha256',
                'project_static_required_sha256','project_static_analyzed_sha256','project_static_findings_sha256',
                'project_static_limitations_sha256','project_static_modeled_inputs_sha256',
                'clang_fallback_required_sha256','clang_fallback_analyzed_sha256'):
        if not isinstance(native.get(key),str) or re.fullmatch(r'[0-9a-f]{64}',native[key]) is None:
            raise ValueError('worker_configure_first_native_invalid')
    if runtime_contract:
        if (type(native.get('runtime_complete')) is not bool
                or type(native.get('runtime_duration_ms')) is not int or native['runtime_duration_ms']<0
                or any(not isinstance(native.get(key),str) or re.fullmatch(r'[0-9a-f]{64}',native[key]) is None
                    for key in ('runtime_plan_sha256','runtime_summary_sha256'))):
            raise ValueError('worker_configure_first_native_invalid')
    if membership_contract:
        if (any(type(native.get(k)) is not bool for k in ('enabled_target_membership_verified',
                'database_source_membership_complete','context_argv_binding_verified'))
                or not native_command_contract and native.get('context_argv_binding_verified') is not False
                or not native_command_contract and native.get('complete_execution') is not False
                or any(type(native.get(k)) is not int or native[k] < 0
                       for k in ('enabled_target_contexts_count','missing_database_contexts_count'))
                or any(not isinstance(native.get(k),str) or re.fullmatch(r'[0-9a-f]{64}',native[k]) is None
                       for k in ('enabled_target_contexts_sha256','missing_database_contexts_sha256'))):
            raise ValueError('worker_configure_first_native_invalid')
    if membership_contract:
        capture_sha=native.get('enabled_target_capture_sha256')
        ref=(native.get('artifacts') or {}).get('project-enabled-targets') or {}
        if (capture_sha != ref.get('sha256')
                or (capture_sha is not None and (not isinstance(capture_sha,str) or re.fullmatch(r'[0-9a-f]{64}',capture_sha) is None))
                or (native['enabled_target_membership_verified'] and capture_sha is None)):
            raise ValueError('worker_configure_first_native_invalid')
    if native_command_contract:
        from nico.assessment_cpp_header_evidence import HEADER_TOOL_MANIFEST_SHA256
        for key in ('header_context_evidence','header_population','header_unvisited_files'):
            if (type(native.get(key+'_count')) is not int or native[key+'_count']<0
                    or not isinstance(native.get(key+'_sha256'),str)
                    or re.fullmatch(r'[0-9a-f]{64}',native[key+'_sha256']) is None):
                raise ValueError('worker_configure_first_native_invalid')
        if (type(native.get('header_context_evidence_complete')) is not bool
                or type(native.get('header_population_complete')) is not bool
                or native.get('header_tool_manifest_sha256') not in (None,HEADER_TOOL_MANIFEST_SHA256)
                or native['header_context_evidence_complete'] and (
                    native['header_context_evidence_count']!=native['project_static_required_count']
                    or native['header_context_evidence_count']<1
                    or native['header_tool_manifest_sha256']!=HEADER_TOOL_MANIFEST_SHA256)
                or native['header_population_complete'] and (not native['header_context_evidence_complete']
                    or native['header_unvisited_files_count']!=0)
                or native['complete_execution'] and not native['header_context_evidence_complete']):
            raise ValueError('worker_configure_first_native_invalid')
        if (any(type(native.get(k)) is not int or native[k]<0 for k in ('native_contexts_count','analysis_invocations'))
            or not isinstance(native.get('native_contexts_sha256'),str)
            or re.fullmatch(r'[0-9a-f]{64}',native['native_contexts_sha256']) is None):
            raise ValueError('worker_configure_first_native_invalid')
        for key in ('native_command_capture_sha256','native_command_plan_sha256','analysis_compilation_database_sha256'):
            value=native.get(key)
            if (value is not None and (not isinstance(value,str) or re.fullmatch(r'[0-9a-f]{64}',value) is None)
                or native['context_argv_binding_verified'] and value is None):
                raise ValueError('worker_configure_first_native_invalid')
        for key in ('native_command_post_capture_sha256','native_command_freeze_sha256'):
            value=native.get(key)
            if (value is not None and (not isinstance(value,str) or re.fullmatch(r'[0-9a-f]{64}',value) is None)
                or native['complete_execution'] and value is None):
                raise ValueError('worker_configure_first_native_invalid')
        if native['native_command_post_capture_sha256']!=(native['artifacts'].get('project-native-commands-post-build') or {}).get('sha256'):
            raise ValueError('worker_configure_first_native_invalid')
        if (native['native_command_capture_sha256']!=(native['artifacts'].get('project-native-commands') or {}).get('sha256')
            or native['context_argv_binding_verified'] and (native['native_contexts_count']<1
                or native['native_contexts_count']!=native['analysis_invocations']
                or native['native_contexts_count']!=native['enabled_target_contexts_count'])
            or native['complete_execution'] and (not native['context_argv_binding_verified']
                or native['analysis_invocations']!=native['project_compiler_required_count']
                or native['analysis_invocations']!=native['project_static_required_count'])):
            raise ValueError('worker_configure_first_native_invalid')
    for key in ('source_count','configured_invocations','tests_discovered_count','tests_executed_count','tests_passed_count',
                'tests_skipped_count','project_compiler_required_count','project_compiler_checked_count',
                'project_static_required_count','project_static_analyzed_count','project_static_findings_count',
                'project_static_limitations_count','project_static_modeled_inputs_count','clang_fallback_required_count',
                'clang_fallback_analyzed_count'):
        if type(native.get(key)) is not int or native[key] < 0:
            raise ValueError('worker_configure_first_native_invalid')
    if native.get('complete_execution') is True:
        discovered=native['tests_discovered_count']
        passed=native['tests_passed_count']
        if (discovered < 1 or native['tests_executed_count'] != discovered
                or native['tests_executed_sha256'] != native['tests_discovered_sha256']
                or native['tests_skipped_count'] != 0 or passed > discovered
                or native['tests_passed'] is not (passed == discovered)
                or (passed == discovered and native['tests_passed_sha256'] != native['tests_discovered_sha256'])):
            raise ValueError('worker_configure_first_native_invalid')
    refs=native.get('artifacts')
    required_refs={'project-compilation-database','project-generated-context','project-compiler-evidence',
        'project-static-environment','project-static-evidence','project-baseline-evidence'}
    if runtime_contract:
        required_refs.add('project-runtime-evidence')
    if native_command_contract:
        required_refs |= {'project-native-commands','project-native-commands-post-build','project-enabled-targets-post-build'}
    if generation_contract:
        required_refs.add('project-generation-evidence')
        ref=(native.get('artifacts') or {}).get('project-generation-evidence')
        if (type(native['generated_input_materialization_complete']) is not bool
                or type(native['generation_selected_targets_count']) is not int
                or not 0<=native['generation_selected_targets_count']<=128
                or (ref is None and native['generation_evidence_sha256'] is not None)
                or (ref is not None and native['generation_evidence_sha256']!=ref.get('sha256'))
                or native['complete_execution'] is True and native['generated_input_materialization_complete'] is not True):
            raise ValueError('worker_configure_first_native_invalid')
    if (not isinstance(refs,dict) or 'project-compilation-database' not in refs
            or (native.get('complete_execution') is True and not required_refs <= set(refs))):
        raise ValueError('worker_configure_first_native_invalid')
    for key,value in refs.items():
        if (not isinstance(value,dict) or value.get('key')!=key or value.get('storage_backend')!='postgres'
                or not isinstance(value.get('artifact_id'),str) or not value['artifact_id'].startswith('scanartifact_')
                or not isinstance(value.get('sha256'),str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None):
            raise ValueError('worker_configure_first_native_invalid')
    if collection_contract:
        _validate_configure_first_collection(native,runtime_contract=runtime_contract)
    receipt_sha=hashlib.sha256(encoded).hexdigest()
    binding={'run_id':identity.run_id,'scan_id':identity.scan_id,'customer_id':identity.customer_id,
        'project_id':identity.project_id,'repository':identity.repository_id,'commit_sha':identity.revision,
        'scanner_name':'cppcheck'}
    execution_complete=native['complete_execution'] is True
    return encoded,{**binding,'tool':'cppcheck','category':'static','status':'partial' if execution_complete else 'failed',
        'completed':False,'verified_complete':False,'verified_for_this_report':False,'current_run':True,
        'execution_observed_for_this_report':execution_complete,'exact_commit_match':True,
        'snapshot_commit_sha':identity.revision,'output_capture_complete':True,'raw_artifact_capture_complete':True,
        'returncode_valid':execution_complete,'exit_code':0 if execution_complete else None,'timed_out':False,
        'output_truncated':False,'duration_seconds':(native.get('aggregate_duration_ms') or native.get('duration_ms') or 0)/1000,
        'findings':[],'finding_count':native['project_static_findings_count'],'scanner_tool_version':contract['tool_version'],
        'applicable':True,'evidence_required':True,
        'reason':('Configure-first execution completed; canonical findings projection from retained native artifacts is pending.'
                  if execution_complete else
                  'Enabled target inventory was collected; exact source-target compiler command mapping remains unproven. '
                  'Source membership cannot receive whole-project execution or header coverage credit.'
                  if membership_contract and native['enabled_target_membership_verified'] and not native['context_argv_binding_verified'] else
                  'Generated-file capture exceeded its bounded capacity. The retained build/test fields describe earlier execution; '
                  'compiler, static and later runtime analysis are incomplete and receive no completion credit.'
                  if native['error']=='worker_configuration_probe_snapshot_capacity_exceeded' else
                  'Configure-first execution is incomplete; retained native evidence requires repair.'),
        'worker_provenance':{'job_id':identity.job_id,'worker_id':receipt['worker_id'],
            'release_revision':identity.release_revision,'image_digest':contract['image_digest'],
            'contract_sha256':identity.contract_sha256,'configuration_sha256':receipt['configuration_sha256'],
            'receipt_sha256':receipt_sha,'profile':contract['profile'],'identity':asdict(identity),
            'provisioning':deepcopy(receipt.get('provisioning')),'native_artifacts':deepcopy(refs)},
        'cppcheck_source_coverage':{'requested_target_count':native['project_static_required_count'],
            'observed_target_count':native['project_static_analyzed_count'],
            'required_contexts_sha256':native['project_static_required_sha256'],
            'analyzed_contexts_sha256':native['project_static_analyzed_sha256'],
            'limitations_count':native['project_static_limitations_count'],
            'limitations_sha256':native['project_static_limitations_sha256'],
            'population_sha256':native['source_population_sha256'],'configuration_aware':True,
            'header_context_verified':(native['header_context_evidence_complete'] if native_command_contract else True),
            'repository_build_executed':native['compiled'],
            'all_repository_configurations_analyzed':native['project_static_complete'] and not membership_contract},
        'cpp_build_evidence':{'profile':contract['profile'],'compiled':native['compiled'],'tests_executed':native['tests_executed'],
            'tests_passed':native['tests_passed'],'configured_invocations':native['configured_invocations'],
            'tests_discovered_count':native['tests_discovered_count'],
            'tests_executed_count':native['tests_executed_count'],
            'tests_passed_count':native['tests_passed_count'],
            'tests_skipped_count':native['tests_skipped_count'],
            'configure_status':native['status'],'configure_error':native['error'],
            'compilation_database_sha256':native['compilation_database_sha256'],
            'project_option_policy':native['project_option_policy'],
            'project_options':deepcopy(native['project_options']),
            'project_options_sha256':native['project_options_sha256'],
            **({'collection_complete':False,
                'collection_claimed_complete':native['collection_complete'],
                'project_compiler_collection':deepcopy(native['project_compiler_collection']),
                'project_static_collection':deepcopy(native['project_static_collection']),
                'independent_collection_error':native['independent_collection_error']}
               if collection_contract else {}),
            **({'runtime_complete':native['runtime_complete'],
                'runtime_plan_sha256':native['runtime_plan_sha256'],
                'runtime_summary_sha256':native['runtime_summary_sha256'],
                'runtime_duration_ms':native['runtime_duration_ms']} if runtime_contract else {})},
        'canonical_findings_projected':False,'human_review_required':True,'client_delivery_allowed':False},binding


def _configured_record(identity, contract, receipt, encoded):
    if contract['profile'] == 'cpp-full-project-v1':
        from nico.assessment_cpp_full_project import validate_native
    else:
        from nico.assessment_cpp_configuration import validate_native
    result = validate_native(receipt['native'], contract)
    receipt_sha = hashlib.sha256(encoded).hexdigest()
    binding = {'run_id': identity.run_id, 'scan_id': identity.scan_id, 'customer_id': identity.customer_id,
        'project_id': identity.project_id, 'repository': identity.repository_id,
        'commit_sha': identity.revision, 'scanner_name': 'cppcheck'}
    for finding in result['findings']:
        finding.update(commit_sha=identity.revision, configuration_sha256=receipt['configuration_sha256'],
                       evidence_reference='worker_receipt:' + receipt_sha)
        finding['observation_id'] = 'cppcheck_' + _digest({key: finding[key] for key in (
            'rule_id', 'path', 'line', 'column', 'commit_sha', 'configuration_sha256',
            'translation_unit', 'unit_configuration_sha256')})
    complete = result['complete']
    record = {**binding, 'tool': 'cppcheck', 'category': 'static', 'status': result['status'],
        'completed': complete, 'verified_complete': complete, 'verified_for_this_report': complete,
        'current_run': True, 'execution_observed_for_this_report': True, 'exact_commit_match': True,
        'snapshot_commit_sha': identity.revision, 'output_capture_complete': not result['output_truncated'],
        'raw_artifact_capture_complete': True, 'returncode_valid': complete, 'exit_code': 0 if complete else None,
        'timed_out': result['status'] == 'timed_out', 'output_truncated': result['output_truncated'],
        'duration_seconds': result['duration_ms'] / 1000, 'findings': result['findings'],
        'finding_count': len(result['findings']), 'scanner_tool_version': contract['tool_version'],
        'applicable': True, 'evidence_required': True,
        'reason': '' if complete else 'Native target execution or parsing is incomplete; retained observations require review.',
        'worker_provenance': {'job_id': identity.job_id, 'worker_id': receipt['worker_id'],
            'release_revision': identity.release_revision, 'image_digest': contract['image_digest'],
            'contract_sha256': identity.contract_sha256, 'configuration_sha256': receipt['configuration_sha256'],
            'receipt_sha256': receipt_sha, 'profile': contract['profile'],
            **({'identity': asdict(identity)} if contract['profile'] == 'cpp-full-project-v1' else {}),
            **({'provisioning': deepcopy(receipt['provisioning'])} if 'provisioning' in receipt else {})},
        'cppcheck_source_coverage': result['coverage'], 'cpp_build_evidence': result['build'],
        'human_review_required': True, 'client_delivery_allowed': False}
    return encoded, record, binding


def publish_receipt(jobs: WorkerJobs, identity: JobIdentity, lease: str, worker: str, receipt: dict):
    job = jobs.get(identity)
    if job is None or not isinstance(job.get("contract"), dict):
        raise JobConflict("worker_contract_missing")
    if job["contract"].get("profile") == "cpp-configure-first-v2":
        artifacts=((receipt.get("native") or {}).get("artifacts") if isinstance(receipt,dict) else None)
        if not isinstance(artifacts,dict) or artifacts != job.get("native_artifacts",{}):
            raise JobConflict("worker_artifact_receipt_binding_mismatch")
    raw, record, binding = validate_receipt(identity, job["contract"], lease, worker, receipt)
    compressed = gzip.compress(raw, mtime=0)
    raw_sha = hashlib.sha256(raw).hexdigest()
    store = ScannerArtifactStore(jobs.adapter._connect)
    if job["contract"].get("profile") == "cpp-configure-first-v2":
        native=receipt["native"]
        required={"project-compilation-database","project-generated-context","project-compiler-evidence",
                  "project-static-environment","project-static-evidence"}
        from nico.assessment_cpp_configure_first_contract import runtime_required, membership_required, native_commands_required, generation_required
        if runtime_required(job['contract']['configuration']):
            required.add("project-runtime-evidence")
        if membership_required(job['contract']['configuration']):
            required.add('project-enabled-targets')
        if native_commands_required(job['contract']['configuration']):
            required |= {'project-native-commands','project-native-commands-post-build','project-enabled-targets-post-build'}
        if generation_required(job['contract']['configuration']):
            required.add('project-generation-evidence')
        # Complete retained populations are reconstructed before publication.
        # A bounded incomplete producer result may legitimately stop before a
        # later artifact exists; retain that truthful failure record without
        # converting it into canonical findings or completion credit.
        if required <= set(native["artifacts"]):
            from nico.assessment_cpp_configure_first_projection import reconstruct_configure_first, project_configure_first_record
            reconstruction=reconstruct_configure_first(identity,job["contract"],receipt,store)
            record=project_configure_first_record(record,identity,job["contract"],receipt,reconstruction)

    def publish(connection, _job):
        row = connection.execute("SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE",
                                 (identity.scan_id,)).fetchone()
        scan = row["payload"] if row else {}
        if any(scan.get(key) != value for key, value in {
            "worker_job_id": identity.job_id, "customer_id": identity.customer_id,
            "project_id": identity.project_id, "run_id": identity.run_id,
            "repository": identity.repository_id, "snapshot_commit_sha": identity.revision,
        }.items()):
            raise JobConflict("worker_scan_binding_mismatch")
        artifact_id = store.put_in_transaction(connection, binding, compressed, raw_sha)
        record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=raw_sha,
            raw_artifact={"storage_backend": "postgres", "artifact_id": artifact_id,
                "sha256": raw_sha, "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
                "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True})
        # The prepared C++ profile cannot erase the assessment's other requested
        # scanners. They remain explicitly unavailable until supported dispatch
        # for the full qualified contract exists.
        unsupported = [name for name in scan.get("tools_requested", []) if name != "cppcheck"]
        missing_records = [{**binding, "scanner_name": name, "tool": name, "status": "unavailable",
            "completed": False, "verified_complete": False, "verified_for_this_report": False,
            "applicability_state": "unproven", "execution_state": "unavailable",
            "reason": "The selected worker profile does not execute this requested tool.",
            "raw_artifact_retention_complete": False, "findings": [],
            "human_review_required": True, "client_delivery_allowed": False} for name in unsupported]
        # No worker-supplied canonical status, findings, score or human decision is accepted.
        scan.update(status="complete", current_stage="worker_receipt_retained", progress_percent=100,
            actual_commit_sha=identity.revision, snapshot_match=True, scanner_results=[record, *missing_records],
            unavailable_tools=unsupported,
            receipt_sha256=raw_sha, tools_run=["cppcheck"] if record["completed"] else [],
            failed_tools=["cppcheck"] if record["status"] in {"failed", "partial"} else [],
            timed_out_tools=["cppcheck"] if record["timed_out"] else [],
            finding_summary={"raw_total": int(record.get("finding_count") or 0), "material_total": 0,
                "review_required_total": int(record.get("finding_count") or 0), "approved_or_nonblocking_total": 0,
                "excluded_test_only_total": 0, "by_tool": {"cppcheck": {
                    "raw": int(record.get("finding_count") or 0), "material": 0,
                    "review_required": int(record.get("finding_count") or 0), "approved_or_nonblocking": 0,
                    "excluded_test_only": 0}}, "by_category": {}},
            human_review_required=True, client_delivery_allowed=False)
        connection.execute("UPDATE scanner_runs SET status=%s,payload=%s,updated_at=clock_timestamp() "
            "WHERE scan_id=%s AND customer_id=%s AND project_id=%s",
            (scan["status"], jobs.adapter._jsonb(scan), identity.scan_id, identity.customer_id, identity.project_id))

    return jobs.complete(identity, lease, raw_sha, worker_id=worker, publish=publish)
