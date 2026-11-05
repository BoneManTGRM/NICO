import base64
from copy import deepcopy
import io
import json
import zipfile

import pytest
from pypdf import PdfReader

from nico import ordinary_review_bundle_v2 as bundles
from tests.test_client_pdf_compose_v2 import _pdf


def identity(locale="en"):
    return {"run_id": "comprun_bundle", "repository": "owner/repo", "commit_sha": "a" * 40,
            "report_language": locale, "canonical_truth_sha256": "b" * 64}


def sections(counts=(32, 32)):
    return [(f"section-{index}", _pdf(*[[f"SECTION_{index}_PAGE_{page}"] for page in range(count)]))
            for index, count in enumerate(counts)]


def validate(bundle, expected=None):
    bundles.validate_review_bundle(bundle, expected_identity=expected or identity(),
                                   expected_manifest_sha256=bundle["manifest_sha256"])


def rehash(bundle):
    bundle["manifest_sha256"] = bundles._sha(bundles._json(bundle["manifest"]))


def test_deterministic_complete_partition_and_navigation():
    source = sections((32, 32, 70))
    bundle = bundles.build_review_bundle(identity(), source)
    assert bundle == bundles.build_review_bundle(identity(), source)
    assert [v["page_count"] for v in bundle["manifest"]["volumes"]] == [33, 60, 44]
    # Whole sections that fit a fresh volume do not split merely to fill space.
    assert bundle["manifest"]["volumes"][0]["segments"] == [
        {"section_id": "section-0", "source_start": 0, "page_count": 32, "volume_start": 1}]
    observed = []
    for member, file in zip(bundle["manifest"]["volumes"], bundle["files"]):
        reader = PdfReader(io.BytesIO(base64.b64decode(file["pdf_base64"])))
        assert len(reader.pages) <= 60
        assert "CLIENT DELIVERY BLOCKED" in reader.pages[0].extract_text()
        assert reader.page_labels == [str(n) for n in range(1, len(reader.pages) + 1)]
        assert [reader.get_destination_page_number(item) for item in reader.outline] == [s["volume_start"] for s in member["segments"]]
        observed.extend(p.extract_text() for p in reader.pages[member["index_pages"]:])
    expected = [p.extract_text() for _, pdf in source for p in PdfReader(io.BytesIO(pdf)).pages]
    assert observed == expected
    kwargs = {"expected_identity": identity(), "expected_manifest_sha256": bundle["manifest_sha256"]}
    archive = bundles.review_bundle_zip(bundle, **kwargs)
    assert archive == bundles.review_bundle_zip(bundle, **kwargs)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert len(zipped.namelist()) == len(bundle["files"]) + 1
        assert json.loads(zipped.read("bundle-manifest.json")) == bundle["manifest"]
        for file in bundle["files"]:
            assert zipped.read(file["filename"]) == base64.b64decode(file["pdf_base64"])


@pytest.fixture(scope="module")
def frozen():
    return bundles.build_review_bundle(identity(), sections())


@pytest.mark.parametrize("damage", ["missing", "extra", "reorder", "duplicate", "path", "tamper"])
def test_members_fail_closed(frozen, damage):
    bundle = deepcopy(frozen)
    if damage == "missing": bundle["files"].pop()
    if damage == "extra": bundle["files"].append(deepcopy(bundle["files"][0]))
    if damage == "reorder": bundle["files"].reverse()
    if damage == "duplicate": bundle["files"][1] = deepcopy(bundle["files"][0])
    if damage == "path": bundle["files"][0]["filename"] = "../report.pdf"
    if damage == "tamper": bundle["files"][0]["pdf_base64"] = base64.b64encode(_pdf(["changed"])).decode()
    with pytest.raises(ValueError): validate(bundle)


@pytest.mark.parametrize("field,value", [("run_id", "other"), ("repository", "other/repo"),
                                         ("commit_sha", "c" * 40), ("canonical_truth_sha256", "d" * 64),
                                         ("report_language", "es-MX")])
def test_external_identity_is_required(frozen, field, value):
    expected = identity(); expected[field] = value
    with pytest.raises(ValueError, match="identity_mismatch"): validate(frozen, expected)


def test_changed_manifest_cannot_reuse_approval_identity(frozen):
    bundle = deepcopy(frozen)
    bundle["manifest"]["volumes"].reverse()
    rehash(bundle)
    with pytest.raises(ValueError, match="manifest_digest"):
        bundles.validate_review_bundle(bundle, expected_identity=identity(), expected_manifest_sha256=frozen["manifest_sha256"])


@pytest.mark.parametrize("damage", ["duplicate_source", "order", "unaccounted", "promote", "traversal", "source_hash"])
def test_structural_checks_even_with_recomputed_manifest(frozen, damage):
    bundle = deepcopy(frozen)
    manifest = bundle["manifest"]
    if damage == "duplicate_source": manifest["source_sections"][1]["section_id"] = manifest["source_sections"][0]["section_id"]
    if damage == "order": manifest["source_sections"].reverse()
    if damage == "unaccounted": manifest["volumes"][0]["segments"][0]["page_count"] -= 1
    if damage == "promote": manifest["client_delivery_allowed"] = True
    if damage == "traversal": manifest["volumes"][0]["filename"] = "../report.pdf"
    if damage == "source_hash": manifest["source_sections"][0]["page_digests"][0] = "0" * 64
    rehash(bundle)
    with pytest.raises(ValueError): validate(bundle)


