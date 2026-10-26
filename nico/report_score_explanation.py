"""Read-only presentation of explicitly supplied, internally consistent deductions."""
from collections.abc import Callable, Mapping

UNAVAILABLE = "Score deduction explanation unavailable: the retained score contract is missing, unsupported, or inconsistent."
LABELS_ES = {
    UNAVAILABLE: "Explicación de deducciones no disponible: el contrato de puntuación conservado falta, no es compatible o es inconsistente.",
    "Technical-to-adjusted score explanation": "Explicación de la puntuación técnica a la ajustada",
    "Technical score": "Puntuación técnica",
    "Evidence-adjusted score": "Puntuación ajustada por evidencia",
    "Candidate-volume deduction": "Deducción por volumen de candidatos",
    "Missing raw-payload deduction": "Deducción por datos originales faltantes",
    "Incomplete-analyzer deduction": "Deducción por analizadores incompletos",
    "Other named deductions": "Otras deducciones identificadas",
    "Retained formula": "Fórmula conservada",
    "Incomplete analyzers recorded by the contract": "Analizadores incompletos registrados en el contrato",
    "Analyzer names unavailable in the retained contract": "Nombres de analizadores no disponibles en el contrato conservado",
}


def score_explanation(assessment: Mapping, localize: Callable[[str], str] = lambda s: s) -> list[str]:
    """Never repair scores, synthesize missing penalties, or infer weighting."""
    unavailable = [localize(UNAVAILABLE)]
    contract = assessment.get("score_contract")
    if not isinstance(contract, Mapping):
        return unavailable
    model = contract.get("scoring_model_version")
    fields = [("missing_raw_payload_penalty", "Missing raw-payload deduction"),
              ("incomplete_analyzer_penalty", "Incomplete-analyzer deduction")]
    if model == "technical-minus-named-assurance-deductions.v1":
        fields.insert(0, ("candidate_volume_penalty", "Candidate-volume deduction"))
    elif model != "technical-minus-evidence-completeness-deductions.v1":
        return unavailable
    technical, adjusted = contract.get("technical_score"), contract.get("evidence_adjusted_score")
    if any(type(v) is not int or not 0 <= v <= 100 for v in (technical, adjusted)):
        return unavailable
    penalties = [contract.get(key) for key, _ in fields]
    if any(type(v) is not int or v < 0 for v in penalties):
        return unavailable
    others = contract.get("other_assurance_penalties", {})
    if not isinstance(others, Mapping) or any(not isinstance(k, str) or not k.strip()
            or type(v) is not int or v < 0 for k, v in others.items()):
        return unavailable
    if model == "technical-minus-named-assurance-deductions.v1":
        if "other_assurance_penalties" not in contract:
            return unavailable
        penalties.append(sum(others.values()))
        if (type(contract.get("other_assurance_penalty_total", penalties[-1])) is not int
                or contract.get("other_assurance_penalty_total", penalties[-1]) != penalties[-1]):
            return unavailable
    elif (others or type(contract.get("candidate_volume_penalty", 0)) is not int
          or contract.get("candidate_volume_penalty", 0) != 0):
        return unavailable
    total = sum(penalties)
    if (max(0, technical - total) != adjusted
            or type(contract.get("assurance_penalty")) is not int
            or contract.get("assurance_penalty") != total):
        return unavailable
    formula = " - ".join(map(str, [technical, *penalties])) + f" = {adjusted}"
    if contract.get("score_formula") != formula:
        return unavailable
    maturity = assessment.get("maturity_signal", {})
    if not isinstance(maturity, Mapping):
        return unavailable
    for obj, keys, expected in (
        (assessment, ("technical_score", "canonical_technical_score"), technical),
        (assessment, ("evidence_adjusted_score", "canonical_evidence_adjusted_score"), adjusted),
        (maturity, ("score", "presented_score", "technical_score"), technical),
        (maturity, ("evidence_readiness_score", "evidence_adjusted_score", "canonical_evidence_adjusted_score"), adjusted),
    ):
        if any(key in obj and (type(obj[key]) is not int or obj[key] != expected) for key in keys):
            return unavailable
    lines = [f'{localize("Technical score")}: {technical}/100']
    lines += [f"{localize(label)}: {contract[key]}" for key, label in fields]
    if model == "technical-minus-named-assurance-deductions.v1":
        lines.append(f'{localize("Other named deductions")}: {sum(others.values())}')
        lines += [f"{key}: {value}" for key, value in others.items()]
    if contract["incomplete_analyzer_penalty"]:
        names = contract.get("incomplete_analyzers")
        if isinstance(names, list) and names and all(isinstance(n, str) and n.strip() for n in names):
            lines.append(f'{localize("Incomplete analyzers recorded by the contract")}: {", ".join(names)}')
        else:
            lines.append(localize("Analyzer names unavailable in the retained contract"))
    lines += [f'{localize("Retained formula")}: {formula}',
              f'{localize("Evidence-adjusted score")}: {adjusted}/100']
    return lines
