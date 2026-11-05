from __future__ import annotations

import io
import re
from copy import deepcopy
from functools import partial
from nico import comprehensive_artifact_manifest_approval_v1 as manifest

import pytest
from pypdf import PdfReader

from nico.comprehensive_human_review_package_cleanup_v1 import render_manifest_approval_supplement
from nico.comprehensive_spanish_client_surface_localization_v85 import _render_spanish_manifest


def _inputs(spanish: bool, extreme: bool):
    canonical = {"identity": {"repository": "example/review", "commit_sha": "a" * 40,
        "run_id": "synthetic_typography", "evidence_ledger_id": "synthetic_ledger",
        "report_language": "es-MX" if spanish else "en"},
        "approval": {"reviewer_identity": "REVIEWER_START_" + ("retained_" * (500 if extreme else 1)) + "_REVIEWER_END"}}
    entries = [{"artifact_type": "evidence_csv", "filename": f"artifact_{i}_" + ("ámbito_evidence_" * (350 if extreme else 2)) + f"_TAIL_{i}.csv",
                "sha256": f"{i + 1:064x}"} for i in range(3)]
    return canonical, entries


@pytest.mark.parametrize("spanish", [False, True], ids=["en", "es-MX"])
@pytest.mark.parametrize("extreme", [False, True], ids=["short", "oversized_rows"])
def test_manifest_flows_complete_literals_at_readable_size(spanish, extreme) -> None:
    canonical, entries = _inputs(spanish, extreme)
    before = deepcopy((canonical, entries))
    render = partial(_render_spanish_manifest, manifest) if spanish else render_manifest_approval_supplement
    pdf = render(canonical, entries)
    assert render(canonical, entries) == pdf
    assert (canonical, entries) == before
    reader = PdfReader(io.BytesIO(pdf))
    raw = "\n".join(p.extract_text() or "" for p in reader.pages)
    # Page decorations may occur inside a row split across pages. Remove only
    # renderer-owned footer lines before testing complete literal sequences.
    lines = [line for line in raw.splitlines() if not line.startswith("NICO |") and not re.fullmatch(r"(?:Integrity|Integridad) \d+", line.strip())]
    text = re.sub(r"\s+", "", "\n".join(lines))
    # Repeated column headers and adjacent digest cells can interrupt a
    # filename across a page boundary; remove only those exact decorations.
    filename_text = text
    for label in ("ArtifactFilenameSHA-256", "ArtefactoNombredearchivoSHA-256"):
        filename_text = filename_text.replace(label, "")
    for item in entries:
        filename_text = filename_text.replace(item["sha256"], "")
    for item in entries:
        assert re.sub(r"\s+", "", item["filename"]) in filename_text
        assert item["sha256"] in text
    assert canonical["approval"]["reviewer_identity"] in text
    assert "APPROVED FINAL" in raw if not spanish else "FINAL APROBADO" in raw
    sizes = []
    for page in reader.pages:
        def visit(t, cm, tm, font, size):
            if t.strip() and not t.startswith("NICO |") and not re.fullmatch(r"(?:Integrity|Integridad) \d+", t.strip()):
                sizes.append(float(size))
        page.extract_text(visitor_text=visit)
    assert sizes and min(sizes) >= 9
    if extreme:
        assert len(reader.pages) > 2


def test_worker_preparation_preserves_flowing_review_binding() -> None:
    # Bootstrap mutates renderer aliases globally; verify in a fresh interpreter.
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", """
from nico.api import final_report_worker_bootstrap
from nico import client_report_completion_v2 as completion
from nico import comprehensive_client_review_companion_v7 as review
from nico import comprehensive_client_review_companion_v7_rebind as rebind
from tests.test_client_report_completion_v2 import _package

def assert_flowing():
    for renderer in (completion.render_comprehensive_review_companion_pdf,
                     review.render_paired_substantive_review_pdf,
                     rebind.render_paired_substantive_review_pdf):
        assert getattr(renderer, '_nico_review_flowing', False)

assert_flowing()
package = completion.prepare_client_report_package(_package())
assert_flowing()
completion.legacy._prepare_completion_text(package)
assert_flowing()
"""], check=True, timeout=45, capture_output=True, text=True)


def test_manifest_markup_preserves_safe_normalization_without_length_cap():
    import html
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import comprehensive_full_report_finish_v1 as finish

    raw = '  alpha\t<beta>\x7f\n' + 'retained_' * 300 + '.csv  '
    expected = ' '.join(raw.replace('\x7f', '-').split()).strip()
    for helper in (cleanup._filename_markup, cleanup._digest_markup,
                   finish.filename_markup, finish.digest_markup):
        rendered = helper(raw)
        assert '<beta>' not in rendered
        assert html.unescape(rendered.replace('<br/>', '')) == expected