@pytest.mark.parametrize("limit,value", [("MAX_SOURCE_PAGES", 1), ("MAX_TOTAL_PAGES", 1), ("MAX_VOLUMES", 1), ("MAX_BYTES", 1), ("MAX_SECTIONS", 1), ("MAX_SECONDS", -1)])
def test_finite_limits(monkeypatch, limit, value):
    monkeypatch.setattr(bundles, limit, value)
    with pytest.raises(ValueError, match="limit"):
        bundles.build_review_bundle(identity(), sections())


def test_index_page_growth_counts_against_sixty():
    bundle = bundles.build_review_bundle(identity(), sections((1,) * 60))
    assert [v["page_count"] for v in bundle["manifest"]["volumes"]] == [60, 4]
    assert bundle["manifest"]["source_page_count"] == 60
    assert bundle["manifest"]["total_page_count"] == 64


@pytest.mark.parametrize("spanish", [False, True])
def test_existing_dense_worksheets_keep_streams_typography_and_text(monkeypatch, spanish):
    from nico import comprehensive_pdf_layout_polish_v1 as polish
    from nico import comprehensive_client_review_companion_v5 as v5
    from tests.test_readable_professional_worksheets import dense_sections
    from tests.test_comprehensive_pdf_layout_polish_v1 import _review_canonical
    projected = dense_sections(spanish)
    monkeypatch.setattr(v5, "substantive_review_sections", lambda *a, **k: deepcopy(projected))
    pdf = polish._render_polished_review_pdf(_review_canonical(), spanish=spanish)
    locale = "es-MX" if spanish else "en"
    source = PdfReader(io.BytesIO(pdf))
    bundle = bundles.build_review_bundle(identity(locale), [("worksheets", pdf)])
    validate(bundle, identity(locale))
    copied = []
    for member, file in zip(bundle["manifest"]["volumes"], bundle["files"]):
        reader = PdfReader(io.BytesIO(base64.b64decode(file["pdf_base64"])))
        copied.extend(reader.pages[member["index_pages"]:])
    assert len(copied) == len(source.pages)
    import math
    sizes = []
    for before, after in zip(source.pages, copied):
        assert before.get_contents().get_data() == after.get_contents().get_data()
        assert before.extract_text() == after.extract_text()
        def visitor(text, cm, tm, font, size):
            if text.strip():
                a,b=tm[0]*cm[0]+tm[1]*cm[2],tm[0]*cm[1]+tm[1]*cm[3]
                c,d=tm[2]*cm[0]+tm[3]*cm[2],tm[2]*cm[1]+tm[3]*cm[3]
                sizes.append(size*min(math.hypot(a,b), math.hypot(c,d)))
        after.extract_text(visitor_text=visitor)
    assert sizes and min(sizes) >= 9


def test_locales_have_independent_page_populations():
    en = bundles.build_review_bundle(identity(), sections((30, 29)))
    es = bundles.build_review_bundle(identity("es-MX"), sections((30, 30)))
    assert len(en["files"]) == 1 and len(es["files"]) == 2
    assert en["manifest_sha256"] != es["manifest_sha256"]
    assert "Volumen 1" in PdfReader(io.BytesIO(base64.b64decode(es["files"][0]["pdf_base64"]))).pages[0].extract_text()


def test_navigation_tampering_rejected_even_after_rehash(frozen):
    from pypdf import PdfWriter
    bundle = deepcopy(frozen)
    reader = PdfReader(io.BytesIO(base64.b64decode(bundle["files"][0]["pdf_base64"])))
    writer = PdfWriter()
    writer.append(reader)
    writer.pages[0].replace_contents(PdfReader(io.BytesIO(_pdf(["False volume index"])) ).pages[0].get_contents())
    out = io.BytesIO(); writer.write(out); data = out.getvalue()
    bundle["files"][0]["pdf_base64"] = base64.b64encode(data).decode()
    bundle["manifest"]["volumes"][0].update(sha256=bundles._sha(data), size_bytes=len(data))
    rehash(bundle)
    with pytest.raises(ValueError, match="navigation"): validate(bundle)


def test_builder_never_returns_partial_bundle(monkeypatch):
    source = sections(); saved = deepcopy(source)
    navigation = bundles._navigation
    def fail_second(segments, number, *args):
        if number == 2: raise ValueError("injected second volume failure")
        return navigation(segments, number, *args)
    monkeypatch.setattr(bundles, "_navigation", fail_second)
    with pytest.raises(ValueError, match="second volume failure"):
        bundles.build_review_bundle(identity(), source)
    assert source == saved
