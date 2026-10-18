# Execution and reporting

Use State-Given and State-Seeking on the same dataset revision. Run all seven families for each language and report the coverage explicitly. Do not mix a subset score with a full benchmark score.

Record the model identifier and provider revision, code commit, dataset commit, prompt and output budgets, context limit, temperature, seed when supported, and interaction limit. Defaults are visible in each CLI's `--help`; provider-side nondeterminism can remain even at temperature zero.

The standard entrypoints use the default single-attempt generation path. Parse failures, context overflow, transport failures, and tool errors remain visible in predictions. Do not silently discard failures or rerun only unsuccessful cases. Any transport retry must be disclosed and preserve original records.

API token counts may use a portable tokenizer rendering or a conservative heuristic rather than the provider's exact chat template. A local tokenizer file alone does not prove an exact provider context count. Keep provider usage and budget diagnostics when available.

Report strict success, family scores, language and interface breakdowns, and AIR review coverage. A scorer invocation can score a subset; its output is not evidence of complete dataset coverage. Do not infer on-device speed or deployment feasibility from server/API runs.
