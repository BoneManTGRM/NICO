import type {ReactNode} from "react";
import {Geist, Geist_Mono} from "next/font/google";
import "../styles/globals.css";
import "../styles/navigation.css";
import "../styles/score-assurance.css";
import "../styles/assessment-executive.css";
import "../styles/professional-polish.css";
import "../styles/site-polish-v2.css";
import "../styles/workflow-simplification.css";
import "../styles/assessment-terminal-mobile.css";
import "../styles/assessment-mobile-stability.css";
import "../styles/assessment-recovery-overlay.css";
import "../styles/assessment-failure-terminal.css";
import AssessmentActiveRunReset from "./AssessmentActiveRunReset";
import AssessmentApiTransportBridge from "./AssessmentApiTransportBridge";
import AssessmentExactCommitTransport from "./AssessmentExactCommitTransport";
import AssessmentExpressRecoveryActions from "./AssessmentExpressRecoveryActions";
import AssessmentExpressRecoveryGuard from "./AssessmentExpressRecoveryGuard";
import AssessmentFailureEvidencePanel from "./AssessmentFailureEvidencePanel";
import AssessmentFailureResponseBridge from "./AssessmentFailureResponseBridge";
import AssessmentFinalGateAuthoritativeGuard from "./AssessmentFinalGateAuthoritativeGuard";
import AssessmentFinalReviewAction from "./AssessmentFinalReviewAction";
import AssessmentHomeRedirect from "./AssessmentHomeRedirect";
import AssessmentMarkdownCopyBridge from "./AssessmentMarkdownCopyBridge";
import AssessmentProgressIntegrityGuard from "./AssessmentProgressIntegrityGuard";
import AssessmentRecoveryActions from "./AssessmentRecoveryActions";
import AssessmentRequestGuard from "./AssessmentRequestGuard";
import AssessmentReviewPdfDownload from "./AssessmentReviewPdfDownload";
import AssessmentRunStateGuard from "./AssessmentRunStateGuard";
import AssessmentScoreAssuranceGuard from "./AssessmentScoreAssuranceGuard";
import AssessmentStatusOutcomeGuard from "./AssessmentStatusOutcomeGuard";
import AssessmentStatusResilience from "./AssessmentStatusResilience";
import ComprehensiveStuckRunRecovery from "./ComprehensiveStuckRunRecovery";
import GenericRepositoryExample from "./GenericRepositoryExample";
import LegacyFullRunRedirect from "./LegacyFullRunRedirect";
import {MidWorkspaceProvider} from "./MidWorkspaceContext";
import OperationsPreloadGuard from "./OperationsPreloadGuard";
import PrimaryNavigation from "./PrimaryNavigation";
import ReportPresentationGuard from "./ReportPresentationGuard";
import RetainerAutoEvidenceLauncher from "./RetainerAutoEvidenceLauncher";
import UnifiedAssessmentPublicGuard from "./UnifiedAssessmentPublicGuard";
import WorkflowCallout from "./WorkflowCallout";
import WorkspaceClarityRepair from "./WorkspaceClarityRepair";

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

/*
Canonical public workflow:
Assessment workflow: Run one unified NICO assessment from href="/assessment?tier=comprehensive#assessment".
The assessment captures one immutable commit and continues through required human review.
NICO never approves findings or creates client delivery automatically.
Guidance remains under More → Guide.
Operator-only deployment controls are hidden from normal assessment navigation.
Ongoing evidence refresh remains a post-acceptance operator workflow.

Legacy source-level compatibility contracts retained for stored links, historical tests, and hidden routes only:
Start Express or Comprehensive from href="/assessment?tier=express#assessment".
Operator-only deployment controls are available under More → Operations (Admin).
Ongoing evidence refresh remains under More → Retainer Ops.
These strings do not restore the retired public selector; UnifiedAssessmentPublicGuard forces the one Strategic lifecycle.
*/

export const metadata = {
  title: "NICO",
  description: "Evidence-bound technical assessments with human-reviewed and authorized automated delivery modes.",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable}`}>
      <body className="nico-app">
        <MidWorkspaceProvider>
          <AssessmentActiveRunReset />
          <ComprehensiveStuckRunRecovery />
          <AssessmentRunStateGuard />
          <AssessmentStatusResilience />
          <AssessmentStatusOutcomeGuard />
          <AssessmentExpressRecoveryGuard />
          <AssessmentProgressIntegrityGuard />
          <AssessmentFinalGateAuthoritativeGuard />
          <AssessmentApiTransportBridge />
          <AssessmentExactCommitTransport />
          <AssessmentFailureResponseBridge />
          <AssessmentReviewPdfDownload />
          <AssessmentMarkdownCopyBridge />
          <AssessmentHomeRedirect />
          <LegacyFullRunRedirect />
          <AssessmentRequestGuard />
          <ReportPresentationGuard />
          <AssessmentScoreAssuranceGuard />
          <OperationsPreloadGuard />
          <RetainerAutoEvidenceLauncher />
          <WorkspaceClarityRepair />
          <UnifiedAssessmentPublicGuard />
          <AssessmentFinalReviewAction />
          <PrimaryNavigation />
          <WorkflowCallout />
          <GenericRepositoryExample />
          <AssessmentFailureEvidencePanel />
          <AssessmentExpressRecoveryActions />
          <AssessmentRecoveryActions />
          {children}
        </MidWorkspaceProvider>
      </body>
    </html>
  );
}
