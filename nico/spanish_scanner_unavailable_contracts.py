"""Translate only the scanner stage's source-authored presentation contracts."""
import re


_SUMMARY = re.compile(
    r'Scanner execution: ([0-9]+)/([0-9]+) complete\. '
    r'Candidate disposition: ([0-9]+) pending human review from ([0-9]+) raw candidates\. '
    r'(?:Confirmed material findings|Hallazgos materiales confirmados): ([0-9]+)\. Scanner completion does not equal candidate approval\.'
)

_EVIDENCE = re.compile(
    r'(?P<scanner>[A-Za-z0-9_.+-]+): execution=(?P<state>[A-Za-z0-9_-]+); '
    r'exact commit=(?P<exact>yes|no); artifact=(?P<artifact>retained|missing); '
    r'confirmed material findings=(?P<material>[0-9]+); review-required candidates=(?P<review>[0-9]+); '
    r'raw candidates=(?P<raw>[0-9]+); raw candidate payload=(?P<payload>retained|count-only|unavailable)'
)

_FAILURE_ES = {
    'timed out before complete exact-SHA evidence was retained.': 'agotó el tiempo antes de conservar evidencia completa del SHA exacto.',
    'was unavailable for the exact-run scanner execution.': 'no estuvo disponible para la ejecución del analizador vinculada a esta ejecución exacta.',
    'failed during the exact-run scanner execution.': 'falló durante la ejecución del analizador vinculada a esta ejecución exacta.',
    'did not retain a complete exact-SHA scanner record.': 'no conservó un registro completo del analizador para el SHA exacto.',
}
_FAILURE = re.compile(r'(?P<scanner>[A-Za-z0-9_.+-]+): (?P=scanner) (?P<reason>'
    + '|'.join(re.escape(reason) for reason in _FAILURE_ES) + r')')


def translate_scanner_unavailable_contract(value: str) -> str | None:
    if type(value) is not str:
        return None
    match = _FAILURE.fullmatch(value)
    if match:
        from nico.comprehensive_spanish_canonical_report_v87 import (
            _CANONICAL_PARITY_EXACT, _ES_EXTRA_EXACT, ES_EXACT,
        )
        for approved in (_CANONICAL_PARITY_EXACT, _ES_EXTRA_EXACT, ES_EXACT):
            existing = approved.get(value)
            if existing is not None:
                return existing
        return f"{match['scanner']}: {_FAILURE_ES[match['reason']]}"
    match = _EVIDENCE.fullmatch(value)
    if match:
        from nico.comprehensive_spanish_canonical_report_v87 import _SCANNER_STATUS_ES, _scanner_status_visible
        from nico.comprehensive_spanish_current_copy_worker_v98 import _STATE_ES
        raw_state = match['state']
        label = {**_SCANNER_STATUS_ES, **_STATE_ES, 'review_required': 'revisión requerida'}.get(raw_state)
        if label is None:
            label = _scanner_status_visible(raw_state)  # Preserve existing unknown-status rejection.
        state = f'{raw_state} ({label})' if '_' in raw_state else label
        exact = {'yes': 'sí', 'no': 'no'}[match['exact']]
        artifact = {'retained': 'conservado', 'missing': 'faltante'}[match['artifact']]
        payload = {'retained': 'conservada', 'count-only': 'solo recuento', 'unavailable': 'no disponible'}[match['payload']]
        return (f"{match['scanner']}: ejecución={state}; commit exacto={exact}; artefacto={artifact}; "
                f"hallazgos materiales confirmados={match['material']}; candidatos pendientes de revisión={match['review']}; "
                f"candidatos sin procesar={match['raw']}; carga de candidatos sin procesar={payload}")
    match = _SUMMARY.fullmatch(value)
    if match:
        return (f'Ejecución de los analizadores: {match[1]}/{match[2]} completada. '
                f'Disposición de candidatos: {match[3]} pendientes de revisión humana de {match[4]} candidatos sin procesar. '
                f'Hallazgos materiales confirmados: {match[5]}. '
                'La finalización del analizador no equivale a la aprobación de candidatos.')
    return None
