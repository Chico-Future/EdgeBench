# EdgeBench

[![Tests](https://github.com/Chico-Future/EdgeBench/actions/workflows/ci.yml/badge.svg)](https://github.com/Chico-Future/EdgeBench/actions/workflows/ci.yml)
[![Hugging Face Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-EdgeBench--Home-yellow)](https://huggingface.co/datasets/chico-research/EdgeBench-Home)
[![License: Apache 2.0](https://img.shields.io/badge/Code-Apache--2.0-blue.svg)](LICENSE)

**EdgeBench** is an extensible benchmark suite for evaluating language models as agents in practical environments. **EdgeBench-Home** is the first benchmark in the suite, focused on bilingual smart-home tasks.

[Website](https://chico-future.github.io/EdgeBench/) · [EdgeBench-Home website](https://chico-future.github.io/EdgeBench/home/) · [Submit results](https://chico-future.github.io/EdgeBench/home/#submit-results) · [Dataset on Hugging Face](https://huggingface.co/datasets/chico-research/EdgeBench-Home) · [Home benchmark guide](benchmarks/home/README.md)

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

## Revised result accounting

The EdgeBench-Home results page follows the revised ICLR/rebuttal accounting: 840 bilingual cases (420 Chinese and 420 English), seven task families with 60 cases per family and language, and 22 evaluated configurations (18 local plus four Server/API references).

The RK3588 State-Seeking result for **Qwen3-1.7B-16K** is 23/420 Chinese (5.5%), 4/420 English (1.0%), and 27/840 bilingual (3.2%). Under the same State-Seeking task families, the four-configuration Server reference group averages 43.8% on FAR and 40.2% on REQ, while the tested local configurations score 0% on both. These values support separation among the evaluated configurations; they do not by themselves validate every case or identify local failure causes.

All 840 final cases received individual expert review for bilingual wording, relative difficulty, and duplicate or near-duplicate cases. The public materials do not provide independent bilingual episode-level reproduction of the original P0 campaign, local FAR/REQ failure attribution, or aligned RK3588 latency, memory, and energy measurements.

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

## Submit results

After scoring a run, use the [Email results](https://chico-future.github.io/EdgeBench/home/#submit-results) link on the EdgeBench-Home page to open a pre-addressed email to **yiliu.li@chico-future.com**. GitHub Pages is a static site, so it does not upload or store results. Attach `report.md` and `summary.json` from the scorer output directory, complete the template, review it, and send it yourself.

Include the model and revision, interface, language, strict micro-success, scored and expected case counts, dataset revision, EdgeBench commit, and per-family scores when available. Report partial coverage as partial; a subset score is not a full benchmark result. For reproducibility, include the generation settings and AIR review status described above.

## License

The code in this repository is licensed under the [Apache License 2.0](LICENSE). EdgeBench-Home is a separately distributed dataset; its license and access terms are defined by the [Hugging Face dataset card](https://huggingface.co/datasets/chico-research/EdgeBench-Home). Model weights and external runtimes retain their own licenses.
