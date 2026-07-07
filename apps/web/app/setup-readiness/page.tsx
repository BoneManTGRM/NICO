const checks = [
  ["Frontend deployed", "Confirm https://app.nicoaudit.com loads."],
  ["Backend URL configured", "Set NEXT_PUBLIC_NICO_API_URL in Vercel."],
  ["Backend online", "Confirm the Railway /health endpoint returns ok."],
  ["Persistent storage active", "Configure DATABASE_URL and confirm /storage/status shows persistence_available=true."],
  ["Run ID available", "Rerun Express so the result includes a stable run_id."],
  ["Final-review link available", "Use the generated /final-review link from the Express result."],
  ["Final review requested", "Create the review record from /final-review."],
  ["Final review approved", "Human reviewer approves after checking evidence and unavailable-data notes."],
  ["Acceptance green after rerun", "Rerun Express after approval so Client / Human Acceptance can turn green."],
  ["Express completion present", "Attach Express Service Completion to the returned result."],
];

export default function SetupReadinessPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Setup Readiness</p>
        <h1>Checklist for reaching max service coverage</h1>
        <p className="lead">These are the deployment, storage, review, and rerun gates that must be complete before NICO can truthfully operate near the max target numbers.</p>
        <div className="hero-actions"><a href="/" className="secondary-link">Back to Command Center</a><a href="/coverage-targets" className="secondary-link">Coverage targets</a><a href="/final-review" className="secondary-link">Final review</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Setup Gates</p><h2>Max target readiness</h2></div><span className="status blue">Human review required</span></div>
        <div className="results-grid">
          {checks.map(([title, detail], index) => (
            <article className="result-card" key={title}>
              <div className="result-head"><b>{index + 1}. {title}</b><span className="status gray">Verify</span></div>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
