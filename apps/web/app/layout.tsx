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
            <a href="/easy">Easy Mode</a>
            <a href="/start-job">Start Job</a>
            <a href="/scanner-workflow">Scanner to Express</a>
            <a href="/refresh-full-evidence">Refresh Evidence</a>
            <a href="/guided-workflow">Guide</a>
            <a href="/">Command Center</a>
          </div>
        </nav>
        <GenericRepositoryExample />
        {children}
      </body>
    </html>
  );
}
