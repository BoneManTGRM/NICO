# Embedded-font evidence section flow

The final report worker installs ReportLab's bundled Vera TrueType faces under Helvetica aliases before importing the application. This changes real paragraph widths and wrapping. The layout-polish installer replaces the base sparse renderer, and its renderer previously kept only the section heading with its first paragraph. Consequently a short evidence section could begin on one page and leave its last evidence bullet on the next page. Test ordering merely exposed the production font configuration; reverting global fonts in tests would conceal the product issue.

Before the fix, installing embedded fonts and then running the existing sparse heading/evidence regression reproduced heading page0 versus final evidence page1. Running the same test alone with Base-14 fonts passed. Independent review reproduced the font-first failure. The exact fixture has189.9 points of wrapped height plus paragraph spacing with embedded fonts. An initial180-point grouping experiment therefore did not fix it; that failure was retained.

The polished renderer now measures titled Evidence/Evidencia sections at the actual frame width, including paragraph spacing. Sections no taller than216 points (three inches, below one-third of usable page height) keep their paragraphs together. Larger sections continue to flow. The leading spacer stays outside the section, and the last paragraph is never chained to the following section. Fonts, sizes, wording, scores, approval gates, original assertions and overall page-budget checks are unchanged.

Validation on Python3.12 with installed ReportLab5.0.1:29 tests passed across embedded-font, layout-polish, new bilingual section-flow, sparse-flow/page-budget, and literal-preservation files. No offline guard events. New tests explicitly install production font aliases; they preserve the original regression and cover short and oversized ordinary sections in English/es-MX. Poppler text-box checks passed for containment and non-overlap. Existing page-budget, protected-stream preservation and effective-font-size checks passed. These are synthetic local PDF tests, not comprehensive production report acceptance.

Command (from the isolated worktree, using the existing offline synthetic runner):

```bash
env -i PATH=/workspace/nico-venv/bin:/usr/bin:/bin \
  PYTHONPATH=/workspace/NICO-pdf-font-fix \
  NICO_HOME=/tmp/fontfix-tests2 NICO_SQLITE_PATH=/tmp/fontfix-tests2/nico.sqlite3 \
  timeout 60 /workspace/nico-venv/bin/python /tmp/nico-panel-synthetic-tests.py -q \
  tests/test_comprehensive_pdf_embedded_fonts_v1.py \
  tests/test_comprehensive_pdf_layout_polish_v1.py \
  tests/test_embedded_font_evidence_section_flow.py \
  tests/test_sparse_reflow_section_flow.py \
  tests/test_bilingual_reflow_literal_preservation_v1.py
```

Independent post-fix review found no blocking defect and separately passed14 embedded-font/layout/new-regression tests with no guard events.

PR1869 target ReportLab5.1.0, FastAPI0.162.0 and Pydantic2.14.2 remain unavailable here. Repeat these checks under that exact dependency set before claiming upgrade compatibility. No dependency installation, publication, merge, deployment, sandbox change or acceptance-check weakening occurred.
