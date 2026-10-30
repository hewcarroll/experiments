# Experiments

Experiments I run on my own machines, with everything needed to repeat them: the scripts, the raw data, the logs and
screenshots of the captured output. Each folder is one experiment and each has a write-up at
https://hewcarroll.com/experiments/.

| Date | Experiment | Status |
|---|---|---|
| 2026-10-30 | [Two requests at a time on an Intel Arc B580](2026-10-30-darwin-two-slots/) | done |
| 2026-10-29 | [Tuning a throttling Tesla P100 from the driver up](2026-10-29-p100-r580-vulkan/) | ongoing |

Each experiment folder has the same shape: a README with the question, setup, results and steps to replicate, then
`scripts/`, `data/`, `screenshots/` (with the source text each image was rendered from) and, where they apply,
`logs/`, `inputs/` and `methods/`. `tools/render-terminal.mjs` turns captured terminal text into the screenshots.

If you repeat one of these and get a different result, or the same one, please open an issue with your numbers and
setup.

## Licence

Code (`scripts/`, `tools/`) is available under either the MIT licence or the Apache License 2.0, at your option
(`LICENSE-MIT`, `LICENSE-APACHE`). Data, logs, screenshots and text are licensed under Creative Commons Attribution
4.0 International (`LICENSE-DATA.md`).
