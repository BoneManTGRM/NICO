const services = [
  {
    title: "Express",
    target: "95%",
    gaps: ["human review", "client acceptance", "final rerun evidence"],
  },
  {
    title: "Mid",
    target: "85%",
    gaps: ["QA evidence", "platform parity", "stakeholder inputs", "six-month roadmap"],
  },
  {
    title: "Retainer",
    target: "70%",
    gaps: ["backlog cadence", "release tracking", "blocker owners", "weekly status"],
  },
  {
    title: "Client-ready",
    target: "85%",
    gaps: ["Postgres persistence", "approved final review", "rerun", "green acceptance"],
  },
];

export default function CoverageGapsPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Coverage Gaps</p>
        <h1>Control system for reaching max coverage</h1>
        <p className="lead">This page defines the missing evidence gates for each service tier. The goal is to move toward max coverage without inflating technical maturity or pretending human/client approval exists.</p>
        <div className="hero-actions"><a href="/operator" className="primary-link">Operator Hub</a><a href="/setup-actions" className="secondary-link">Setup Actions</a><a href="/coverage-targets" className="secondary-link">Max Targets</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Targets</p><h2>Gap map by service tier</h2></div><span className="status blue">Evidence-bound</span></div>
        <div className="results-grid">
          {services.map((service) => (
            <article className="result-card" key={service.title}>
              <div className="result-head"><b>{service.title}</b><span className="status gray">Max {service.target}</span></div>
              <h3>Remaining gates</h3>
              <ul className="tight-list">
                {service.gaps.map((gap) => <li key={gap}>{gap}</li>)}
              </ul>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
