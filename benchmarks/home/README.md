# EdgeBench-Home

EdgeBench-Home evaluates smart-home agents within the EdgeBench suite. The dataset supplies bilingual cases, model-visible inputs, evaluation annotations, device specifications, and output contracts. Evaluation annotations must never be added to model prompts.

## Task families

| Abbreviation | Task family |
| --- | --- |
| DGC | Device Grounding and Control |
| MSC | Multi-device Selection and Control |
| AIR | Ambiguity and Intent Resolution |
| FAR | Future Automation Registration |
| DCR | Dialogue-context Resolution |
| PMU | Personalized Memory Use |
| REQ | Read-only Environment Queries |

**State-Given (SG).** The model receives the supplied context and produces a single response.

**State-Seeking (SS).** The model starts with partial observations and can query or act through the supplied tools. The runner records the interaction trace; the scorer replays it to verify effects.

## Run State-Seeking

From the repository root, after the installation and download steps in the main README:

```bash
python3 -m cloud.run_state_seeking   --suite-root datasets/home   --input datasets/home/en/State-Seeking/data/DGC.jsonl   --output outputs/home/en/State-Seeking/DGC.jsonl   --run-id my-model-en-ss-dgc   --base-url http://localhost:8000/v1 --model your-model-id

python3 -m scoring.unified_scorer   --suite-root datasets/home --interface State-Seeking   --predictions outputs/home/en/State-Seeking/DGC.jsonl   --output-dir outputs/home/en/State-Seeking/scores
```

Replace `en` with `zh` for the other language and `DGC` with each family abbreviation. Dataset-supplied protocol files take precedence; bundled contracts provide a fallback. Default execution makes no format-repair generation.

## Scoring and AIR review

Scores check task requirements, action validity, relevant state changes, and preservation constraints. Clarification responses in AIR additionally require semantic review. Pending reviews are reported explicitly and must not be presented as completed formal results.

See [scoring and review](../../docs/SCORING_AND_REVIEW.md). Pass `--air-reviews` to the scorer once reviews are available. `--require-complete` fails when required reviews are pending; it does **not** verify that all benchmark cases have been run. Independently check coverage for every family, interface, and language before reporting a full result.

## Dataset and reproducibility

Download the dataset from [our Hugging Face repository](https://huggingface.co/datasets/chico-research/EdgeBench-Home). Record the dataset revision, code commit, model version, generation settings, language, interface, and review configuration. The runner writes prediction records and a run manifest. Keep outputs outside version control.

The module registration is [benchmark.json](benchmark.json). Other domains should receive their own directory and registration under `benchmarks/`.
