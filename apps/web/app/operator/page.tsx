const cards = [
  {
    title: "Command Center",
    href: "/",
    status: "Start here",
    detail: "Run Express, scanner worker, repair suggestions, approvals, and report package workflows.",
  },
  {
    title: "Coverage Targets",
    href: "/coverage-targets",
    status: "Max goals",
    detail: "View the upper-end targets: Express 95%, Mid 85%, Retainer 70%, and client-ready 85%.",
  },
  {
    title: "Setup Readiness",
    href: "/setup-readiness",
    status: "Checklist",
    detail: "Verify frontend, backend, persistence, run ID, review link, approval, rerun, and completion gates.",
  },
  {
    title: "Setup Actions",
    href: "/setup-actions",
    status: "Ordered fixes",
    detail: "Follow the priority sequence for Vercel, Railway, Postgres, Express rerun, and final review gates.",
  },
  {
    title: "Final Review",
    href: "/final-review",
    status: "Human gate",
    detail: "Request, approve, reject, or ask for more evidence before client-facing delivery.",
  },
];

export default function OperatorHubPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Operator Hub</p>
        <h1>One launch point for max-coverage setup</h1>
        <p className="lead">Use this page to move through the live workflow in the right order: run the audit, verify setup, complete final review, rerun, then check whether the system can truthfully operate near the upper-end service targets.</p>
        <div className="hero-actions"><a href="/" className="primary-link">Open Command Center</a><a href="/setup-actions" className="secondary-link">Next setup actions</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Workflow Map</p><h2>Operator pages</h2></div><span className="status blue">Evidence-bound</span></div>
        <div className="results-grid">
          {cards.map((item) => (
            <a className="result-card" href={item.href} key={item.title}>
              <div className="result-head"><b>{item.title}</b><span className="status gray">{item.status}</span></div>
              <p>{item.detail}</p>
            </a>
          ))}
        </div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Correct sequence</p><h2>Max-coverage path</h2></div><span className="status yellow">Manual gates remain</span></div>
        <ol className="tight-list">
          <li>Confirm Vercel points to the Railway backend.</li>
          <li>Confirm backend health is ok.</li>
          <li>Confirm Postgres persistence is active.</li>
          <li>Run Express and copy the generated run ID / final-review link.</li>
          <li>Request and complete final review after human evidence review.</li>
          <li>Rerun Express so acceptance evidence can apply to the report.</li>
          <li>Check Coverage Targets and Express Service Completion separately from technical maturity.</li>
        </ol>
      </section>
    </main>
  );
}
