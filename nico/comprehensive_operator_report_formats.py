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


def project_operator_report_formats(reports, *, authorized=False, approval_receipt=None):
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
        if key in parent and not (
            key == 'four_phase_program'
            and canonical.get('report_truth_schema') == 'nico.report_truth.v2'
        )
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
        if approval_receipt:
            from html import escape
            from copy import deepcopy
            from nico.comprehensive_operator_presentation_v1 import _approval_record_rows
            canonical['operator_approval_receipt'] = deepcopy(approval_receipt)
            rows = _approval_record_rows(approval_receipt, authorized=authorized)
            spanish = approval_receipt['source_identity']['report_language'] == 'es-MX'
            heading = 'Registro de aprobación del operador' if spanish else 'Operator Report Approval Record'
            replacement = '## ' + heading + '\n\n' + '\n'.join(f'- {label}: {value or ("No conservado" if spanish else "Not retained")}' for label, value in rows) + '\n'
            # Only the renderer-owned trailing manifest section carries this
            # approval template. Supplied literals elsewhere remain verbatim.
            pattern = r'(## (?:Client Artifact Manifest|Manifiesto de artefactos del cliente)\n.*?)(## (?:Operator Report Approval Record|Registro de aprobación del operador)\n.*?)(?=</pre></section>|\Z)'
            start = (text.rfind('<section data-nico-artifact-manifest="true">') if key == 'html' else
                     max(text.rfind('## ' + title + '\n') for title in ('Client Artifact Manifest', 'Manifiesto de artefactos del cliente')))
            if start >= 0:
                text = text[:start] + re.sub(pattern, lambda match: match[1] + (escape(replacement) if key == 'html' else replacement), text[start:], count=1, flags=re.S)
        reports[key] = text


def project_authorized_companion_formats(reports, *, receipt, delivery):
    """Render owned lifecycle sections from validated decisions, preserving evidence.

    Called after authority validation. PDF and canonical evidence bytes are not
    regenerated. Legacy approval projection stays frozen for receipt validation.
    """
    from nico.comprehensive_operator_approval_v1 import _cover
    from nico.comprehensive_four_phase_model_v1 import _EN, _ES, four_phase_markdown
    from nico.client_ready_html_v1 import render_client_html

    canonical = reports.get('json', {})
    if not canonical.get('human_report_export_schema'):
        return
    spanish = receipt['source_identity']['report_language'] == 'es-MX'
    badge = ('APROBADO POR OPERADOR · REVISIÓN ESPECIALIZADA SEPARADA · ENTREGA AL CLIENTE AUTORIZADA'
             if spanish else 'OPERATOR APPROVED · SPECIALIST REVIEW SEPARATE · CLIENT DELIVERY AUTHORIZED')
    markdown = reports.get('markdown', '')
    # The certificate is the renderer-owned prefix, never a source quotation.
    if markdown.startswith('NICO Comprehensive — '):
        _, separator, body = markdown.partition('\n\n---\n\n')
        if separator:
            _, certificate = _cover(receipt, spanish=spanish, corrected_presentation=True,
                                    delivery_authorization=delivery)
            markdown = certificate + separator + body

    def owned_section(headings, transform):
        nonlocal markdown
        pattern = r'(?ms)^(## (?:' + '|'.join(re.escape(h) for h in headings) + r')\n)(.*?)(?=^## |\Z)'
        markdown = re.sub(pattern, lambda m: m[1] + transform(m[2]), markdown)

    phase = four_phase_markdown(canonical, spanish=spanish)
    phase_body = phase.split('\n', 1)[1]
    # Replace only this generated section's default draft banner.
    phase_body = re.sub(r'(?m)^\*\*[^\n]+\*\*$', '**' + badge + '**', phase_body)
    owned_section((_EN, _ES), lambda _: phase_body)
    boundary = ('La aprobación del operador y la autorización de entrega están registradas para esta edición. '
                'La revisión especializada y el control de calidad siguen separados; no se ha enviado el informe. '
                'La evidencia faltante se declara y no se convierte en un resultado aprobado.\n\n' if spanish else
                'Operator approval and delivery authorization are recorded for this edition. '
                'Specialist review and quality control remain separate; no report has been sent. '
                'Missing evidence is disclosed and is never converted into a passing claim.\n\n')
    owned_section(('Decision Boundary', 'Límite de decisión'), lambda _: boundary)

    def review_instructions(text):
        # Exact checklist item within the owned gate, not a document-wide rewrite.
        return text.replace('- [ ] Approve or reject this immutable automated draft before delivery.',
            '- Operator approval and delivery authorization are recorded. Complete outstanding specialist acceptance separately.').replace(
            '- [ ] Aprobar o rechazar este borrador automatizado antes de la entrega.',
            '- La aprobación del operador y la autorización de entrega están registradas. Completar por separado la aceptación especializada pendiente.')
    owned_section(('Human Review and Acceptance Gate', 'Puerta de revisión humana y aceptación'), review_instructions)
    def legacy_checklist(text):
        return text.replace('- [ ] Approve or reject the exact immutable report package before any client delivery.',
            '- Operator approval and delivery authorization are recorded. Complete outstanding specialist acceptance separately.').replace(
            '- [ ] Aprobar o rechazar el paquete inmutable exacto del informe antes de cualquier entrega al cliente.',
            '- La aprobación del operador y la autorización de entrega están registradas. Completar por separado la aceptación especializada pendiente.')
    owned_section(('Human Review Checklist', 'Lista de verificación para revisión humana'), legacy_checklist)
    markdown = re.sub(
        r'(?m)^(### Client Human Evidence — [^\n]+\n)These observations were explicitly supplied by people and are retained ',
        r'\1This information was explicitly supplied by people and is retained ', markdown)
    reports['markdown'] = markdown
    title = ('Evaluación Técnica Integral NICO' if spanish else 'NICO Comprehensive Technical Assessment')
    reports['html'] = render_client_html(markdown, title, spanish=spanish, lifecycle_badge=badge)
