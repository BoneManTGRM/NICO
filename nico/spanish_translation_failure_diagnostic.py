"""Classify missing translations without emitting report text or identifiers."""

import ast
from functools import lru_cache
from pathlib import Path


_PREFIX = 'missing Spanish presentation translation for '
_FIELDS = frozenset((
    'acceptance_criteria', 'business_impact', 'can_conclude', 'cannot_conclude',
    'decision', 'description', 'evidence', 'evidence_to_resolve', 'exit_criteria',
    'fact', 'findings', 'focus', 'impact', 'interpretation', 'label', 'limitations',
    'objective', 'recommendation', 'recommended_correction', 'required_input',
    'rollback', 'score_rationale', 'summary', 'title', 'unavailable',
    'unavailable_data_notes', 'verification', 'why_it_matters',
))
# Fixed source-owned producers only. Never resolve a path supplied by a report.
_PRODUCERS = (
    'comprehensive_native_providers', 'comprehensive_native_providers_v4',
    'comprehensive_assessment_hardening_v1', 'comprehensive_core_report_readiness_v1',
    'comprehensive_decision_grade_report_v5', 'comprehensive_decision_grade_model_v5',
    'comprehensive_decision_grade_roadmap_v5', 'comprehensive_decision_grade_pdf_v5',
    'comprehensive_report_package', 'comprehensive_report_content_render_v66',
    'comprehensive_decision_content_restoration_v66', 'comprehensive_decision_content_restoration_v67',
    'comprehensive_client_review_companion_v5', 'comprehensive_current_report_truth_parity_v1',
    'comprehensive_executive_risk_truth_v7', 'comprehensive_finding_roadmap_v1',
    'comprehensive_final_report_execution_v1', 'comprehensive_canonical_report_source_v1',
    'client_finding_remediation_register_v5', 'client_report_completion_v2',
    'phase5_visible_outcome_appendix_v1', 'phase6_canonical_truth_v2',
    'phase6_sql_dispositions_v1', 'phase9_comprehensive_report_integration_v1',
    'phase15_production_integration_v1', 'phase16_client_delivery_verification_v1',
    'phase17_canonical_artifact_rebuild_v1', 'v2_premium_report_renderer',
    'v2_pipeline_adapter', 'source_function_conformance_report_v1',
    'scanner_evidence_pipeline_v1', 'comprehensive_authoritative_scanner_truth_v62',
    'comprehensive_client_readiness_v59', 'comprehensive_scanner_stage_wording_v1',
    'snapshot_repository_evidence', 'scanner_worker',
    'comprehensive_retained_scanner_evidence_v1', 'comprehensive_requested_scanner_projection_v62',
)
_SCANNERS = frozenset(('bandit', 'semgrep', 'eslint', 'typescript', 'gitleaks',
                      'trufflehog', 'osv-scanner', 'pip-audit', 'npm-audit', 'lizard'))
_MAX_SOURCE_BYTES = 1_000_000
_MAX_NODES = 100_000


def _source_locations(source: str):
    """Separate static literals from tentative long f-string prefixes/fragments."""
    tree = ast.parse(source)
    pending = [tree]
    visited = 0
    while pending:
        node = pending.pop()
        visited += 1
        if visited > _MAX_NODES:
            raise ValueError('source_catalog_budget')
        if isinstance(node, ast.JoinedStr):
            if node.values and isinstance(node.values[0], ast.Constant):
                prefix = node.values[0].value
                if type(prefix) is str:
                    prefix = ' '.join(prefix[:180].split())
                    if len(prefix) >= 32:
                        yield 'dynamic', prefix, node.lineno
            for part in node.values:
                visited += 1
                if visited > _MAX_NODES:
                    raise ValueError('source_catalog_budget')
                if isinstance(part, ast.Constant) and type(part.value) is str:
                    fragment = ' '.join(part.value[:180].split())
                    if len(fragment) >= 32:
                        yield 'fragment', fragment, node.lineno
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, ast.Constant) and type(node.value) is str and node.value:
            # v87 retains at most 180 characters; the v2 boundary collapses whitespace.
            snippet = ' '.join(node.value[:180].split())
            if snippet:
                yield 'static', snippet, node.lineno
        pending.extend(ast.iter_child_nodes(node))


@lru_cache(maxsize=1)
def _source_catalog():
    catalog = {'static': {}, 'dynamic': {}, 'fragment': {}}
    root = Path(__file__).resolve().parent
    for module in _PRODUCERS:
        try:
            with (root / (module + '.py')).open('rb') as stream:
                raw = stream.read(_MAX_SOURCE_BYTES + 1)
            if len(raw) > _MAX_SOURCE_BYTES:
                continue
            locations = list(_source_locations(raw.decode('utf-8')))
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
            continue
        for kind, snippet, line in locations:
            catalog[kind].setdefault(snippet, set()).add((module, line))
    return catalog


def spanish_translation_failure_diagnostic(error):
    result = {'field': 'other', 'source_match': 'none'}
    if type(error) is not str or len(error) > 300 or not error.startswith(_PREFIX):
        return result
    field, separator, snippet = error[len(_PREFIX):].partition(': ')
    if not separator or field not in _FIELDS or not snippet or len(snippet) > 180:
        return result
    result['field'] = field
    catalog = _source_catalog()
    matches = set(catalog['static'].get(snippet, set()))
    scanner, scanner_separator, detail = snippet.partition(': ')
    detail_matches = set()
    if scanner_separator and scanner.casefold() in _SCANNERS:
        detail_matches = catalog['static'].get(detail, set())
        matches.update(detail_matches)
    if len(matches) == 1:
        module, line = next(iter(matches))
        result.update(source_match='unique_static_literal', source_module=module, source_line=line)
        if detail_matches:
            result['source_scope'] = 'scanner_detail'
    elif matches:
        result['source_match'] = 'ambiguous_static_literal'
    else:
        candidates = set()
        for prefix, locations in catalog['dynamic'].items():
            if snippet.startswith(prefix):
                candidates.update(locations)
        if len(candidates) == 1:
            module, line = next(iter(candidates))
            result.update(source_match='unique_dynamic_prefix_candidate', source_module=module, source_line=line)
        elif candidates:
            result['source_match'] = 'ambiguous_dynamic_prefix_candidate'
        else:
            fragments = set()
            for fragment, locations in catalog.get('fragment', {}).items():
                if fragment in snippet:
                    fragments.update(locations)
            if len(fragments) == 1:
                module, line = next(iter(fragments))
                result.update(source_match='unique_dynamic_fragment_candidate', source_module=module, source_line=line)
            elif fragments:
                result['source_match'] = 'ambiguous_dynamic_fragment_candidate'
    return result
