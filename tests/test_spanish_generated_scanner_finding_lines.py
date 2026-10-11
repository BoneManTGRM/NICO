"""Production-generated scanner summaries retain literals and translate owned copy."""
import pytest

from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.client_finding_remediation_register_v1 import _scanner_finding_record
from nico.v2_premium_report_renderer import _finding_lines


def generated_line():
    record = _scanner_finding_record(
        {"scanner_name": "semgrep", "category": "static"},
        {"check_id": "owned.rule.0", "path": "src/main.py"},
        "a" * 40,
    )
    return _finding_lines([record])[0], record


def test_generated_scanner_finding_summary_translates_owned_copy():
    source, record = generated_line()
    translated = canonical._translate_presentation_field(source, "findings")
    assert translated == (
        f"P2 · owned.rule.0 · {record['finding_id']} · src/main.py · "
        "Impacto: Una instancia confirmada podría afectar la seguridad, la corrección, "
        "la mantenibilidad o la fiabilidad de la entrega; un candidato no confirmado "
        "solo afecta la garantía de la evidencia. · Recomendación: requiere revisión"
    )


def test_generated_scanner_correction_and_ranged_location_translate():
    record = _scanner_finding_record(
        {"scanner_name": "semgrep", "category": "static"},
        {"check_id": "owned.rule.0", "path": "src/main.py",
         "line": 4, "end_line": 8, "column": 2},
        "a" * 40,
    )
    record["recommendation"] = record["recommended_correction"]
    assert record["location"] == "src/main.py:4-8:2"
    translated = canonical._translate_presentation_field(_finding_lines([record])[0], "findings")
    assert "src/main.py:4-8:2" in translated
    assert translated.endswith(
        "Recomendación: Revise la ubicación exacta del código fuente, aplique la corrección "
        "acotada más pequeña, ejecute pruebas de regresión específicas y completas, "
        "y vuelva a ejecutar NICO sobre el commit de remediación."
    )


@pytest.mark.parametrize("field,key", [
    ("observed_evidence", "fact"),
    ("interpretation", "interpretation"),
    ("business_impact", "business_impact"),
    ("recommended_correction", "recommendation"),
])
def test_generated_register_fields_translate_and_unknown_variants_remain_blocked(field, key):
    _, record = generated_line()
    source = record[field]
    translated = canonical._translate_presentation_field(source, key)
    assert translated != source
    assert not canonical._looks_like_untranslated_english(translated)
    with pytest.raises(ValueError, match="Spanish presentation"):
        canonical._translate_presentation_field(source + " Future untranslated policy requires review.", key)


@pytest.mark.parametrize("old,new", [
    ("owned.rule.0", "Future untranslated title requires review"),
    ("src/main.py", "Future untranslated location requires review"),
    ("requires review", "Future untranslated recommendation requires review"),
    ("A confirmed instance could affect", "A future untranslated impact could affect"),
    (" · Impact:", " · New impact:"),
])
def test_unknown_generated_finding_prose_still_fails_closed(old, new):
    source, _ = generated_line()
    with pytest.raises(ValueError, match="Spanish presentation"):
        canonical._translate_presentation_field(source.replace(old, new), "findings")


def test_long_hyphenated_rule_with_unknown_suffix_is_rejected_promptly():
    # Run the negative case in a bounded subprocess: an ambiguous nested rule-ID
    # regex must not turn a malformed finding into unbounded backtracking.
    import subprocess
    import sys

    source, _ = generated_line()
    source = source.replace("owned.rule.0", "owned-" * 40 + "rule") + "!"
    probe = (
        "import sys\n"
        "from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field\n"
        "try:\n"
        "    _translate_presentation_field(sys.argv[1], 'findings')\n"
        "except ValueError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('Unknown suffix accepted')\n"
    )
    result = subprocess.run([sys.executable, "-c", probe, source], capture_output=True,
                            text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
