# Contributing

Run the synthetic offline tests before opening a pull request. Keep credentials, dataset records, model weights, generated predictions, and private experiment settings out of commits.

For a new benchmark domain, create `benchmarks/<domain>/` with a guide and registration. Define its environment, task contracts, scorer, and synthetic tests explicitly. Do not rename EdgeBench-Home to represent the whole suite.

Changes to scoring or simulation semantics should explain their effect on comparability and add regression coverage. Hardware-dependent changes should identify what was tested on a device.
