# Codex audit of this write-up (Oct 30, 2026)

codex-cli 0.162.1 · gpt-6-astra · reasoning high · read-only. Verdict on the first draft: FAIL, five errors. Each was
reproduced and fixed before publishing: the run-to-run spread was mislabelled, the Mesa formula for non-CPU-visible
VRAM was misstated, "every ordinary program" overstated a fresh-process result, the novelty claim covered a
documented kernel rule, and an outside request during run r2-j1 wasn't disclosed. The brief and the review follow
unedited, except that local scratch paths are shortened to `codex-extra/`.

## Brief


Working directory: the experiment folder (2026-10-30-darwin-two-slots). Extra files for you are in CODEX_EXTRA (path
given below): post.html (the website version of the write-up), the Mesa 26.1.6 files anv_physical_device.c and
xe_intel_device_info.c, llama.cpp b11747 files ggml-vulkan.cpp, c-fit.cpp (common/fit.cpp) and fit-params.cpp, and the
kernel uAPI headers xe_drm.h and i915_drm.h from the test machine.

### What was done (facts)
- Intel Arc B580 desktop GPU, llama.cpp b11747 Vulkan server with 2 slots, Gemma 4 12B. scripts/measure_slots.py ran 8
  extraction jobs six times, alternating one-at-a-time and two-at-a-time, sampling GPU package energy (xe hwmon) at 2 Hz.
  Raw data: data/run-2026-10-30b/ (summary.json, telemetry.csv, results-*.jsonl, server logs). scripts/summarize.py
  prints the tables.
