import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import GenericRepositoryExample from "./GenericRepositoryExample";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import PrimaryNavigation from "./PrimaryNavigation";
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
        <PrimaryNavigation />
        <div className="full-run-callout" role="status">
          <b>Mid workflow:</b> Start with the unified Express/Mid intake in the <a href="/">Command Center</a>, inspect the admin-authenticated review-by-exception packet in <a href="/mid-review">Mid Review</a>, generate the bound draft in <a href="/mid-report">Mid Report</a>, and decide the exact state in <a href="/mid-approval">Mid Approval</a>. Approval creates a separate approved artifact but does not create a client delivery link. After approval, create an expiring and download-limited link in <a href="/mid-delivery-admin">Mid Delivery</a>. Client downloads require acknowledgement and create integrity-bound receipts. Operators can verify deployment, readiness, workload, incidents, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>. <b>Retainer workflow:</b> Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually.
        </div>
        <GenericRepositoryExample />
        {children}
        <MidAssessmentCompanion />
        <MidEvidencePacketHelper />
      </body>
    </html>
  );
}
