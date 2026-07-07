const gates = [
  ["Technical audit", "Reuse the Express audit as the technical foundation."],
  ["QA review", "Collect iOS/Android critical-flow behavior, bugs, and friction points."],
  ["Platform parity", "Compare feature behavior, UX, and release readiness across platforms."],
  ["Stakeholder inputs", "Capture goals, pain points, desired outcomes, and decision owners."],
  ["Risk register", "Track technical, product, staffing, dependency, and delivery risks."],
  ["Six-month roadmap", "Build milestone, priority, and execution recommendations."],
  ["Resourcing plan", "Recommend Product Engineering Architect, Mobile Product Engineer, and Product Quality coverage."],
  ["Executive review", "Prepare a strategy packet for final human presentation."],
];

export default function MidEvidencePage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Mid Evidence</p>
        <h1>Evidence gates for reaching the 85% Mid target</h1>
        <p className="lead">This page maps the Mid Technical Health Assessment requirements into evidence gates. NICO can prepare the packets, but stakeholder interviews and final roadmap judgment remain human-controlled.</p>
        <div className="hero-actions"><a href="/operator" className="primary-link">Operator Hub</a><a href="/coverage-gaps" className="secondary-link">Coverage Gaps</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Mid Target</p><h2>Max 85%</h2></div><span className="status blue">Human judgment required</span></div>
        <div className="results-grid">
          {gates.map(([title, detail]) => (
            <article className="result-card" key={title}>
              <div className="result-head"><b>{title}</b><span className="status gray">Evidence gate</span></div>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
