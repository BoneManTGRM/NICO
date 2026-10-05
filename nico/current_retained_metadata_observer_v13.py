"""Temporary body-free observer for one authorized retained report.

This module observes already validated inputs. It provides no authorization,
integrity, scanner execution, scoring, approval or delivery decision.
"""
from __future__ import annotations
import json
import hashlib
import logging
import math
import os
import re
import sys
from nico.report_delivery_timing_v1 import _ACTIVE

RUN='comprun_1279a7fb482daa07d2f69deaee14b319'
REPOSITORY='BoneManTGRM/NICO'
TARGET='b8cfbc354d4cb144a03f9159b9ac6c2c3ea83215'
OUTPUT_LIMIT=16*1024
_LOGGER=logging.getLogger('uvicorn.error')
SECTION_IDS = {'code_audit', 'dependency_health', 'dependency_library_ecosystem', 'secrets_review', 'static_analysis', 'ci_cd', 'ci_cd_analysis', 'architecture_debt', 'velocity_complexity', 'scanner_worker_evidence'}

TOOLS = {'pip-audit', 'npm-audit', 'osv-scanner', 'bandit', 'semgrep', 'eslint', 'typescript', 'gitleaks', 'trufflehog'}

STATUSES = {'complete', 'completed', 'completed_with_findings', 'failed', 'timeout', 'unavailable', 'partial', 'not_applicable', 'verified', 'review_limited', 'review_required', 'blocked', 'unproven', 'pending', 'unknown'}

REASONS = {'scanner_verification_not_proven', 'complete_artifact_capture_not_proven', 'scanner_execution_receipt_invalid', 'scanner_execution_receipt_missing', 'scanner_tool_unavailable', 'project_preparation_unavailable'}

DEFICITS = REASONS | {'current_run_not_proven', 'execution_not_observed_for_this_report', 'exact_commit_match_not_proven', 'artifact_hash_missing', 'full_git_history_not_verified', 'status=unavailable', 'status=partial', 'status=failed', 'status=timeout'}

FIXED_REASONS = {'Project dependencies were not prepared.': 'project_dependencies_not_prepared', 'typescript requires NICO_ALLOW_PROJECT_COMMANDS=true because it may execute project-local commands.': 'project_command_policy_disabled', 'Project-tool preparation requires NICO_ALLOW_PROJECT_COMMANDS=true.': 'project_preparation_policy_disabled', 'package.json not found in a supported Node project.': 'supported_node_manifest_missing', 'npm is not installed in the worker image.': 'npm_tool_unavailable', 'npm ci did not establish node_modules': 'project_dependencies_not_established', 'No complete retained exact-SHA scanner artifact was available.': 'retained_artifact_incomplete', 'No retained scanner execution record was available.': 'retained_execution_record_missing', 'The retained scanner manifest records this tool as unavailable.': 'retained_manifest_unavailable'}

VERSIONS = {'nico.comprehensive_score_truth.v1', 'nico.comprehensive_evidence_quality.v1', 'nico.comprehensive_premium_synthesis.v6', 'nico.comprehensive_express_quality.v7', 'nico.comprehensive-native-providers.v3', 'nico.comprehensive-native-providers.v4', 'nico.comprehensive-native-providers.v5', 'nico.decision_grade_scanner_executions.v1'}

NUMBER_FIELDS = {'technical_score', 'canonical_technical_score', 'evidence_adjusted_score', 'canonical_evidence_adjusted_score', 'score', 'source_score', 'presented_score', 'evidence_readiness_score', 'weight', 'weight_percent', 'weighted_contribution', 'assurance_factor', 'candidate_volume_penalty', 'missing_raw_payload_penalty', 'incomplete_analyzer_penalty', 'assurance_penalty', 'canonical_finding_count', 'analyzer_execution_coverage', 'count', 'raw', 'confirmed', 'review_required', 'material', 'count_only'}

BOOLEAN_FIELDS = {'included', 'exclude_from_maturity', 'candidate_volume_affects_technical_score', 'candidate_volume_affects_evidence_adjusted_score', 'unverified_candidate_volume_affects_technical_score', 'unverified_candidate_volume_affects_assurance_only', 'calculated_once_after_control_specific_assurance', 'immutable_for_downstream_report_formats'}

class Refusal(Exception):

    def __init__(self, code):
        self.code = code

def require(value, code):
    if not value:
        raise Refusal(code)

def scalar(value):
    if type(value) in (int, float) and abs(value) <= 10 ** 12 and math.isfinite(value):
        return value
    return None

def boolean(value):
    return value if type(value) is bool else None

def enum(value, allowed):
    return value if type(value) is str and len(value) <= 128 and value in allowed else None

