const targets = [
  {
    title: "Express Technical Health Assessment",
    max: "95%",
    previousRange: "90-95%",
    note: "Max scanner/report automation target with human review and client acceptance still required.",
  },
  {
    title: "Mid Technical Health Assessment",
    max: "85%",
    previousRange: "75-85%",
    note: "Max QA, parity, stakeholder, roadmap, and risk-planning support target.",
  },
  {
    title: "Ongoing Product Engineering Retainer",
    max: "70%",
    previousRange: "55-70%",
    note: "Max backlog, sprint, release, blocker, and approval-workflow support target.",
  },
  {
    title: "Full client-ready replacement",
    max: "85%",
    previousRange: "75-85%",
    note: "Max client-ready package target after human validation and accepted review evidence.",
  },
];

export default function CoverageTargetsPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Coverage Targets</p>
        <h1>Maximum evidence-bound service goals</h1>
        <p className="lead">These are the upper-end targets for each service tier. They are goals, not automatic claims. Human review and client acceptance still control final delivery.</p>
        <div className="hero-actions"><a href="/" className="secondary-link">Back to Command Center</a></div>
      </section>

      <section className="section panel status-panel">
        <div className="section-head"><div><p className="eyebrow">Max Targets</p><h2>Upper-end numbers only</h2></div><span className="status blue">Human review required</span></div>
        <div className="grid four target-grid">
          {targets.map((item) => (
            <article key={item.title}>
              <b>{item.title}</b>
              <span className="target-number">{item.max}</span>
              <small>Previous range: {item.previousRange}</small>
              <small>{item.note}</small>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
