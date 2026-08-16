from __future__ import annotations

import io
from copy import deepcopy

import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico import comprehensive_full_report_finish_v1 as finish
from nico.comprehensive_full_data_worksheet_localization_v1 import (
    WORKSHEET_TITLES_BY_STAGE_ID,
    install_comprehensive_full_data_worksheet_localization_v1,
)


def _canonical(*, spanish: bool = True, drop_stage: str | None = None) -> dict:
    stages = []
    for stage_id, (english_title, spanish_title) in WORKSHEET_TITLES_BY_STAGE_ID.items():
        if stage_id == drop_stage:
            continue
        stages.append(
            {
                "stage_id": stage_id,
                "title": spanish_title if spanish else english_title,
                "status": "review_required",
                "evidence": [f"retained evidence for {stage_id}"],
            }
        )
    return {
        "report_language": "es-MX" if spanish else "en",
        "identity": {
            "run_id": "comprun_full_data_localized_worksheets",
            "report_language": "es-MX" if spanish else "en",
        },
        "assessment": {
            "report_language": "es-MX" if spanish else "en",
            "stage_summaries": deepcopy(stages),
        },
        "stage_summaries": stages,
    }


def _spanish_surfaces(*, omit_title: str | None = None) -> tuple[str, str, bytes]:
    titles = [
        spanish_title
        for _english_title, spanish_title in WORKSHEET_TITLES_BY_STAGE_ID.values()
        if spanish_title != omit_title
    ]
    markdown = "\n".join(f"## {title}" for title in titles)
    rendered_html = "<html><body>" + "".join(f"<h2>{title}</h2>" for title in titles) + "</body></html>"
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, invariant=1).build(
        [Paragraph(title, styles["BodyText"]) for title in titles]
    )
    return markdown, rendered_html, buffer.getvalue()


def test_spanish_full_data_worksheets_use_stage_ids_and_localized_surface_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def strict_legacy_validator(canonical, markdown, rendered_html, pdf):
        captured["canonical"] = canonical
        captured["markdown"] = markdown
        captured["rendered_html"] = rendered_html
        captured["pdf"] = pdf
        titles = {stage.get("title") for stage in canonical.get("stage_summaries") or []}
        assert set(finish._WORKSHEET_TITLES).issubset(titles)
        for title in finish._WORKSHEET_TITLES:
            assert title in markdown
        return {"proof_kind": "full_comprehensive", "worksheet_count": 8}

    monkeypatch.setattr(finish, "assert_full_data_parity", strict_legacy_validator)
    state = install_comprehensive_full_data_worksheet_localization_v1()
    markdown, rendered_html, pdf = _spanish_surfaces()

    proof = finish.assert_full_data_parity(
        _canonical(),
        markdown,
        rendered_html,
        pdf,
    )

    assert state["localized_spanish_worksheet_titles_required"] is True
    assert state["missing_worksheets_not_synthesized"] is True
    assert proof["proof_kind"] == "full_comprehensive"
    assert proof["localized_spanish_worksheet_validation"] is True
    assert proof["worksheet_identity_source"] == "stable_stage_id"
    assert captured["rendered_html"] == rendered_html
    assert captured["pdf"] == pdf
    assert "validation aliases for localized worksheet headings" in str(captured["markdown"])


def test_missing_canonical_worksheet_stage_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def legacy_validator(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(finish, "assert_full_data_parity", legacy_validator)
    install_comprehensive_full_data_worksheet_localization_v1()
    markdown, rendered_html, pdf = _spanish_surfaces()

    with pytest.raises(
        ValueError,
        match="full-data proof is missing human-review worksheets: Requirements Traceability",
    ):
        finish.assert_full_data_parity(
            _canonical(drop_stage="requirements_traceability"),
            markdown,
            rendered_html,
            pdf,
        )

    assert called is False


def test_missing_spanish_worksheet_heading_still_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def legacy_validator(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(finish, "assert_full_data_parity", legacy_validator)
    install_comprehensive_full_data_worksheet_localization_v1()
    missing_title = WORKSHEET_TITLES_BY_STAGE_ID["six_month_roadmap"][1]
    markdown, rendered_html, pdf = _spanish_surfaces(omit_title=missing_title)

    with pytest.raises(
        ValueError,
        match="full-data Spanish proof is missing localized human-review worksheets",
    ):
        finish.assert_full_data_parity(
            _canonical(),
            markdown,
            rendered_html,
            pdf,
        )

    assert called is False


def test_english_full_data_path_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _canonical(spanish=False)
    markdown = "english markdown"
    rendered_html = "<p>english html</p>"
    pdf = b"not-read-on-english-path"
    captured: dict[str, object] = {}

    def legacy_validator(canonical_arg, markdown_arg, html_arg, pdf_arg):
        captured.update(
            canonical=canonical_arg,
            markdown=markdown_arg,
            html=html_arg,
            pdf=pdf_arg,
        )
        return {"proof_kind": "full_comprehensive"}

    monkeypatch.setattr(finish, "assert_full_data_parity", legacy_validator)
    install_comprehensive_full_data_worksheet_localization_v1()

    proof = finish.assert_full_data_parity(
        canonical,
        markdown,
        rendered_html,
        pdf,
    )

    assert proof == {"proof_kind": "full_comprehensive"}
    assert captured == {
        "canonical": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf": pdf,
    }
