# Batch B — score and CI presentation integrity

This batch enforces two report-level invariants before PDF rendering:

- score contributions use proportional geometry metadata instead of glyph bars; a contribution of 0 has zero width, 1/6 is visibly short, and 6/6 uses full width;
- CI status labels are canonicalized, emitted once, and reconciled so the category sum equals the reported total.

Detailed non-success categories replace the aggregate `non-success` bucket to prevent double counting. When only the aggregate is available, it remains explicit and the residual is represented once as `other/unknown`.

The regression suite covers geometry values, glyph removal, metadata, duplicate-label elimination, aggregate-versus-detailed category behavior, and the category-sum invariant. Human review and client-delivery blocking remain unchanged.
