const gates = [
  ["Persistent storage", "Storage must survive backend restarts."],
  ["Stable run ID", "The report needs a fixed run scope."],
  ["Final-review link", "Use a run-scoped review link."],
  ["Review requested", "Create the review record."],
  ["Review approved", "Human review must approve the final package."],
  ["Rerun after approval", "Rerun so approval evidence can apply."],
  ["Acceptance green", "Client / Human Acceptance must be green."],
  ["Report exports", "Export the final package."],
  ["Delivery notes", "Attach notes and unavailable-data disclosure."],
];

export default function ClientReadyPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Client Ready</p>
        <h1>Evidence gates for the 85% client-ready target</h1>
        <p className="lead">This page shows the required delivery gates. NICO can prepare the package, but review and acceptance stay human-controlled.</p>
        <div className="hero-actions"><a href="/operator" className="primary-link">Operator Hub</a><a href="/coverage-gaps" className="secondary-link">Coverage Gaps</a><a href="/final-review" className="secondary-link">Final Review</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Client Ready Target</p><h2>Max 85%</h2></div><span className="status blue">Review required</span></div>
        <div className="results-grid">
          {gates.map(([title, detail]) => (
            <article className="result-card" key={title}>
              <div className="result-head"><b>{title}</b><span className="status gray">Gate</span></div>
              <p>{detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
