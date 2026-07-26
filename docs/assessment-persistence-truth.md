# Assessment persistence truth

Writable storage is not sufficient evidence of durability. NICO only permits production assessment creation when the run store is backed by Postgres or by a mounted volume explicitly proven to survive container replacement.
