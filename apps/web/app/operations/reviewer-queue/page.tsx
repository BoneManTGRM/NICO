import ReviewerWorkspace from "./ReviewerWorkspace";

export const metadata = {
  title: "Human review workspace | NICO",
  description: "Exception-first canonical candidate review, complete filtering and search, controlled bulk disposition, configurable quality control, evidence requests, assignments, audit trail, and empirical reviewer-time measurement.",
};

export default function ReviewerQueuePage() {
  return <ReviewerWorkspace />;
}
