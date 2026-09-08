"""E3/E4 proof through actual collectors, final reconstruction and composition."""
from __future__ import annotations

import base64
import copy
import io
import json

import pytest
from pypdf import PdfReader

import test_source_architecture_profile_evidence as source_fixture
from test_client_report_completion_v2 import _package
from nico import comprehensive_report_package as report
from nico.comprehensive_native_providers import architecture_data_flow_provider, deployment_review_provider


def collected_package(monkeypatch, tmp_path, *, spanish=False):
    package = _package()
    canonical = package["json"]
    identity = dict(canonical["identity"])
    identity.update(customer_id="customer_render_test", project_id="project_render_test", report_language="es-MX" if spanish else "en")
    snapshot = {**identity, "status": "attached", "snapshot_id": "snapshot_render_test", "tree_sha": "b" * 40,
                "captured_at": "2026-09-08T10:00:00Z"}
    monkeypatch.setattr(source_fixture, "identities", lambda: (copy.deepcopy(identity), copy.deepcopy(snapshot)))
    context, repository, complexity, _ = source_fixture.collect("snapshot", monkeypatch, tmp_path)
    canonical["identity"] = identity
    canonical["repository_evidence"] = repository
    canonical["complexity_evidence"] = complexity
    canonical["stage_summaries"] = [
        report._stage_summary("deployment_and_infrastructure", deployment_review_provider(context)),
        report._stage_summary("architecture_and_data_flow", architecture_data_flow_provider(context)),
    ]
    return package, repository["architecture_evidence"]["source_observation"]


def test_projection_keeps_full_observation_and_profile_without_flattening(monkeypatch, tmp_path):
    package, observation = collected_package(monkeypatch, tmp_path)
    stage = package["json"]["stage_summaries"][1]
    assert stage["source_observation"] == observation
    assert stage["structured_tables"]
    assert stage["profile_coverage"]["analyzed_source_files"] == package["json"]["complexity_evidence"]["files_analyzed"]
    assert not any("observed_text_sha256" in line for line in stage["evidence"])


@pytest.mark.parametrize("spanish", [False, True])
def test_actual_final_package_retains_source_tables_and_bilingual_pdf(monkeypatch, tmp_path, spanish):
    from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
    from nico.comprehensive_spanish_current_copy_worker_v98 import install_comprehensive_spanish_current_copy_worker_v98
    from nico.comprehensive_client_review_companion_v7 import install_comprehensive_review_companion_v7
    from nico.comprehensive_pdf_layout_polish_v1 import install_comprehensive_pdf_layout_polish_v1
    from nico.comprehensive_spanish_canonical_report_v87 import render_spanish_markdown, render_spanish_pdf
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    assert install_comprehensive_pdf_embedded_fonts_v1()["bound"] is True
    assert install_comprehensive_spanish_current_copy_worker_v98()["bound"] is True
    install_comprehensive_review_companion_v7()
    install_comprehensive_pdf_layout_polish_v1()
    package, observation = collected_package(monkeypatch, tmp_path, spanish=spanish)
    canonical = package["json"]
    retained_tables = copy.deepcopy(canonical["stage_summaries"][1]["structured_tables"])
    if spanish:
        package["markdown"] = render_spanish_markdown(canonical)
        pdf, _ = render_spanish_pdf(canonical)
        package["pdf_base64"] = base64.b64encode(pdf).decode()
    else:
        package["markdown"] = report._markdown(canonical["identity"], canonical["assessment"], canonical["stage_summaries"], package["generated_at"])
        encoded, error, _ = report._pdf(canonical["identity"], canonical["assessment"], canonical["stage_summaries"], package["generated_at"])
        assert not error
        package["pdf_base64"] = encoded
    result = rebuild_client_artifacts(package)
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    title = "Componentes observados en el código" if spanish else "Observed source components"
    for rendered in (result["markdown"], result["html"], text):
        assert title in rendered
        assert "app.py" in rendered
        assert ("Cobertura del perfil acotado" if spanish else "Bounded profile coverage") in rendered
        assert observation["observation_sha256"] in rendered.replace("\n", "")
    assert "<table>" in result["html"] and '<th scope="col">' in result["html"]
    assert result["json"]["stage_summaries"][1]["source_observation"] == observation
    assert result["json"]["stage_summaries"][1]["structured_tables"] == retained_tables
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert len(reader.pages) <= result["client_report_completion"]["client_pdf_page_boundary"]
    (tmp_path / ("source-profile-es-MX.pdf" if spanish else "source-profile-en.pdf")).write_bytes(pdf)
    (tmp_path / ("source-profile-es-MX.json" if spanish else "source-profile-en.json")).write_text(json.dumps(result["json"], ensure_ascii=False, sort_keys=True))


def test_source_table_cells_are_escaped_and_machine_facts_are_not_translated():
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    stage = {"structured_tables": [{"title": "Observed source components", "columns": ["Source"],
                                    "rows": [["<script>alert(1)</script>|á.py"]]}],
             "source_observation": {"source": "Not assessed/file.py", "observation_sha256": "a" * 64}}
    assert _localize_tree(stage, path=("stage_summaries",)) == stage
    markdown = "\n".join(report._source_markdown(stage, spanish=True))
    html = report._semantic_html(markdown, "Prueba")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert '<th scope="col">Fuente</th>' in html


def test_shared_source_projection_is_complete_in_both_stage_orders(monkeypatch, tmp_path):
    package, _ = collected_package(monkeypatch, tmp_path)
    stages = package["json"]["stage_summaries"]
    forward = report._source_presentation_stages(stages)
    reverse = report._source_presentation_stages(reversed(stages))
    assert forward == reverse
    assert len(forward) == 1
    assert forward[0]["profile_coverage"]
    assert len(forward[0]["structured_tables"]) == 3