def numeric_projection(value):
    value = value if isinstance(value, dict) else {}
    out = {field: scalar(value.get(field)) for field in sorted(NUMBER_FIELDS) if field in value}
    out.update({field: boolean(value.get(field)) for field in sorted(BOOLEAN_FIELDS) if field in value})
    if 'version' in value:
        out['version'] = enum(value.get('version'), VERSIONS)
    return out

def project_assessment(assessment):
    if not isinstance(assessment, dict):
        assessment = {}
    out = {'scores': {name: scalar(assessment.get(name)) for name in ('technical_score', 'evidence_adjusted_score', 'canonical_evidence_adjusted_score')}, 'maturity': numeric_projection(assessment.get('maturity_signal')), 'score_contract': numeric_projection(assessment.get('score_contract')), 'evidence_coverage': numeric_projection(assessment.get('evidence_coverage')), 'canonical_evidence_score_contract': numeric_projection(assessment.get('canonical_evidence_score_contract')), 'sections': [], 'scoring_weights': [], 'incomplete_analyzers': None}
    for field in ('sections', 'scoring_weights'):
        rows = assessment.get(field)
        if not isinstance(rows, list):
            continue
        require(len(rows) <= 48, 'projection_population_exceeded')
        for row in rows:
            if not isinstance(row, dict):
                continue
            sid = enum(row.get('section_id') or row.get('id'), SECTION_IDS)
            if sid is None:
                continue
            item = numeric_projection(row)
            item['section_id'] = sid
            item['score_value'] = scalar(row.get('score_value'))
            item['assurance_status'] = enum(row.get('assurance_status'), STATUSES)
            out[field].append(item)
    incomplete = (assessment.get('score_contract') or {}).get('incomplete_analyzers')
    if isinstance(incomplete, list):
        require(len(incomplete) <= 9, 'projection_population_exceeded')
        out['incomplete_analyzers'] = [enum(v, TOOLS) for v in incomplete]
    return out

def digest(value):
    return value if type(value) is str and len(value) == 64 and re.fullmatch('[0-9a-f]{64}', value) else None

def receipt_projection(value):
    # Read only fixed top-level retained claims. Do not traverse, serialize or
    # rehash argv/configuration/raw output; this observer grants no receipt proof.
    return {'status': 'retained_fields_not_reverified',
            'declared_receipt_sha256': digest(value.get('receipt_sha256')),
            'argument_count': scalar(value.get('argument_count')),
            'argv_capture_status': enum(value.get('argv_capture_status'), {'complete_redacted', 'partial_redacted', 'unknown'}),
            'input_identity_status': enum(value.get('input_identity_status'), {'stable_observed_inputs', 'changed_unavailable_or_not_observed', 'unknown'}),
            'full_configuration_verified': False, 'summary_only_not_reverified': True,
            'raw_receipt_integrity_reverified': False}

def closed_reason_codes(row):
    selected = set()
    for field in ('reason_code', 'reason', 'failure_reason', 'failure_or_unavailable_reason'):
        value = row.get(field)
        if type(value) is str and len(value) <= 4000:
            parts = [part.strip() for part in re.split('[,;]', value)]
            if parts and all((part in DEFICITS for part in parts)):
                selected.update(parts)
    values = row.get('verification_deficits')
    if isinstance(values, list) and len(values) <= 32:
        selected.update((value for value in values if type(value) is str and value in DEFICITS))
    return sorted(selected)

def reason_metadata(row):
    value = next((row.get(field) for field in ('failure_reason', 'failure_or_unavailable_reason', 'reason') if type(row.get(field)) is str and row.get(field)), None)
    if type(value) is not str or len(value) > 4000:
        return {'retained_reason_sha256': None, 'source_literal_classification': None, 'classification_is_retained_claim_not_execution_proof': True}
    classification = FIXED_REASONS.get(value)
    if classification is None and re.fullmatch('[A-Za-z0-9_.\\-/]{1,512}/tsconfig\\.json or the exact local TypeScript compiler is missing\\.', value):
        classification = 'project_configuration_or_exact_local_compiler_missing'
    if classification is None and re.fullmatch('[A-Za-z0-9_.\\-/]{1,512}/package-lock\\.json is required for deterministic project-tool preparation\\.', value):
        classification = 'deterministic_project_lockfile_missing'
    return {'retained_reason_sha256': hashlib.sha256(value.encode()).hexdigest(), 'source_literal_classification': classification, 'classification_is_retained_claim_not_execution_proof': True}

