# AIR clarification review

The public entry point is `python3 -m scoring.air_judge`. The implementation
remains in `tc3_judge.py`; existing schema and prompt version identifiers and
`tc3_judge_prompt_v1.txt` are retained for hash compatibility.

## Dataset and CLI

Run from the repository root. Supply the public EdgeBench-Home dataset separately;
no dataset or historical results are bundled here. `--suite-root` accepts a dataset
root containing `en/AIR/data/` and `zh/AIR/data/`, or an individual `en` or `zh`
directory. Each language requires `cases.jsonl` and `evaluation.jsonl` with matching
IDs. Duplicate IDs across languages are rejected rather than overwritten.

```sh
python3 -m scoring.air_judge prepare --suite-root /path/to/EdgeBench-Home \
  --interface State-Given --predictions /path/to/predictions.jsonl \
  --output /path/to/packets.jsonl --manifest /path/to/prepare.json
python3 -m scoring.air_judge run-judge --packets /path/to/packets.jsonl \
  --reviews /path/to/reviews.jsonl --audit /path/to/audit.jsonl \
  --manifest /path/to/run.json --judges-file /path/to/judges.yaml
python3 -m scoring.air_judge validate --packets /path/to/packets.jsonl \
  --reviews /path/to/reviews.jsonl --require-complete
```

Use `State-Seeking` for predictions stored under `final_output`; State-Given reads
`prediction`. Each prediction row needs an `id`. Preparation selects AIR gold
clarification cases with a submitted clarification mode and a nonempty response.
Rows outside AIR are ignored. Preparation does not replay trajectories or certify
structural validity; the unified scorer performs those checks independently.

## Configuration and outputs

`judges.yaml` is a disabled placeholder, not an endorsed or frozen judge. Copy it,
set the provider and model, configure the endpoint and API-key environment variables,
and enable the entry. Only Responses-style APIs are supported. Use provider
`openai` to send `store=false`; other providers do not receive that option.
Configure schema strictness, reasoning effort, temperature, and token limits for
the selected endpoint. No provider compatibility is guaranteed by the placeholder.
`run-judge` requires the `openai` SDK and PyYAML. Loading an existing `--env-file`
(default: repository `.env`) also requires python-dotenv; existing environment
variables take precedence. `--judge-key`, `--prompt`, and `--retries` are optional.

Packets bind the candidate response, source record, and judge input using SHA256
of sorted compact UTF-8 JSON. Dataset and prediction files are hashed in the
preparation manifest. Judge input contains only user-visible context, ambiguity,
clarification rubric, and candidate response, excluding reference clarifications
and simulated follow-up branches. Only this judge input is sent with the prompt;
packet IDs, interface, and source metadata are not sent to the judge.

Reviews contain `id`, `response_sha256`, `quality`, and a nonempty `rationale`.
Labels are `full`, `partial`, and `fail`. The unified scorer requires an exact
response-hash match: full passes strict semantic scoring; full or partial passes
the separate lenient diagnostic. Structural failures remain deterministic failures.
No matching review leaves an otherwise valid clarification pending.

The run manifest records prompt/catalog/file hashes, configuration, SDK version,
resolved models, and available fingerprints. Per-case audits record response and
input hashes, prompt/output hashes, requested/resolved model, response ID, usage,
and available fingerprint. These records do not freeze a remote model. Resume
skips existing hash-valid reviews; it does not verify that their original prompt,
configuration, or audit matches the new run. Use fresh output paths when changing
judge settings. API/network errors are retried; output parsing/validation errors
are not. A manifest's storage field is not proof of provider-side retention policy.

## Human review and utilities

`python3 -m scoring.human_review --help` exposes the existing two-reviewer workflow.
It removes system identity into a separate mapping, uses deterministic review IDs,
and preserves response hashes. Keep mappings and source manifests private from
reviewers. Case IDs, interfaces, and response content remain visible; this is
system-identity blinding, not anonymization of all content.

For comparable experiments, record the chosen configuration and prompt, disclose
rolling model aliases, inspect model/fingerprint changes, and report human review
agreement. The tools do not enforce a common run window or automatic reruns.

`scripts/merge_transport_retry.py` retains audited replacement of a transient
transport failure. `scripts/verify_suite_manifest.py` checks a supplied manifest
with `files` entries containing relative `path`, `bytes`, and `sha256`; it neither
ships nor generates a dataset manifest. The campaign report and legacy artifact
validator were removed because they assumed historical output layouts and counts.
