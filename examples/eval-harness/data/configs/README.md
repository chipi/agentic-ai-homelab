# configs/ — experiment definitions

One YAML per arm. Required: `config_id` and `dataset_id`. Everything under
`params` is handed to `run_item()` untouched — model, temperature, prompt
version, thresholds.

An arm is a config. To compare two things, write two configs against the SAME
`dataset_id` and run both.
