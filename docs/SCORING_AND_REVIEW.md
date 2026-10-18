# Scoring and semantic review

Run `python3 -m scoring.unified_scorer --help` for prediction scoring. The scorer writes per-case records, a summary, and a Markdown report. It checks task-specific requirements and replays State-Seeking interactions.

AIR cases that require clarification also need a semantic review. The review checks whether the response requests the missing information without performing an unsupported action. Missing reviews remain pending. Review records bind to case, input, and response hashes; regenerate them when these inputs change.

Use `python3 -m scoring.air_judge --help` for packet preparation, model review, and validation commands. Configure the judge explicitly; the repository does not prescribe a provider or claim that automated judgements equal human ground truth. Retain judge configuration and raw responses. Review disagreements or uncertain cases manually with the human-review utilities.

Use `--air-reviews` when scoring reviewed predictions and `--require-complete` to reject pending review results. Full dataset coverage must be verified separately. See [review policy](../scoring/JUDGE_POLICY.md) for the implementation details.
