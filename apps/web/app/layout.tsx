import type {ReactNode} from "react";
import "../styles/globals.css";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import GenericRepositoryExample from "./GenericRepositoryExample";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import ReportPresentationGuard from "./ReportPresentationGuard";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <AssessmentRequestGuard />
        <ReportPresentationGuard />
        <nav className="global-nav" aria-label="NICO primary navigation">
          <a className="global-brand" href="/easy">NICO</a>
          <div className="global-links">
            <a href="/operations">Operations</a>
            <a href="/operations/recovery">Recovery</a>
            <a href="/full-run">Full Assessment</a>
            <a href="/mid-review">Mid Review</a>
            <a href="/mid-report">Mid Report</a>
            <a href="/mid-approval">Mid Approval</a>
            <a href="/mid-delivery-admin">Mid Delivery</a>
            <a href="/easy">Easy Mode</a>
            <a href="/start-job">Start Job</a>
            <a href="/scanner-workflow">Scanner to Express</a>
            <a href="/refresh-full-evidence">Refresh Evidence</a>
            <a href="/guided-workflow">Guide</a>
            <a href="/">Command Center</a>
          </div>
        </nav>
        <div className="full-run-callout" role="status">
          <b>Mid workflow:</b> Start with the unified Express/Mid intake in the <a href="/">Command Center</a>, inspect the admin-authenticated review-by-exception packet in <a href="/mid-review">Mid Review</a>, generate the bound draft in <a href="/mid-report">Mid Report</a>, and decide the exact state in <a href="/mid-approval">Mid Approval</a>. Approval creates a separate approved artifact but does not create a client delivery link. After approval, create an expiring and download-limited link in <a href="/mid-delivery-admin">Mid Delivery</a>. Client downloads require acknowledgement and create integrity-bound receipts. Operators can verify deployment, readiness, workload, incidents, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>.
        </div>
        <GenericRepositoryExample />
        {children}
        <MidAssessmentCompanion />
        <MidEvidencePacketHelper />
      </body>
    </html>
  );
}
