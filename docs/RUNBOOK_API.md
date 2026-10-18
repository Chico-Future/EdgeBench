# API execution

Use `python3 -m cloud.run_state_given --help` or `python3 -m cloud.run_state_seeking --help`. Commands and dataset paths are shown in the [Home guide](../benchmarks/home/README.md).

The endpoint must implement OpenAI-compatible chat completions. Supply the base URL, model identifier, and an environment variable containing credentials. Credentials are not committed. Configure request timeouts and output budgets explicitly for formal runs. Availability of sampling parameters varies by provider.

Optional YAML model configuration is supported through `--models-file` and `--model-key`; replace the example values with your own endpoint settings. Do not commit private endpoint configurations.
