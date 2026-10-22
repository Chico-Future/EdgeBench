# EdgeBench

[![Tests](https://github.com/Chico-Future/EdgeBench/actions/workflows/ci.yml/badge.svg)](https://github.com/Chico-Future/EdgeBench/actions/workflows/ci.yml)
[![Hugging Face Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-EdgeBench--Home-yellow)](https://huggingface.co/datasets/chico-research/EdgeBench-Home)
[![License: Apache 2.0](https://img.shields.io/badge/Code-Apache--2.0-blue.svg)](LICENSE)

**EdgeBench** is an extensible benchmark suite for evaluating language models as agents in practical environments. **EdgeBench-Home** is the first benchmark in the suite, focused on bilingual smart-home tasks.

[Website](https://chico-future.github.io/EdgeBench/) · [EdgeBench-Home website](https://chico-future.github.io/EdgeBench/home/) · [Dataset on Hugging Face](https://huggingface.co/datasets/chico-research/EdgeBench-Home) · [Home benchmark guide](benchmarks/home/README.md)

## What is included

EdgeBench-Home evaluates seven task families through two interfaces:

| Task family | Description |
| --- | --- |
| DGC | Device Grounding and Control |
| MSC | Multi-device Selection and Control |
| AIR | Ambiguity and Intent Resolution |
| FAR | Future Automation Registration |
| DCR | Dialogue-context Resolution |
| PMU | Personalized Memory Use |
| REQ | Read-only Environment Queries |

- **State-Given:** the model receives the relevant context and produces a response.
- **State-Seeking:** the model starts with partial observations and interacts with a simulated environment.
- **Bilingual evaluation:** English and Chinese tracks are distributed through the [EdgeBench-Home dataset](https://huggingface.co/datasets/chico-research/EdgeBench-Home).
- **Task-level scoring:** the scorer checks actions, state changes, preservation constraints, and interaction traces.

The repository contains the public runner and scorer. Dataset records, model weights, inference servers, and vendor runtimes are distributed separately.

## Installation

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-cloud.txt
python3 -m unittest discover -s tests -v
```

The offline test suite uses synthetic fixtures and does not require dataset access, API credentials, model weights, or an edge device.

## Dataset access

The benchmark data is hosted at **[chico-research/EdgeBench-Home on Hugging Face](https://huggingface.co/datasets/chico-research/EdgeBench-Home)**. Follow the dataset card and access terms there. Keep the dataset revision fixed for reproducibility and do not commit downloaded records to this repository.

```bash
pip install huggingface_hub
hf auth login
hf download chico-research/EdgeBench-Home \
  --repo-type dataset \
  --local-dir datasets/home
```

## Quick start

The runner accepts an OpenAI-compatible chat completion endpoint. Run one family and one interface as follows:

```bash
python3 -m cloud.run_state_given \
  --input datasets/home/en/State-Given/data/DGC.jsonl \
  --output outputs/home/en/State-Given/DGC.jsonl \
  --run-id example-en-sg-dgc \
  --base-url http://localhost:8000/v1 \
  --model your-model-id

python3 -m scoring.unified_scorer \
  --suite-root datasets/home \
  --interface State-Given \
  --predictions outputs/home/en/State-Given/DGC.jsonl \
  --output-dir outputs/home/en/State-Given/scores
```

Repeat for all seven families, both interfaces, and both languages before reporting a complete benchmark result. See the [EdgeBench-Home guide](benchmarks/home/README.md) for State-Seeking evaluation and AIR review.

For all command-line options:

```bash
python3 -m cloud.run_state_given --help
python3 -m cloud.run_state_seeking --help
python3 -m scoring.unified_scorer --help
```

## Repository layout

```text
benchmarks/        Benchmark registrations and domain guides
common/            Shared runner, environment, and protocol code
cloud/             OpenAI-compatible API runner
server/            Server adapter entrypoints
edge/              Optional Rockchip RKLLM adapter
scoring/           Deterministic scoring and AIR review
protocols/         Public output contracts
site/              GitHub Pages website
tests/             Synthetic offline tests
```

Future domains should be added under `benchmarks/<domain>/` with their own registration, task contracts, environment, and scorer. The suite name remains **EdgeBench**; the smart-home module remains **EdgeBench-Home**.

## Reproducibility and reporting

Record the EdgeBench commit, EdgeBench-Home dataset revision, model identifier and revision, language, interface, generation settings, context and output limits, and AIR review configuration. Keep generated predictions and reports outside version control.

The scorer reports incomplete coverage and pending AIR reviews explicitly. Do not treat a subset score as a full benchmark result.

## License

The code in this repository is licensed under the [Apache License 2.0](LICENSE). EdgeBench-Home is a separately distributed dataset; its license and access terms are defined by the [Hugging Face dataset card](https://huggingface.co/datasets/chico-research/EdgeBench-Home). Model weights and external runtimes retain their own licenses.
