# Verified final report timeout root cause

Production run `comprun_33925b5a68994333ab148ec925d5bd2f` on exact release `f457ed47fc374358fe47e23128066c771db4f261` failed at 82.61 percent after 908.093 seconds.

The retained backend diagnostic is `background_stage_execution_timeout`, not the earlier completed-analyzer semantic contradiction.

The final report was still routed through the generic detached background mechanism. Its context included all retained stages, and final rendering performed repeated scanner-truth and recursive evidence processing before the report package could be atomically attached to the canonical run.

The continuation removes final publication from that mechanism and bounds the large-evidence processing that precedes rendering. It does not weaken artifact validation or human approval.
