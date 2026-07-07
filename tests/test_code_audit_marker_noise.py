from nico.report_accuracy import apply_code_marker_noise_filter


def test_non_actionable_security_wording_does_not_cap_code_audit():
    sections = [
        {
            "id": "code_audit",
            "label": "Code Audit",
            "score": 80,
            "status": "green",
            "evidence": [
                "Commits returned since 2026-01-01T00:00:00Z: 100.",
                "Pull requests updated in the assessment window: 48; merged=44; open=2.",
                "Text files inspected for code-risk markers: TODO/FIXME/security notes=57, risky pattern hits=2, test-path signals=2.",
                ".github/workflows/security-audit.yml:1: name: Security Audit Evidence",
                "docs/REAL_EVIDENCE_ARTIFACT_INGESTION_V19.md:2: security evidence is parsed from artifacts.",
            ],
            "findings": ["TODO/FIXME/security-note markers require triage before client-ready delivery."],
            "unavailable": [],
        }
    ]

    apply_code_marker_noise_filter(sections)
    code = sections[0]

    assert code["score"] >= 86
    assert code["status"] == "green"
    assert code["findings"] == []
    assert any("actionable TODO/FIXME/security markers=0" in item for item in code["evidence"])
    assert not any("Security Audit Evidence" in item for item in code["evidence"])


def test_actionable_todo_marker_still_caps_code_audit():
    sections = [
        {
            "id": "code_audit",
            "label": "Code Audit",
            "score": 80,
            "status": "green",
            "evidence": [
                "Text files inspected for code-risk markers: TODO/FIXME/security notes=1, risky pattern hits=0, test-path signals=2.",
                "nico/example.py:10: TODO: replace placeholder before release",
            ],
            "findings": ["TODO/FIXME/security-note markers require triage before client-ready delivery."],
            "unavailable": [],
        }
    ]

    apply_code_marker_noise_filter(sections)
    code = sections[0]

    assert code["score"] == 80
    assert code["findings"] == ["TODO/FIXME/security-note markers require triage before client-ready delivery."]
    assert any("TODO: replace placeholder" in item for item in code["evidence"])
