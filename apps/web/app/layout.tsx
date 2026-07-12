import type {ReactNode} from "react";
import "../styles/globals.css";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import GenericRepositoryExample from "./GenericRepositoryExample";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import ReportPresentationGuard from "./ReportPresentationGuard";
import RetainerAutoEvidenceLauncher from "./RetainerAutoEvidenceLauncher";

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
        <RetainerAutoEvidenceLauncher />
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
            <a href="/retainer-ops">Retainer Ops</a>
            <a href="/easy">Easy Mode</a>
            <a href="/start-job">Start Job</a>
            <a href="/scanner-workflow">Scanner to Express</a>
            <a href="/refresh-full-evidence">Refresh Evidence</a>
            <a href="/guided-workflow">Guide</a>
            <a href="/">Command Center</a>
          </div>
        </nav>
        <div className="full-run-callout" role="status">
          <b>Evidence-bound workflows:</b> Start Express or Mid from the <a href="/">Command Center</a>. Mid review, approval, and controlled delivery remain separate guarded steps. Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually. Operators can verify deployment, readiness, workload, incidents, and alerts in <a href="/operations">Operations</a>, and review interrupted work in <a href="/operations/recovery">Recovery</a>.
        </div>
        <GenericRepositoryExample />
        {children}
        <MidAssessmentCompanion />
        <MidEvidencePacketHelper />
      </body>
    </html>
  );
}
