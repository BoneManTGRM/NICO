"""Exact authored candidate-review prose; opaque evidence atoms stay unchanged."""

import re


_EXACT = {
    'These records require exact package/source, production-scope, and reachability or validity review before any item is promoted to a material finding.': 'Estos registros requieren revisar el paquete o código exacto, el alcance de producción y la accesibilidad o validez antes de promover cualquier elemento a hallazgo material.',
    'Evidence assurance remains limited until triage, but unverified volume does not by itself establish client risk or remediation scope.': 'La garantía de la evidencia permanece limitada hasta el triaje; el volumen sin verificar no establece por sí solo el riesgo del cliente ni el alcance de remediación.',
    'Evidence assurance remains limited until triage; no candidate in this group is represented as a confirmed material defect.': 'La garantía de la evidencia permanece limitada hasta el triaje; ningún candidato de este grupo se presenta como defecto material confirmado.',
    'Triage the retained candidate ledger once, promote confirmed items into individual material findings, and record evidence-backed dismissals for false positives.': 'Realizar una vez el triaje del registro conservado de candidatos, promover los elementos confirmados a hallazgos materiales individuales y registrar los descartes de falsos positivos respaldados por evidencia.',
    'Every candidate has an evidence-backed disposition.': 'Cada candidato cuenta con una disposición respaldada por evidencia.',
    'Confirmed items are promoted into individual material findings with exact source or dependency paths.': 'Los elementos confirmados se promueven a hallazgos materiales individuales con rutas exactas del código o de las dependencias.',
    'Dismissed items retain a reason and evidence reference.': 'Los elementos descartados conservan un motivo y una referencia de evidencia.',
    'Undispositioned candidates may conceal a material issue, but candidate volume is not treated as defect volume.': 'Los candidatos sin disposición pueden ocultar un problema material, pero su volumen no se trata como volumen de defectos.',
    'Unresolved assurance limitation; no unsupported monetary claim.': 'Limitación de garantía sin resolver; no se afirma ningún importe monetario sin respaldo.',
    'Bandit B608 identified string-based SQL construction at the exact assessed source location. Phase 6 retained a source-specific review rather than claiming verified exploitability.': 'Bandit B608 identificó la construcción de SQL mediante cadenas en la ubicación exacta del código evaluado. La fase 6 conservó una revisión específica del código sin afirmar que la explotación estuviera verificada.',
    'The source-specific rationale remains valid for the exact assessed code.': 'La justificación específica del código sigue siendo válida para el código exacto evaluado.',
    'The originating analyzer is rerun after any SQL construction change.': 'El analizador de origen se vuelve a ejecutar después de cualquier cambio en la construcción de SQL.',
}
_CATEGORIES = {'dependency': 'dependencias', 'secret': 'secretos', 'static': 'análisis estático', 'code': 'riesgos del código'}
_LABELS = {'Dependency': 'dependencias', 'Secret': 'secretos', 'Static-analysis': 'análisis estático', 'Code-risk': 'riesgos del código'}
_ATOM = r'[A-Za-z0-9_./@:+-]{1,500}'
_LIST = _ATOM + r'(?:, ' + _ATOM + r'){0,7}'
_LOCATIONS = _ATOM + r'(?:; ' + _ATOM + r'){0,5}'
_SAMPLES = (
    r'(?:packages=' + _LIST + r'(?:; advisories/rules=' + _LIST + r')?(?:; sample locations=' + _LOCATIONS + r')?'
    r'|advisories/rules=' + _LIST + r'(?:; sample locations=' + _LOCATIONS + r')?'
    r'|sample locations=' + _LOCATIONS + r')'
)
_FACT = re.compile(
    r'(?P<count>[0-9]+) unverified (?P<category>dependency|secret|static|code) candidate\(s\) were retained from (?P<scanner>' + _ATOM + r')\. '
    r'Candidate count is not confirmed defect count\.'
    r'(?: (?P<samples>' + _SAMPLES + r'))?'
)


def translate_retained_candidate_contract(value: str) -> str | None:
    """Return only recognized full-field translations, never a generic fallback."""
    if type(value) is not str:
        return None
    if value in _EXACT:
        return _EXACT[value]
    match = re.fullmatch(r'(Dependency|Secret|Static-analysis|Code-risk) review candidates from (' + _ATOM + r') \(([0-9]+) candidates\)', value)
    if match:
        return f'Candidatos de {_LABELS[match[1]]} para revisión de {match[2]} ({match[3]} candidatos)'
    match = _FACT.fullmatch(value)
    if match:
        # Labelled machine lists remain byte-for-byte evidence literals.
        suffix = ' ' + match['samples'] if match['samples'] else ''
        return (f"Se conservaron {match['count']} candidatos de {_CATEGORIES[match['category']]} sin verificar de {match['scanner']}. "
                'El recuento de candidatos no es un recuento de defectos confirmados.' + suffix)
    match = re.fullmatch(r'raw_candidate_count=([0-9]+); scanner=(' + _ATOM + r'); full candidate records retained in review_candidate_evidence_register', value)
    if match:
        return (f'raw_candidate_count={match[1]}; scanner={match[2]}; '
                'registros completos de candidatos conservados en review_candidate_evidence_register')
    return None
