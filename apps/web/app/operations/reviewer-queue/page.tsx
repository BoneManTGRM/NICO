import ReviewerQueue from "./ReviewerQueue";
import ReviewWorkPanel from "./ReviewWorkPanel";

export const metadata = {
  title: "Human review workspace | NICO",
  description: "Exception-first canonical candidate review, authorized disposition, quality control, evidence requests, assignments, audit trail, and empirical reviewer-time measurement.",
};

export default function ReviewerQueuePage() {
  return <>
    <ReviewerQueue />
    <ReviewWorkPanel />
  </>;
}
