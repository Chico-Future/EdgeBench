# Architecture

EdgeBench is the suite; each domain is described under `benchmarks/`. The first domain is EdgeBench-Home. Its registration identifies its dataset, languages, interfaces, and task families. Future domains can provide distinct environments and scorers while reusing suitable backend code.

The current Home runner sends only each case's `model_input` to the model. Evaluation annotations are loaded separately by the scorer. State-Seeking executes against a simulated environment, never a real home. API and device adapters implement generation and token counting; the shared runner handles budgets, interaction records, and diagnostics.

Scoring verifies predictions against evaluation annotations. State-Seeking traces are replayed. AIR clarification judgements bind to response and input hashes so that reviews cannot silently transfer to changed outputs.

Some implementation modules retain historical internal names for compatibility. Public task and interface names are the ones in the benchmark registration.