def typescript_projection(record, package):
    stages = record.get('stage_results') or {}
    scored = stages.get('evidence_reconciliation_and_scoring') or {}
    scanner_stage = stages.get('dependency_security_static_analysis') or {}
    triage = stages.get('deep_scanner_triage') or {}
    containers = [('score_assessment', scored.get('assessment') or {}), ('scoring', scored), ('dependency', scanner_stage), ('triage', triage), ('triage_scanner', triage.get('scanner_triage') or {}), ('retained_canonical', package['json']), ('retained_assessment', package['json'].get('assessment') or {})]
    for field in ('scanner',):
        if isinstance(scanner_stage.get(field), dict):
            containers.append(('dependency_' + field, scanner_stage[field]))
    observations = []
    for origin, container in containers:
        if not isinstance(container, dict):
            continue
        for population in ('scanner_results', 'scanner_execution_records', 'requested_scanner_records'):
            rows = container.get(population)
            if not isinstance(rows, list):
                continue
            require(len(rows) <= 32, 'projection_population_exceeded')
            for row in rows:
                if not isinstance(row, dict) or (row.get('tool') or row.get('scanner_name') or row.get('scanner')) != 'typescript':
                    continue
                require(len(observations) < 12, 'typescript_projection_population_exceeded')
                result = {'origin': origin, 'population': population, 'tool': 'typescript', 'status': enum(row.get('status'), STATUSES), 'reason_codes': closed_reason_codes(row)}
                result.update(reason_metadata(row))
                for key in ('returncode', 'exit_code', 'stdout_bytes', 'stderr_bytes', 'findings_count', 'finding_count', 'raw_artifact_bytes', 'scanner_error_count'):
                    result[key] = scalar(row.get(key))
                for key in ('returncode_valid', 'timed_out', 'output_truncated', 'output_capture_complete', 'raw_artifact_capture_complete', 'raw_artifact_retention_complete', 'source_checkout_verified', 'exact_commit_match', 'execution_observed_for_this_report', 'completed', 'verified', 'verified_complete', 'current_run'):
                    result[key] = boolean(row.get(key))
                observed = result.pop('execution_observed_for_this_report')
                result['retained_execution_observed_claim'] = observed
                exit_value = row.get('exit_code', row.get('returncode'))
                result['execution_observed_by_inventory_rule'] = False if row.get('status') in {'unavailable', 'blocked', 'not_applicable'} and type(exit_value) is not int else observed
                result['raw_artifact_sha256'] = digest(row.get('raw_artifact_sha256'))
                result['retained_record_artifact_sha256'] = digest(row.get('artifact_hash'))
                expected = record.get('identity') or {}
                result['binding_matches'] = {field: row[field] == expected.get(field) if field in row else None for field in ('run_id', 'customer_id', 'project_id', 'repository')}
                result['target_binding_matches'] = {field: row[field] == expected.get('commit_sha') if field in row else None for field in ('commit_sha', 'snapshot_commit_sha', 'target_commit_sha')}
                version = row.get('scanner_tool_version')
                result['tool_version_components'] = [int(v) for v in version.lstrip('v').removeprefix('Version ').split('.')] if type(version) is str and re.fullmatch('(?:v|Version )?\\d{1,4}(?:\\.\\d{1,4}){1,3}', version) else None
                provenance = row.get('execution_provenance') or {}
                summary = provenance.get('execution_receipt') if isinstance(provenance, dict) else None
                if isinstance(row.get('scanner_execution_receipt'), dict):
                    result['execution_receipt'] = receipt_projection(row['scanner_execution_receipt'])
                elif isinstance(summary, dict):
                    result['execution_receipt'] = {'status': enum(summary.get('status'), {'not_recorded', 'integrity_mismatch', 'retained_receipt_integrity_verified'}), 'receipt_sha256': digest(summary.get('receipt_sha256')), 'argument_count': scalar(summary.get('argument_count')), 'input_identity_status': enum(summary.get('input_identity_status'), {'stable_observed_inputs', 'changed_unavailable_or_not_observed', 'unknown'}), 'full_configuration_verified': boolean(summary.get('full_configuration_verified')), 'summary_only_not_reverified': True}
                else:
                    result['execution_receipt'] = None
                findings = row.get('findings')
                if isinstance(findings, list) and row.get('raw_findings_embedded') is not False:
                    require(len(findings) <= 100000, 'typescript_finding_population_exceeded')
                    codes = {}
                    for finding in findings:
                        code = finding.get('code') if isinstance(finding, dict) else None
                        if type(code) is str and re.fullmatch('TS[1-9][0-9]{2,4}', code):
                            number = int(code[2:])
                            codes[number] = codes.get(number, 0) + 1
                    require(len(codes) <= 32, 'typescript_code_population_exceeded')
                    result['diagnostic_code_counts'] = [{'code_number': code, 'count': codes[code]} for code in sorted(codes)]
                    result['retained_findings_population'] = len(findings)
                    result['raw_findings_embedded'] = boolean(row.get('raw_findings_embedded'))
                else:
                    result['diagnostic_code_counts'] = None
                observations.append(result)
    return {'observation_count': len(observations), 'observations': observations, 'separate_scanner_store_read': False, 'raw_artifact_or_target_execution_verified': False}


