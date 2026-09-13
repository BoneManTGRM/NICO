"""Lifecycle projection for newly reviewed editions; source evidence is immutable."""
import re


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
    for node in [canonical, canonical.get('assessment', {}), *[
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
                           ('delivery_status', 'authorized' if authorized else 'blocked'),
                           ('report_finality', 'operator_approved')]:
            if key in node:
                node[key] = value
    canonical['report_lifecycle'] = {
        'operator_approval': 'approved', 'delivery_authorization': 'authorized' if authorized else 'blocked',
        'specialist_review_completed_by_this_action': False, 'transmission_performed': False,
    }
    # The marked appendix is renderer-owned; arbitrary client text is untouched.
    for key in ('markdown', 'html'):
        text = reports.get(key, '')
        def section(match):
            value = re.sub(r'(Final human approval\s*:\s*(?:</strong>\s*)?)PENDING', r'\1APPROVED', match[0], flags=re.I)
            if authorized:
                value = re.sub(r'(Client-delivery authorization\s*:\s*(?:</strong>\s*)?)(BLOCKED|PENDING_AUTHORIZATION)', r'\1AUTHORIZED', value, flags=re.I)
            return value
        text = re.sub(r'<!-- NICO_PHASE2_REVIEW_TRUTH_START -->.*?<!-- NICO_PHASE2_REVIEW_TRUTH_END -->', section, text, flags=re.S)
        reports[key] = text
