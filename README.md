# EdgeBench

A benchmark suite for evaluating small language models as on-device agents.

**EdgeBench** is the suite. **EdgeBench-Home** is its smart-home benchmark. New domains can be added as separate benchmark modules without changing the suite name.

[Project website](https://chico-future.github.io/EdgeBench/) · [EdgeBench-Home dataset](https://huggingface.co/datasets/chico-research/EdgeBench-Home) · [Home guide](benchmarks/home/README.md)

## Benchmarks

| Benchmark | Domain | Interfaces | Languages |
| --- | --- | --- | --- |
| [EdgeBench-Home](benchmarks/home/) | Smart-home agents | State-Given, State-Seeking | English, Chinese |

## Quick start

Requires Python 3.10 or newer. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-cloud.txt
```

Obtain dataset access on Hugging Face and download an authorized snapshot. Keep the dataset revision for reproducibility; the data is distributed separately from this repository.

```bash
pip install huggingface_hub
hf download chico-research/EdgeBench-Home --repo-type dataset --local-dir datasets/home
```

Evaluate a model exposed by an OpenAI-compatible endpoint:

```bash
export OPENAI_API_KEY="your-key"
python3 -m cloud.run_state_given   --input datasets/home/en/State-Given/data/DGC.jsonl   --output outputs/home/en/State-Given/DGC.jsonl   --run-id my-model-en-sg-dgc   --base-url http://localhost:8000/v1 --model your-model-id

python3 -m scoring.unified_scorer   --suite-root datasets/home --interface State-Given   --predictions outputs/home/en/State-Given/DGC.jsonl   --output-dir outputs/home/en/State-Given/scores
```

This example runs one family in one language. It is not a full benchmark result. Repeat for all seven families, both interfaces, and both languages. See the [Home guide](benchmarks/home/README.md) for State-Seeking and semantic review.

## Repository

- `benchmarks/`: benchmark descriptions and machine-readable registrations.
- `common/`: shared execution, environment, and output validation.
- `cloud/`, `server/`, `edge/`: API, server, and optional device adapters.
- `scoring/`: deterministic scoring and AIR semantic review.
- `tests/`: synthetic offline checks, with no benchmark records.
- `site/`: the GitHub Pages website.

[Execution and reporting](docs/EXPERIMENT_PROTOCOL.md) · [Architecture](docs/ARCHITECTURE.md) · [Device adapter](docs/RUNBOOK_EDGE.md)

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests do not need dataset access, API credentials, model weights, or an edge device. Hardware execution and live provider compatibility require separate validation.

## License

Code is licensed under [Apache-2.0](LICENSE). The EdgeBench-Home dataset is separately licensed; consult its current dataset card and access terms. This code license does not grant additional rights to the dataset, model weights, or vendor runtimes.
