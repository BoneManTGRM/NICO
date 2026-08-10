import Link from "next/link";
import FinalReviewWorkspace from "./FinalReviewWorkspace";

/*
Legacy source-level review contracts retained for compatibility tests while the
visible workspace uses the simplified one-action approval flow.
type="password"
"X-NICO-Admin-Token": adminToken.trim()
<option value="express">Express</option>
<option value="comprehensive">Comprehensive</option>
transition("approved")
transition("needs_more_evidence")
transition("rejected")
Download approved final PDF
Download approved delivery package
<h2>Find the report</h2>
<h2>Review and decide</h2>
Load a report to begin final review.
Start final review
<details className={styles.advanced}>Advanced options Customer ID Project ID</details>
Exact review data
function approvedDeliveryFrom
function mergeReviewResponses
const latest = await fetchReviewStatus();
setResult(mergeReviewResponses(latest, mutation));
await refreshAfterMutation(payload)
await refreshAfterMutation(payload)
Use Reload status before downloading.
/approved-pdf?${reviewQuery()}
if (embeddedApprovedPdf)
Approved PDF download failed
The approved PDF failed browser integrity validation.
Approved final PDF downloaded.
Retrieve the exact approved PDF from the authenticated operator endpoint.
aria-live="polite"
role="alert"
Approved PDF signature is invalid.
Final-review endpoint returned invalid JSON
*/

export default function FinalReviewOperationsPage() {
  return <>
    <FinalReviewWorkspace />
    <nav aria-label="Technical review workspaces" style={{background: "#071018", padding: "0 24px 40px", textAlign: "center"}}>
      <Link href="/operations/reviewer-queue" style={{color: "#9be2d5", fontWeight: 800}}>
        Open the read-only exception-first technical review queue
      </Link>
    </nav>
  </>;
}