def observe_validated_retained_pdf(record, package, report_language, response):
    """Observe once after the normal builder returns a validated frozen PDF.

    The caller owns all original checks and returns its original response.
    Nothing here retains a tree, PDF, tenant/session or authorization decision.
    """
    state=_ACTIVE.get()
    if (type(state) is not dict or state.get('run_id')!=RUN
            or state.get('report_language')!=report_language
            or report_language not in {'en','es-MX'}
            or state.get('closeout_numeric_observation_attempted')):
        return
    if type(record) is not dict or type(package) is not dict:
        return
    identity=record.get('identity')
    canonical=package.get('json')
    if type(identity) is not dict or type(canonical) is not dict:
        return
    canonical_identity=canonical.get('identity')
    if type(canonical_identity) is not dict:
        return
    expected={'run_id':RUN,'repository':REPOSITORY,'commit_sha':TARGET}
    if any(identity.get(k)!=v or canonical_identity.get(k)!=v for k,v in expected.items()):
        return
    if any(type(identity.get(k)) is not str or not identity[k]
           or identity[k]!=canonical_identity.get(k) for k in ('customer_id','project_id')):
        return
    if (record.get('terminal') is not True or getattr(response,'status_code',None)!=200
            or response.headers.get('X-NICO-Frozen-Source-Artifact')!='true'
            or response.headers.get('X-NICO-Run-ID')!=RUN
            or response.headers.get('X-NICO-Commit-SHA')!=TARGET
            or response.headers.get('X-NICO-Report-Language')!=report_language
            or response.headers.get('X-NICO-Assessment-Rerun')!='false'
            or response.headers.get('content-type','').split(';',1)[0]!='application/pdf'):
        return
    truth=digest(package.get('canonical_truth_sha256'))
    pdf=digest(package.get('pdf_sha256'))
    if (truth is None or pdf is None
            or response.headers.get('X-NICO-Canonical-Truth-SHA256')!=truth
            or response.headers.get('X-NICO-PDF-SHA256')!=pdf):
        return
    state['closeout_numeric_observation_attempted']=True
    try:
        stages=record.get('stage_results')
        require(type(stages) is dict,'stage_population_invalid')
        stage=stages.get('evidence_reconciliation_and_scoring')
        stage=stage if type(stage) is dict else {}
        scoring=project_assessment(stage.get('assessment'))
        retained=project_assessment(canonical.get('assessment'))
        projection={'scoring_stage':scoring,'retained_report':retained,
                    'typed_assessment_agreement':{
                        k:scoring['scores'][k]==retained['scores'][k]
                        if scoring['scores'][k] is not None and retained['scores'][k] is not None else None
                        for k in scoring['scores']},
                    'typescript':typescript_projection(record,package)}
        body={'schema':'nico.current-retained-metadata.v13','outcome':'observed_validated_frozen_pdf',
              'scope':'exact1279_validated_runtime_numeric_metadata_only',
              'run_id':RUN,'repository':REPOSITORY,'target_commit':TARGET,
              'report_language':report_language,'revision':scalar(record.get('revision')),
              'canonical_truth_sha256':truth,'pdf_sha256':pdf,
              'python_version_components':list(sys.version_info[:3]),
              'projection':projection,
              'raw_artifact_or_native_execution_verified':False,
              'http_transfer_or_browser_completion_inferred':False,
              'report_or_human_approval_inferred':False}
        release=os.environ.get('RAILWAY_GIT_COMMIT_SHA')
        deployment=os.environ.get('RAILWAY_DEPLOYMENT_ID')
        body['reader_release']=release if type(release) is str and re.fullmatch(r'[0-9a-f]{40}',release) else None
        body['reader_deployment']=deployment if type(deployment) is str and re.fullmatch(r'[0-9a-f-]{36}',deployment) else None
        encoded=json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False)
        require(len(encoded.encode('utf-8'))<=OUTPUT_LIMIT,'numeric_projection_byte_limit')
    except BaseException:
        # Observation failure is explicit and never alters the real report or
        # conceals a failure from its original validators, which precede this call.
        encoded=json.dumps({'schema':'nico.current-retained-metadata.v13',
                            'outcome':'observation_unavailable','run_id':RUN,
                            'reason_code':'bounded_numeric_projection_unavailable'},
                           separators=(',',':'),sort_keys=True)
    try:
        _LOGGER.info('NICO_CURRENT_RETAINED_METADATA=%s',encoded)
    except Exception:
        pass
