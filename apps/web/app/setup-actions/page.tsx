const actions = [
  {
    title: "1. Connect frontend to backend",
    detail: "Set NEXT_PUBLIC_NICO_API_URL in Vercel to the Railway backend URL, then redeploy.",
    priority: "Critical",
  },
  {
    title: "2. Confirm backend health",
    detail: "Open the Railway backend /health endpoint and confirm status is ok.",
    priority: "Critical",
  },
  {
    title: "3. Activate persistence",
    detail: "Attach Postgres, set DATABASE_URL, redeploy, and confirm /storage/status shows persistence_available=true.",
    priority: "Critical",
  },
  {
    title: "4. Rerun Express",
    detail: "Run Express and confirm the result includes run_id and final_review.url.",
    priority: "High",
  },
  {
    title: "5. Complete final review",
    detail: "Open /final-review, request review, approve only after human evidence review, then rerun Express.",
    priority: "High",
  },
];

export default function SetupActionsPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">NICO Setup Actions</p>
        <h1>Ordered actions to unlock max service coverage</h1>
        <p className="lead">Use this page after Setup Readiness. It gives the next operational actions in priority order so the live app can move toward the max target workflow without faking acceptance or persistence.</p>
        <div className="hero-actions"><a href="/" className="secondary-link">Back to Command Center</a><a href="/setup-readiness" className="secondary-link">Setup Readiness</a><a href="/final-review" className="secondary-link">Final Review</a></div>
      </section>

      <section className="section panel">
        <div className="section-head"><div><p className="eyebrow">Action Plan</p><h2>Critical setup sequence</h2></div><span className="status blue">Human gates preserved</span></div>
        <div className="results-grid">
          {actions.map((item) => (
            <article className="result-card" key={item.title}>
              <div className="result-head"><b>{item.title}</b><span className="status yellow">{item.priority}</span></div>
              <p>{item.detail}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
