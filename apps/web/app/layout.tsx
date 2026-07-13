import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import GenericRepositoryExample from "./GenericRepositoryExample";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import {MidWorkspaceProvider} from "./MidWorkspaceContext";
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
        <MidWorkspaceProvider>
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <RetainerAutoEvidenceLauncher />
          <PrimaryNavigation />
          <div className="full-run-callout" role="status">
            <b>Mid workflow:</b> Use the guided <a href="/mid-assessment">Mid Assessment workspace</a> to keep one exact run and move through Start, Review, Report, Approval, and controlled Delivery. Approval creates a separate approved artifact but does not create a client delivery link. Client downloads require acknowledgement and create integrity-bound receipts. Operators can verify deployment, readiness, workload, incidents, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>. <b>Retainer workflow:</b> Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually.
          </div>
          <GenericRepositoryExample />
          {children}
          <MidAssessmentCompanion />
          <MidEvidencePacketHelper />
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
