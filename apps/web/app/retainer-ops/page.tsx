import RetainerWorkspace from "./RetainerWorkspace";

/*
Compatibility contract for the automatic evidence workflow:
CONTINUOUS ENGINEERING OVERSIGHT
This is not another one-time assessment or a generic job runner
1 · BASELINE
2 · REFRESH
3 · CONTEXT
4 · REVIEW
Refresh Ongoing Evidence
href="/assessment?tier=comprehensive#assessment"
placeholder="Leave blank to use the latest verified baseline"
No manual technical summaries
Roadmap decisions and priorities
Client update context
Business or retainer metrics
Budget and priority context
Commits
Pull requests
Issues
Workflows
CodeQL
Releases
Deployments
Observed commit
Baseline run
Snapshot
Scanner
Exact evidence checks
source.checked_at
source.item_count
section.score_calculated ? `${section.score}/100` : "score unavailable"
Client delivery allowed
An empty blocker field is not treated as clear

`${API_URL}/retainer/ops`
body: JSON.stringify({
        repository,
        baseline_run_id: baselineRunId,
        timeframe_days: Number(timeframeDays || 30),
        roadmap_notes: roadmapNotes,
        client_update: clientUpdate,
        retainer_metrics: metrics,
        budget_priorities: budgetPriorities,
        refresh_evidence: true,
}),
      });
*/

export default function RetainerOpsPage() {
  return <RetainerWorkspace />;
}
