import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge";
import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel";
import AssessmentHomeRedirect from "./AssessmentHomeRedirect";
import AssessmentMidLiveStatusTransport from "./AssessmentMidLiveStatusTransport";
import AssessmentRecoveryActions from "./AssessmentRecoveryActions";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import AssessmentSavedMidRunGuard from "./AssessmentSavedMidRunGuard";
import AssessmentStatusOutcomeGuard from "./AssessmentStatusOutcomeGuard";
import AssessmentStatusResilience from "./AssessmentStatusResilience";
import GenericRepositoryExample from "./GenericRepositoryExample";
import LegacyFullRunRedirect from "./LegacyFullRunRedirect";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import {MidWorkspaceProvider} from "./MidWorkspaceContext";
import OperationsPreloadGuard from "./OperationsPreloadGuard";
import PrimaryNavigation from "./PrimaryNavigation";
import ReportPresentationGuard from "./ReportPresentationGuard";
import RetainerAutoEvidenceLauncher from "./RetainerAutoEvidenceLauncher";
import UnifiedMidTokenCapture from "./UnifiedMidTokenCapture";
import WorkflowCallout from "./WorkflowCallout";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <MidWorkspaceProvider>
          <AssessmentStatusResilience />
          <AssessmentSavedMidRunGuard />
          <AssessmentStatusOutcomeGuard />
          <AssessmentMidLiveStatusTransport />
          <AssessmentApiTransportBridge />
          <AssessmentHomeRedirect />
          <LegacyFullRunRedirect />
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <OperationsPreloadGuard />
          <UnifiedMidTokenCapture />
          <RetainerAutoEvidenceLauncher />
          <PrimaryNavigation />
          <WorkflowCallout>
            <div className="full-run-callout" role="status">
              <b>Assessment workflow:</b> Start Express, Mid, or Full from the <a href="/assessment?tier=express#assessment">unified assessment page</a>. One Run action completes every automated stage available for the selected tier. Mid and Full continue through repository evidence, scanners, scoring, and report preparation, then stop at required human review. NICO never approves findings or creates client delivery automatically. Approval creates a separate approved artifact but does not create a client delivery link. Client downloads require acknowledgement and create integrity-bound receipts. Operators can verify deployment, readiness, workload, incidents, backup/restore evidence, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>. <b>Retainer workflow:</b> Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually.
            </div>
          </WorkflowCallout>
          <GenericRepositoryExample />
          <AssessmentFailureEvidencePanel />
          <AssessmentRecoveryActions />
          {children}
          <MidAssessmentCompanion />
          <MidEvidencePacketHelper />
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
