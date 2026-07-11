import type {ReactNode} from "react";
import "../styles/globals.css";
import GenericRepositoryExample from "./GenericRepositoryExample";

export const metadata = {
  title: "NICO",
  description: "Neural Intelligence Cyber Operations",
};

export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <html lang="en">
      <body>
        <nav className="global-nav" aria-label="NICO primary navigation">
          <a className="global-brand" href="/easy">NICO</a>
          <div className="global-links">
            <a href="/full-run">Full Assessment</a>
            <a href="/easy">Easy Mode</a>
            <a href="/start-job">Start Job</a>
            <a href="/scanner-workflow">Scanner to Express</a>
            <a href="/refresh-full-evidence">Refresh Evidence</a>
            <a href="/guided-workflow">Guide</a>
            <a href="/">Command Center</a>
          </div>
        </nav>
        <div className="full-run-callout" role="status">
          <b>New:</b> Use <a href="/full-run">Full Assessment</a> for the one-click orchestrated path: scanner worker, evidence attachment, draft scoring, report package, and final human review request. Express PDFs still use the older fast-report path.
        </div>
        <GenericRepositoryExample />
        {children}
      </body>
    </html>
  );
}
