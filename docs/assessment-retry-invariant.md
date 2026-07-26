# Assessment retry invariant

Retry before run creation repeats readiness. Retry after run creation reads and continues the exact existing run. It never emits a second intake merely because status was temporarily unavailable.