- A free-VRAM claim: unprivileged programs get used=0 from the xe kernel driver, Mesa budgets 90% of the card,
  llama.cpp reports budget minus usage as free, and llama.cpp's default --fit plans from that. Screenshots' source text
  is in screenshots/source/*.txt.

### The question
Try to break the write-up. For README.md and post.html:
1. Recompute every number from the raw data (means, standard deviations, ratios like 1.52x and -32%, per-job slowdown
   range 19-31%, power 113/117 W, temperatures, 81%/78% agreement, 42 complete answers, 0 quote failures). Report any
   number that doesn't match, with your computation.
2. Check every claim about code against the provided source files: the xe header notes, Mesa's free/budget
   computation (is 10,994 MiB really 90% of 12,216 rounded down for a fresh process; does the B580's full-BAR case use
   the mappable path), llama.cpp's free-memory computation, and that llama-fit-params / the fit uses no_alloc and
   allocates nothing. Say if any claim is wrong or overstated.
3. Check the reasoning: is "most of the time it takes to generate a token goes to reading the model's weights" a fair
   plain-language explanation of why two slots help; is "I can't tell a gap that small from chance" fair for 17/21 vs
   49/63; are the limits honest; is anything claimed as new that the write-up itself shows is not.
4. Anything that would embarrass the author if a llama.cpp or Mesa developer read it.

### Rules
Read-only. Every finding: quote the sentence, say what's wrong, show the evidence (computation, file and line). If
you find nothing wrong in an area, say so briefly. Output markdown: Numbers, Code claims, Reasoning, Other, then a
one-line verdict (PASS or FAIL with the count of real errors).
CODEX_EXTRA = codex-extra

## Review

### Numbers

The headline results survive recomputation. One definite numerical wording error appears in the website.

**1. Standard deviations are mislabeled as run-to-run ranges.**

> “runs within 0.4 s of each other”  
> “runs within 0.7 s of each other”

— [post.html, lines 38–39](codex-extra/post.html:38)

The observed ranges are:

- One at a time: \(155.07-154.23=\mathbf{0.84\,s}\).
- Two at a time: \(102.01-100.52=\mathbf{1.49\,s}\).

The quoted 0.4/0.7 values are **population standard deviations**, as implemented in [summarize.py, line 28](scripts/summarize.py:28). The README correctly calls them standard deviations. Change the website labels accordingly.

Recomputed from [summary.json](data/run-2026-10-30b/summary.json:1), independently summing generated tokens from each results file:

| Run | Wall, s | Generated tokens | Tokens/s¹ | Package J | J/token | Mean W |
|---|---:|---:|---:|---:|---:|---:|
| r1-j1 | 154.23 | 5,255 | 34.07249 | 17,415.6 | 3.314101 | 112.920 |
| r1-j2 | 101.98 | 5,286 | 51.83369 | 11,911.5 | 2.253405 | 116.802 |
| r2-j2 | 100.52 | 5,177 | 51.50219 | 11,742.1 | 2.268128 | 116.814 |
| r2-j1 | 154.28 | 5,250 | 34.02904 | 17,421.7 | 3.318419 | 112.923 |
| r3-j1 | 155.07 | 5,286 | 34.08783 | 17,521.2 | 3.314642 | 112.989 |
| r3-j2 | 102.01 | 5,286 | 51.81845 | 11,917.9 | 2.254616 | 116.831 |

¹ The published 51.84 for r1-j2 is compatible with rounding: the script calculates throughput using the unrounded duration, then separately rounds wall time. See [measure_slots.py, lines 105–108](scripts/measure_slots.py:105).

| Statistic | One at a time | Two at a time |
|---|---:|---:|
| Mean wall time | 154.526667 s | 101.503333 s |
| Population SD | 0.384737 s | 0.695430 s |
| Sample SD, for comparison | 0.471204 s | 0.851724 s |
| Mean throughput | 34.063120 tok/s | 51.718110 tok/s |
| Mean energy/token | 3.315721 J | 2.258716 J |
| Mean package power | 112.943749 W | 116.815529 W |

Consequently:

- Wall-time speedup: **1.522380×**.
- Generated-token throughput ratio: **1.518302×**. Both round to **1.52×**.
- Energy/token reduction: **31.878568%**, correctly rounded to **32%**.
- Power increase: **3.871780 W**, correctly rounded to **4 W**.

Per-job recomputation from the six `results-*.jsonl` files:

| Job | One, mean seconds | Two, mean seconds | Slowdown |
|---|---:|---:|---:|
| results | 6.536667 | 8.546667 | 30.7496% |
| whats-new | 12.116667 | 14.493333 | 19.6149% |
| setup | 13.920000 | 16.510000 | 18.6063% |
| replicate | 16.490000 | 20.023333 | 21.4271% |
| root-plan | 15.433333 | 18.886667 | 22.3758% |
| limits-methods | 9.880000 | 12.893333 | 30.4993% |
| engine-summary | 46.353333 | 57.520000 | 24.0903% |
| sustained-analysis | 33.756667 | 42.570000 | 26.1084% |

**Precision discrepancy, not counted as a definite underlying error:** the README’s `limits-methods` row says **31%** ([line 105](README.md:105)). The archived times give:

\[
100\left(\frac{(12.93+12.81+12.94)/3}{9.88}-1\right)=30.499325\%.
\]

Strict rounding directly to an integer gives **30%**. However, the archived durations themselves are rounded to hundredths; their possible underlying slowdown spans approximately 30.383–30.616%. Use **30.5%** to avoid this boundary issue. The overall **19–31%** range remains correct.

Other checks:

- Agreement: **17/21 = 80.9524%** within each mode separately; pooled within-mode agreement is **34/42**. Across modes: **49/63 = 77.7778%**. Both published percentages match.
- **42 complete JSON answers**; I independently checked **245 quote strings**, finding **zero substring failures**.
- All six `engine-summary` jobs generated **1,600 tokens**, reported `finish=length`, and failed JSON parsing. Their quote validation never ran; “zero quote failures” should not imply those six incomplete answers were validated.
- Package maxima, in run order: **63, 64, 63, 64, 63, 64 °C**. VRAM maximum: **66 °C** in every run.
- Clock median: **2,850 MHz** in every run. “Held” is acceptable shorthand for the operating clock, but not literal constancy: telemetry includes a few 0/1,350 MHz transition samples.
- Every in-window VRAM sample reports **9,145 MiB**.
- \(12,216-9,145=\mathbf{3,071}\) MiB; \(6,637+2,652+679=\mathbf{9,968}\) MiB. These match the screenshots. The latter sums individually truncated MiB estimates, so “about 9,968 MiB” is most precise.

**Reproducibility limitation:** exact energy totals cannot be independently reconstructed from `telemetry.csv`. The script takes separate boundary counter readings and saves their difference, not the original readings ([measure_slots.py, lines 94–108](scripts/measure_slots.py:94)). All six reported totals fall between the corresponding inner and outer telemetry-sample energy differences; none is contradicted.

### Code claims

**2. The README misstates the non-mappable VRAM formula.**

> “computes free VRAM as size minus `cpu_visible_used` and size minus `used`”

— [README.md, lines 125–126](README.md:125)

The actual formulas are:

```text
mappable.free   = mappable.size   - cpu_visible_used
unmappable.free = unmappable.size - (used - cpu_visible_used)
```

Evidence: [xe_intel_device_info.c, lines 131–132](codex-extra/xe_intel_device_info.c:131).

The missing subtraction matters for the general explanation, although it does **not** change the unprivileged/full-BAR conclusion here. Also, the quoted “elevated privileges” comment at line 115 is physically in the **system-memory** branch.

**3. “Every ordinary program” overgeneralizes the fresh-process result.**

> “every ordinary program on it is told 90% of the card is free”

— [README.md, lines 7–8](README.md:7); also post.html line 4.

Mesa retains the querying process’s own heap usage. With full-BAR heap size \(S\), own usage \(U\), and unavailable global accounting:

\[
B=\operatorname{floorMiB}(\min(S,U+0.9S)),\qquad F=\max(B-U,0).
\]

For example, \(S=12,216\) MiB and \(U=4,096\) MiB gives **8,120 MiB free**, not 10,994 MiB.

Evidence: [anv_physical_device.c, lines 3130–3170](codex-extra/anv_physical_device.c:3130), and [ggml-vulkan.cpp, lines 15311–15315](codex-extra/ggml-vulkan.cpp:15311). Vulkan explicitly defines `heapUsage` as the current process’s allocation estimate. [Vulkan specification](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceMemoryBudgetPropertiesEXT.html)

Use: **“A fresh unprivileged llama.cpp process reports about 90% of the card as free, ignoring other processes’ usage.”**

The central code trace otherwise checks out:

- **xe privilege restriction:** both fields explicitly document zero without either capability. [xe_drm.h, lines 325–329 and 351–358](codex-extra/xe_drm.h:325)
- **Full BAR uses the mappable path:** non-mappable size becomes zero; ANV selects the mappable heap and its availability. [xe_intel_device_info.c, lines 123–124](codex-extra/xe_intel_device_info.c:123); [anv_physical_device.c, lines 2217–2241 and 3135–3141](codex-extra/anv_physical_device.c:2217).
- **Fresh-process budget:** \(\lfloor12,216\times0.9\rfloor=\mathbf{10,994}\) MiB. Correct.
- **llama.cpp free memory:** budget minus usage, with heap-size clamping and saturation at zero. Correct.
- **i915:** its header explicitly substitutes `probed_size` for unprivileged `unallocated_size`. The tentative inference about A-series is fairly qualified. [i915_drm.h, lines 3500–3507](codex-extra/i915_drm.h:3500)

**Dry-run qualification:**

> “it loads the model with `no_alloc` and no tensor data, so nothing is allocated on the card.”

— [README.md, lines 134–135](README.md:134)

The first part is confirmed: `no_alloc=true`, `load_mode=LLAMA_LOAD_MODE_NONE`, followed by model/context construction. The tool calls the shared fitting function. [c-fit.cpp, lines 56–66](codex-extra/c-fit.cpp:56); [fit-params.cpp, lines 33–37](codex-extra/fit-params.cpp:33).

“Nothing” is stronger than these files establish. Backend initialization still creates Vulkan device/resources; `no_alloc` is not proof of zero driver-internal GPU allocation. See `ggml-vulkan.cpp` lines 4776 and 5489–5500. Prefer **“estimates memory without loading the model’s tensor data.”** I am not counting an actual unwanted allocation as demonstrated.

The supplied files also omit the parameter initializers establishing **default `--fit on` and the 1,024 MiB default margin**. The fitting logic consumes those settings, and the screenshot’s approximately 1,026 MiB remaining budget is consistent with them, but their defaults are not independently established by this source bundle.

### Reasoning

**The bandwidth explanation is fair as an intuition, but stronger than the measurement proves.**

> “Most of the time it takes to generate a token goes to reading the model’s weights out of VRAM.”

— README.md lines 112–113; post.html line 42.

Weight-loading dominance at small batch sizes is an established explanation for batching gains. [Efficiently Scaling Transformer Inference, §3.1](https://arxiv.org/html/2211.05102v1)

However, this experiment records energy, clocks and timings—not memory bandwidth or kernel stalls. “Reads them once for two tokens” describes the ideal shared-weight benefit, not a verified count of physical reads. Suggested wording: **“Batching lets the GPU reuse weights across requests, reducing memory traffic per generated token.”** This is a qualification, not evidence that the explanation is wrong.

**The chance statement is appropriately cautious.**

> “I can’t tell a gap that small from chance.”

— README.md line 110; post.html line 43.

The gap is **3.1746 percentage points**. The comparisons reuse the same answers and therefore are not independent Bernoulli trials; a naïve significance test using 21 and 63 independent observations would be inappropriate. The write-up does not claim equivalence or statistical significance, so this sentence is fair.

**4. The website overstates what is new.**

> “As far as I could find neither of these has been published before.”  
> “Ordinary programs can’t see VRAM use on Intel’s xe driver.”

— [post.html, lines 9–12](codex-extra/post.html:9)

That restriction is already explicitly published in the kernel header the article reproduces. Mesa’s own comment acknowledges it too: `xe_drm.h` lines 325–329, 351–358; `xe_intel_device_info.c` line 115.

The potentially new contribution is **the demonstrated consequence for llama.cpp’s automatic fit on this stack**, not discovery of the privilege restriction. The README’s narrower framing is substantially better. Nothing supplied contradicts the specifically B580 throughput/energy novelty claim; it does not claim batching itself is new.

The stated limits are otherwise candid: one configuration, three runs per mode, package energy rather than whole-system energy, incomplete outputs disclosed, and no actual second-model load.

### Other

**5. A nominally serial run contains an undisclosed concurrent request.**

> “Between modes the only change was how many requests the batch tool sent at once.”

— [post.html, line 87](codex-extra/post.html:87)

The isolation implied here needs a qualification. During `r2-j1`:

- Measured task **36937** is running in slot 0.
- Additional task **37276** starts in slot 1.
- It processes **26 prompt tokens**, generates **2 tokens**, and takes **252.88 ms**.
- Task 36937 continues afterward.

Evidence: [server-log-r2-j1.log, lines 47–62](data/run-2026-10-30b/server-log-r2-j1.log:47).

Thus the server log contains **nine completed tasks and 5,252 generated tokens**, while the eight measured jobs total **5,250 tokens**. The job table is correct; the run also includes outside activity whose energy and interference enter the measurement.

This is too small to explain the headline gain, but disclose it or repeat that run with other clients stopped. A reviewer examining the logs will notice.

Two additional clarifications would improve defensibility without changing the findings:

- “Byte-identical answers” refers to **the saved, parsed-and-pretty-printed JSON outputs**, not necessarily raw model response bytes. See [llm-task, lines 121–128](scripts/llm-task:121).
- Quote matching establishes verbatim source presence, not factual correctness or complete extraction. “All 42 … passed” accurately describes that check.

**FAIL — 5 confirmed errors; the headline performance result and fresh-process free-memory diagnosis remain supported.**