# datasets/ — frozen selections

One JSON per `dataset_id`: which items are in, and the sha256 of each.

**The `dataset_id` is the comparison contract.** Every run records it, and
`make run-compare` refuses to compare two runs that do not share one.

> A metric compared across two different dataset_ids is not a comparison.
> It is a coincidence.

Name it for what it is (`support_tickets_2026q1_v1`), not for what you were
doing (`test2`). Created by `make dataset-create`.
