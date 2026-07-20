import type {ReactNode} from "react";
import "../styles/globals.css";
import "../styles/navigation.css";
import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge";
import AssessmentExpressRecoveryActions from "./AssessmentExpressRecoveryActions";
import AssessmentExpressRecoveryGuard from "./AssessmentExpressRecoveryGuard";
import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel";
import AssessmentFinalGateAuthoritativeGuard from "./AssessmentFinalGateAuthoritativeGuard";
import AssessmentHomeRedirect from "./AssessmentHomeRedirect";
import AssessmentMidLiveStatusTransport from "./AssessmentMidLiveStatusTransport";
import AssessmentProgressIntegrityGuard from "./AssessmentProgressIntegrityGuard";
import AssessmentRecoveryActions from "./AssessmentRecoveryActions";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import AssessmentRunStateGuard from "./AssessmentRunStateGuard";
import AssessmentSavedMidRunGuard from "./AssessmentSavedMidRunGuard";
import AssessmentStatusOutcomeGuard from "./AssessmentStatusOutcomeGuard";
import AssessmentStatusResilience from "./AssessmentStatusResilience";
import GenericRepositoryExample from "./GenericRepositoryExample";
import LegacyFullRunRedirect from "./LegacyFullRunRedirect";
import MidAssessmentCompanion from "./MidAssessmentCompanion";
import MidEvidencePacketHelper from "./MidEvidencePacketHelper";
import MidScoreIntelligencePortal from "./MidScoreIntelligencePortal";
import MidSectionReviewPortal from "./MidSectionReviewPortal";
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
          <AssessmentRunStateGuard />
          <AssessmentStatusResilience />
          <AssessmentSavedMidRunGuard />
          <AssessmentStatusOutcomeGuard />
          <AssessmentExpressRecoveryGuard />
          <AssessmentMidLiveStatusTransport />
          <AssessmentProgressIntegrityGuard />
          <AssessmentFinalGateAuthoritativeGuard />
          <MidScoreIntelligencePortal />
          <MidSectionReviewPortal />
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
              <b>Assessment workflow:</b> Start Express or Comprehensive from the <a href="/assessment?tier=express#assessment">assessment workspace</a>. Express provides a fast evidence-bound baseline. Comprehensive captures one immutable commit and continues the same native run through repository evidence, scanners, technical and business-context modules, report generation, and required human review. NICO never approves findings or creates client delivery automatically. Operators can verify deployment, readiness, workload, incidents, backup/restore evidence, and alerts in the <a href="/operations">Operations</a> control center, and review interrupted scanner work in <a href="/operations/recovery">Recovery</a>. <b>Retainer workflow:</b> Run ongoing repository, workflow, release, backlog, and blocker evidence through <a href="/retainer-ops">Retainer Ops</a>; only business context GitHub cannot prove is entered manually.
            </div>
          </WorkflowCallout>
          <GenericRepositoryExample />
          <AssessmentFailureEvidencePanel />
          <AssessmentExpressRecoveryActions />
          <AssessmentRecoveryActions />
          {children}
          <MidAssessmentCompanion />
          <MidEvidencePacketHelper />
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
