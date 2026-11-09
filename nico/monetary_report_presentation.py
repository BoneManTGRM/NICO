"""Presentation of retained estimates; never creates amounts or approval state."""
import re

_NUMBER = r"(?:[0-9][0-9,]*(?:\.[0-9]+)?|\?)"
# Engineering hours use Python float text, including finite exponent notation.
_HOURS_NUMBER = r"(?:[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?|\?)"
_PREFIX = re.compile(r"(?P<amounts>No monetary total calculated|(?:low|base|high) [A-Z]{3} " + _NUMBER + r"(?:, (?:low|base|high) [A-Z]{3} " + _NUMBER + r")*) over (?P<days>[0-9]+) days\.(?: Engineering exposure: (?P<low>" + _HOURS_NUMBER + r")–(?P<high>" + _HOURS_NUMBER + r") hours\.)? (?P<tail>.+)", re.DOTALL)

_GENERATED_COPY = {
    "The unresolved condition can create engineering rework and release delay.": "La condición no resuelta puede generar retrabajo de ingeniería y retrasos en la entrega.",
    "Formula: exposure = direct cost + engineering hours × blended engineering cost/hour + release-delay days × release-delay cost/day.": "Fórmula: exposición = costo directo + horas de ingeniería × costo combinado de ingeniería/hora + días de retraso × costo de retraso/día.",
    "Dollar conversion was not performed because no defensible monetary conversion rate was supplied.": "No se realizó una conversión monetaria porque no se proporcionó una tasa de conversión justificable.",
}

def generated_cost_spanish(text):
    """Translate generated labels; surrounding prose still uses the strict translator."""
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field
    if text in _GENERATED_COPY:
        return _GENERATED_COPY[text]
    qualitative = re.fullmatch(r"(Minimal|Limited|Material|Severe|Critical|Unrated) qualitative exposure over ([0-9]+) days\. (.+)", text, re.DOTALL)
    if qualitative:
        levels = {'Minimal':'Mínima','Limited':'Limitada','Material':'Material','Severe':'Grave','Critical':'Crítica','Unrated':'Sin calificar'}
        tail = _translate_presentation_field(qualitative[3], 'recommendation')
        return f"Exposición cualitativa {levels[qualitative[1]]} durante {qualitative[2]} días. {tail}"
    match = _PREFIX.fullmatch(text)
    if not match:
        return None
    amounts = match['amounts']
    if amounts == 'No monetary total calculated':
        amounts = 'No se calculó un total monetario'
    else:
        amounts = re.sub(r'\b(low|base|high)\b', lambda m: {'low':'bajo','base':'base','high':'alto'}[m[0]], amounts)
    tail = match['tail']
    for source, target in _GENERATED_COPY.items():
        tail = tail.replace(source, target)
    for source,target in (
        ('Inputs: engineering hours low/base/high=', 'Entradas: horas de ingeniería bajo/base/alto='),
        ('direct cost low/base/high=', 'costo directo bajo/base/alto='),
        ('release-delay days low/base/high=', 'días de retraso bajo/base/alto='),
        ('engineering rate=', 'tarifa de ingeniería='),
        ('release-delay cost/day=', 'costo de retraso/día='),
        ('not supplied', 'no proporcionado'), ('Source:', 'Fuente:')):
        tail = tail.replace(source,target)
    tail = _translate_presentation_field(tail, 'recommendation')
    hours = '' if match['low'] is None else f" Exposición de ingeniería: {match['low']}–{match['high']} horas."
    return f"{amounts} durante {match['days']} días.{hours} {tail}"
