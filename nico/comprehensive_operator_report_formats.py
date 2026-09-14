"""Lifecycle projection for newly reviewed editions; source evidence is immutable."""
import re


def _current_prose(value, *, authorized, current_truth=False):
    from nico.comprehensive_operator_presentation_v1 import lifecycle_text, delivery_lifecycle_text
    # Literal spans are escaped by the evidence renderer. Keep their full bytes,
    # even when a supplier quotes a report-owned lifecycle phrase.
    pieces = re.split(r'(<span data-nico-client-literal="true">.*?</span>)', value, flags=re.S)
    for index in range(0, len(pieces), 2):
        text = lifecycle_text(pieces[index])
        if authorized:
            text = delivery_lifecycle_text(text)
            text = text.replace('CLIENT DELIVERY NOT AUTHORIZED', 'CLIENT DELIVERY AUTHORIZED')
        if current_truth:
            text = text.replace('BLOCKED - AUTHORIZED HUMAN APPROVAL REQUIRED',
                                'AUTHORIZED' if authorized else 'APPROVED - DELIVERY NOT AUTHORIZED')
            text = text.replace('BLOQUEADA - REQUIERE APROBACIÓN HUMANA AUTORIZADA',
                                'AUTORIZADA' if authorized else 'APROBADA - ENTREGA NO AUTORIZADA')
        pieces[index] = text
    return ''.join(pieces)


def project_operator_report_formats(reports, *, authorized=False):
    canonical = reports.get('json', {})
    if not canonical.get('human_report_export_schema'):
        return
    # Retain the source's truth as explicitly historical; update only report-owned
    # lifecycle nodes, never scanner findings or supplied human payloads.
    canonical['reviewed_source_lifecycle'] = {
        'historical': True, 'operator_approval_status': 'pending',
        'client_delivery_allowed': False,
    }
    for node in [canonical, canonical.get('assessment', {}), canonical.get('lifecycle', {}), *[
        canonical.get(key, {}) for key in ('executive_brief', 'client_evidence_summary',
        'scoring_explanation', 'human_review_section', 'approval_package')
    ]]:
        if not isinstance(node, dict):
            continue
        truth = node.get('human_review_truth')
        if isinstance(truth, dict):
            truth['final_human_approval_status'] = 'approved'
            truth['client_delivery_authorization_status'] = 'authorized' if authorized else 'blocked'
            truth['client_delivery_allowed'] = authorized
        node['operator_approval_status'] = 'approved'
        node['client_delivery_allowed'] = authorized
        for key, value in [('approval_status', 'operator_approved'),
                           ('approval_state', 'OPERATOR-APPROVED'),
                           ('client_delivery_status', 'authorized' if authorized else 'blocked'),
                           ('delivery_status', 'authorized' if authorized else 'blocked'),
                           ('report_finality', 'operator_approved')]:
            if key in node:
                node[key] = value
    canonical['reviewed_source_lifecycle']['historical_contract_paths'] = [
        '/' + prefix + key
        for prefix, parent in [('', canonical), ('assessment/', canonical.get('assessment', {}))]
        for key in ('finding_population', 'client_readiness_contract', 'post_readiness_report_contract_truth',
                    'four_phase_program', 'v2_pipeline_contract', 'v2_prepublication_contract',
                    'post_readiness_maturity_truth', 'approval', 'artifact_manifest')
        if key in parent
    ]
    if canonical.get('report_truth_schema') == 'nico.report_truth.v2':
        for parent in (canonical, canonical.get('assessment', {})):
            program = parent.get('four_phase_program', {})
            for phase in program.get('phases', []):
                if phase.get('id') == 'approval_and_client_delivery':
                    phase['status'] = 'authorized' if authorized else 'approved_pending_delivery_authorization'
            if program:
                program['operator_approval_completed'] = True
                program['client_delivery_allowed'] = authorized
    canonical['report_lifecycle'] = {
        'operator_approval': 'approved', 'delivery_authorization': 'authorized' if authorized else 'blocked',
        'specialist_review_completed_by_this_action': False, 'transmission_performed': False,
    }
    # The marked appendix is renderer-owned; arbitrary client text is untouched.
    for key in ('markdown', 'html'):
        text = _current_prose(reports.get(key, ''), authorized=authorized, current_truth=canonical.get('report_truth_schema') == 'nico.report_truth.v2')
        def section(match):
            value = re.sub(r'(Final human approval\s*:\s*(?:</strong>\s*)?)PENDING', r'\1APPROVED', match[0], flags=re.I)
            if authorized:
                value = re.sub(r'(Client-delivery authorization\s*:\s*(?:</strong>\s*)?)(BLOCKED|PENDING_AUTHORIZATION)', r'\1AUTHORIZED', value, flags=re.I)
            return value
        text = re.sub(r'<!-- NICO_PHASE2_REVIEW_TRUTH_START -->.*?<!-- NICO_PHASE2_REVIEW_TRUTH_END -->', section, text, flags=re.S)
        reports[key] = text
