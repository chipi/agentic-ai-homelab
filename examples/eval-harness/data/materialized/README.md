# materialized/ — derived run inputs

Built by `make dataset-materialize` from `sources/` + the dataset, with every
hash re-verified on the way in.

**Entirely regenerable.** Delete it whenever; rebuild with one command. If
something here cannot be regenerated, it is in the wrong directory — it belongs
in `sources/`.

Gitignored by default: it is derived, and it can be large.
