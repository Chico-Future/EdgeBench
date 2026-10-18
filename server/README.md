# Server adapter

Run an OpenAI-compatible inference server using its own installation guide, then point the public cloud runner at its `/v1` endpoint. The adapter shares the EdgeBench-Home task contracts with API and optional device runs.

```bash
python3 -m cloud.run_state_given --help
python3 -m cloud.run_state_seeking --help
```

The server, model weights, tokenizer, and runtime are intentionally external to this repository. Record their versions and generation settings with any published evaluation.
