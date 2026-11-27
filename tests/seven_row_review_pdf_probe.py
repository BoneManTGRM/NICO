"""Owned 7-row bilingual terminal-report replay. Execute via approved offline wrapper."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
from importlib.metadata import version
import platform
import json
import re
from copy import deepcopy
from pathlib import Path

STAGE = "final_comprehensive_report_generation"
OUTCOMES = ("", "", "needs_more_evidence", "confirmed", "false_positive",
            "not_applicable", "accepted_risk")
PENDING = frozenset(f"REPLAY-{k}" for k in "ABC")
TERMINAL = frozenset(f"REPLAY-{k}" for k in "DEFG")
EXPECTED_DISPOSITIONS = {
    "REPLAY-A": "", "REPLAY-B": "", "REPLAY-C": "needs_more_evidence",
    "REPLAY-D": "confirmed", "REPLAY-E": "false_positive",
    "REPLAY-F": "not_applicable", "REPLAY-G": "accepted_risk",
}
COPY = {
    "en": ("Canonical candidate state", "Code", "Recorded dispositions: 4; pending: 3.",
           "Disposition pending", "AUTOMATED DRAFT", "PENDING HUMAN APPROVAL", "CLIENT DELIVERY BLOCKED"),
    "es-MX": ("Estado canónico de candidatos", "Código", "Disposiciones registradas: 4; pendientes: 3.",
              "Disposición pendiente", "BORRADOR AUTOMATIZADO", "APROBACIÓN HUMANA PENDIENTE",
              "ENTREGA AL CLIENTE BLOQUEADA"),
}

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def record_for(package, new_ledger):
    package = deepcopy(package)
    canonical = package["json"]
    ids = tuple(f"REPLAY-{key}" for key in "ABCDEFG")
    findings = [dict(candidate_id=cid, category="code", scanner="bandit",
                     scanner_name="bandit", rule_id="SYNTHETIC-REVIEW",
                     severity="high" if idx == 3 else "medium",
                     path="fixture/demo.py", line=idx + 1, title="Synthetic review fixture",
                     technical_triage_verdict="needs_review",
                     review_requires_individual_attention=True)
                for idx, cid in enumerate(ids)]
    register = dict(canonical["assessment"].get("canonical_scanner_finding_register") or {})
    register.update(findings=findings, candidate_record_count=7)
    from nico.candidate_phase1_workload_refinement_v1 import refine_candidate_review_workload
    register["totals"] = {"raw": 7, "review_required": 7, "source_path": 7}
    register["summary_by_category"] = {"code": dict(register["totals"])}
    register = refine_candidate_review_workload(register)
    canonical["assessment"]["canonical_scanner_finding_register"] = register
    record = {"identity": deepcopy(canonical["identity"]),
              "stage_results": {STAGE: {"report_package": package}}}
    ledger = new_ledger(record)
    ledger["dispositions"].update({
        cid: dict(disposition=value, reviewer="Synthetic Reviewer",
                  reviewer_role="owner", decided_at="2026-08-04T16:16:00Z",
                  rationale="Synthetic fixture only.", residual_risk="synthetic",
                  residual_risk_owner="Synthetic Reviewer")
        for cid, value in zip(ids, OUTCOMES, strict=True) if value
    })
    record["review_work_ledger"] = ledger
    return record

def validate_truth(truth):
    rows = truth["candidate_review"]
    require(len(rows) == 7, "fixture candidate population drift")
    require({r["candidate_id"] for r in rows if r["human_disposition_state"] == "pending"} == PENDING,
            "producer did not retain exactly the three expected pending IDs")
    require({r["candidate_id"] for r in rows if r["human_disposition_state"] == "completed"} == TERMINAL,
            "producer did not retain exactly the four expected terminal IDs")
    require({r["candidate_id"]: r["human_disposition"] for r in rows} == EXPECTED_DISPOSITIONS,
            "producer changed an exact synthetic reviewer disposition")
    require((truth["authorized_human_disposition_pending"],
             truth["authorized_human_disposition_completed"],
             truth["confirmed_material_findings"]) == (3, 4, 1), "producer count drift")
    require(truth["final_human_approval_status"] == "pending" and
            truth["client_delivery_authorization_status"] == "blocked", "producer approval drift")

def _flat(text):
    return " ".join(text.split())

def validate_pdf_pages(layout_pages, locale, expected_pending):
    title, category, topline, status, draft, pending, blocked = COPY[locale]
    cover = _flat(layout_pages[0]) if layout_pages else ""
    require(all(label in cover for label in (draft, pending, blocked)),
            f"{locale}: cover does not show draft, pending approval and blocked delivery")
    require(any(topline in _flat(text) for text in layout_pages),
            f"{locale}: correct current-review top line not found")
    # The seven-row fixture supplies no repository indicator evidence. Inspect the
    # final rendered section, not the generic bounded footer or table of contents.
    parity_title, negative, positives, action = (
        ("2. Platform Parity", "Repository indicator review not established",
         ("Repository indicator review complete", "Record repository indicators as assessed"),
         "Retain repository indicators tied to this revision")
        if locale == "en" else
        ("2. Paridad de plataformas", "Revisión de indicadores del repositorio no establecida",
         ("Revisión de indicadores del repositorio completa", "Registrar los indicadores del repositorio como evaluados"),
         "Conservar los indicadores del repositorio vinculados a esta revisión")
    )
    sections = [_flat(p) for p in layout_pages if parity_title in _flat(p) and negative in _flat(p)]
    require(len(sections) == 1 and action in sections[0], f"{locale}: parity evidence/action missing")
    require(not any(term in _flat(p) for p in layout_pages for term in positives),
            f"{locale}: parity fixture credited missing repository indicators")
    # Require the actual table on a window following its heading. No generic
    # elsewhere duplicate or unlabelled numeric sequence can satisfy this.
    row_pattern = re.compile(r"^\s*" + re.escape(category) +
                             r"\s{2,}7\s{2,}1\s{2,}(\d+)\s{2,}" + re.escape(status) + r"\s*$", re.M)
    observed = []
    for n, page in enumerate(layout_pages, 1):
        if title in page:
            after = page.split(title, 1)[1].splitlines()[:25]
            observed.extend((n, int(m[1])) for m in row_pattern.finditer("\n".join(after)))
    require(len(observed) == 1, f"{locale}: missing or ambiguous current category table")
    require(observed[0][1] == expected_pending,
            f"{locale}: pending row {observed[0][1]}, expected {expected_pending}")
    return observed[0][0]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh output directory required")
    require(re.fullmatch(r"[0-9a-f]{40}", args.checkout_sha), "exact checkout SHA required")
    pins = {"reportlab": "5.1.0", "pillow": "13.0.0", "pypdf": "6.21.4"}
    require(platform.python_version() == "3.11.18", "exact Python runtime required")
    require({name: version(name) for name in pins} == pins, "exact PDF dependencies required")
    from nico.api import final_report_worker_bootstrap as worker
    require(worker.FINAL_REPORT_WORKER_RUNTIME["same_terminal_report_authority_as_production"] is True,
            "terminal worker qualification unavailable")
    from nico.comprehensive_review_work_v1 import ledger_for_record
    from nico import comprehensive_review_report_truth_v1 as review_producer
    from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_v2_premium_report_renderer import _package
    from pypdf import PdfReader

    fixture_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    producer_sha256 = hashlib.sha256(Path(review_producer.__file__).read_bytes()).hexdigest()
    retained = {}
    for locale in COPY:
        source = record_for(_package(locale), ledger_for_record)
        frozen = deepcopy(source)
        validate_truth(review_producer.build_review_truth(source))
        synchronized = review_producer.synchronize_review_truth(source)
        require(source == frozen, "source record mutated")
        package = synchronized["stage_results"][STAGE]["report_package"]
        validate_truth(package["json"]["human_review_truth"])
        result = rebuild_client_artifacts(package)
        _validate_exact_artifact_hashes(result)
        validate_truth(result["json"]["human_review_truth"])
        canonical_digest = canonical_sha256(result["json"])
        require(canonical_digest == result["canonical_truth_sha256"],
                "canonical truth digest drift")
        require(result["json"]["identity"]["report_language"] == locale, "report locale drift")
        require(result["client_delivery_allowed"] is False and
                result["human_review_required"] is True, "package authorization drift")
        require(result["approval_status"] == "pending_human_approval"
                and result["delivery_status"] == "blocked_pending_human_approval",
                "draft lifecycle drift")
        encoded = result["pdf_base64"]
        require(len(encoded) <= 4 * 1024 * 1024, "fixture PDF exceeds base64 cap")
        pdf = base64.b64decode(encoded, validate=True)
        require(0 < len(pdf) <= 3 * 1024 * 1024, "fixture PDF exceeds byte cap")
        reader = PdfReader(io.BytesIO(pdf))
        require(reader.root_object.get("/Lang") == locale, "PDF catalog locale drift")
        pages = [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
        table_page = validate_pdf_pages(pages, locale, 3)
        retained[locale] = (pdf, dict(pdf_sha256=hashlib.sha256(pdf).hexdigest(),
                                    pdf_size_bytes=len(pdf), pages=len(pages), table_page=table_page,
                                    canonical_truth_sha256=canonical_digest,
                                    producer_sha256=producer_sha256, fixture_sha256=fixture_sha256,
                                    expected_pdf_pending=3, expected_terminal=4,
                                    checkout_sha=args.checkout_sha, locale=locale,
                                    python=platform.python_version(), renderer=pins))
    args.output.mkdir(mode=0o700)
    for locale, (pdf, proof) in retained.items():
        with (args.output / f"{locale}.pdf").open("xb") as stream:
            stream.write(pdf)
        with (args.output / f"{locale}.json").open("x", encoding="utf-8") as stream:
            json.dump(proof, stream, sort_keys=True)
    print("OWNED_PENDING_REVIEW_REPLAY=" + json.dumps({k: v[1] for k, v in retained.items()}, sort_keys=True))

if __name__ == "__main__":
    main()
