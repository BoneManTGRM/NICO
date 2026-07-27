from pathlib import Path

path = Path("apps/web/app/assessment/AssessmentWorkspace.tsx")
source = path.read_text(encoding="utf-8")
block = '''  const reviewAction = result?.run_id && (phase === "review_required" || internalReview.completed)
    ? <a
      className={workspaceStyles.internalReviewAction}
      data-assessment-internal-review="true"
      href={internalReviewHref}
    >{internalReview.approved ? copy.openReviewRecord : copy.openInternalReview}</a>
    : null;
'''
if source.count(block) != 2:
    raise SystemExit(f"expected exactly two duplicate reviewAction blocks, found {source.count(block)}")
source = source.replace(block + "\n" + block, block, 1)
path.write_text(source, encoding="utf-8")
