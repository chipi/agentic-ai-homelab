# runs/ — individual results

One directory per run: `metrics.json` and `predictions.jsonl`.

`metrics.json` carries the three things that make a number mean something —
`dataset_id` (what it measured), `config_id` (the instrument), and `build`
(the system under test). A run missing any of them cannot be attributed, and
`make validate` fails on it.

Gitignored by default. Commit the ones you promote (see `baselines/`), not every
experiment.
