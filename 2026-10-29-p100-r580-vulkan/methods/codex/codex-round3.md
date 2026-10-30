**[inference] The best next tests are prompt reuse, constrained output, n-gram speculation, and concurrent requests in the existing engine.** I found no matched benchmark establishing that another engine beats kala’s present Vulkan configuration. There is useful P100 evidence for alternative quantizations and the two-card MoE, but it does not establish their performance on kala.

## 1. Speculative decoding

### What the five n-gram modes actually do

| Mode | Mechanism | Fit for quote-heavy extraction |
|---|---|---|
| `ngram-simple` | **[documented]** Searches backward for the current N-token suffix in token history, then proposes up to M subsequent tokens. The history includes the input prompt. | **[inference]** Best first test: it can copy a passage that occurs only once in the supplied chunk. |
| `ngram-map-k` | **[documented]** Maintains indexed n-gram matches and drafts their continuations. It remembers previous acceptance lengths and can shorten later drafts. | **[inference]** Worth comparing with simple lookup; no established advantage for these short, mostly independent requests. |
| `ngram-map-k4v` | **[documented]** Tracks up to four alternative continuations per key and uses occurrence/acceptance statistics to select drafts. | **[inference]** More relevant to repeated templates or passages than one-off quotes. Additional statistics need useful repetition. |
| `ngram-mod` | **[documented]** Uses a fixed hash table mapping an N-token sequence to its next token, repeatedly looking up subsequent tokens. Its approximately 16 MiB pool is shared across server slots. | **[inference]** Potentially useful for repeated text across a long batch, but the default minimum draft length is poorly matched to short quotes. |
| `ngram-cache` | **[documented]** Predicts continuations from n-gram frequency statistics, consulting context, dynamic, and static caches. External cache files are optional. | **[inference]** More attractive when many requests share predictable language. I would test direct prompt lookup first. |

Sources: installed-commit [`common/ngram-map.cpp`](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/ngram-map.cpp), [`common/speculative.cpp`](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/speculative.cpp), [`common/ngram-cache.cpp`](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/ngram-cache.cpp); introducing PRs [#18471](https://github.com/ggml-org/llama.cpp/pull/18471) and [#19164](https://github.com/ggml-org/llama.cpp/pull/19164).

**[documented] A small documentation discrepancy:** the speculative-decoding guide describes `ngram-map-k-min-hits` as gating drafts, but in the inspected implementation the `key_only` branch returns before that check. I would not rely on that setting to tune `ngram-map-k` without checking the particular build. [Implementation](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/ngram-map.cpp).

### Starting settings

**[inference] Start with one change:**

```text
--spec-type ngram-simple
--spec-ngram-simple-size-n 8
--spec-ngram-simple-size-m 16
```

Compare against `--spec-type none`, then the installed defaults, N=12/M=48. These are experimental choices, not published P100 optima. N=8 allows earlier matching within quotes; M=16 limits verification wasted when the quote ends.

**[inference] If quotes are predominantly long passages**, compare:

```text
--spec-type ngram-mod
--spec-ngram-mod-n-match 16
--spec-ngram-mod-n-min 4
--spec-ngram-mod-n-max 16
```

**[documented] Here `n-match` is the lookup length; `n-min` and `n-max` are draft lengths.** The source explicitly warns about `n-match < 16`. Its default minimum of 48 means shorter available continuations can be discarded. [Argument definitions](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp), [drafting implementation](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/speculative.cpp).

**[inference] Important limitations for this workload:**

- A short quote may finish before enough matching tokens accumulate.
- JSON escaping, whitespace and tokenization can interrupt matches even when the decoded quote is a valid substring.
- Classification labels and novel field values provide less prompt-copying opportunity.
- Acceptance percentage alone is insufficient: record accepted tokens per verification pass and total request time.

### Grammar and parallel slots

**[documented] Yes: the inspected installed source and upstream b11988 support speculative decoding with multiple server slots and target-side grammar sampling.** Speculative state is initialized with `n_parallel`; verification samples and accepts tokens through the target sampler, including its grammar. Sources: [installed server](https://github.com/ggml-org/llama.cpp/blob/5190c2e/tools/server/server-context.cpp), [current server](https://github.com/ggml-org/llama.cpp/blob/b11988/tools/server/server-context.cpp), [current sampling implementation](https://github.com/ggml-org/llama.cpp/blob/b11988/common/sampling.cpp).

**[documented] That is not a blanket guarantee for every model and memory-pressure case.** Initialization depends on context rollback support. There has also been a speculative sub-batch indexing bug; b11988 contains an explicit error path when speculative indices fall outside a retried sub-batch. [Issue #24840](https://github.com/ggml-org/llama.cpp/issues/24840), [server implementation](https://github.com/ggml-org/llama.cpp/blob/b11988/tools/server/server-context.cpp).

**[inference] Test Qwen2.5 with speculation and parallelism separately, then together.** Do not automatically extend the result to the recurrent/hybrid Qwen3.5/3.6 architectures.

### Draft model versus n-grams

**[inference] Qwen2.5-0.5B-Instruct could help predictable JSON scaffolding and classifications, but I would not predict that it beats prompt lookup here.** It adds draft inference, prompt processing, weights and KV storage. Prompt lookup can reproduce long quotations without running another network.

**[documented] The draft must pass llama.cpp’s vocabulary/token compatibility checks; sharing a family name is insufficient.** [Compatibility checks](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/speculative.cpp).

**[community] Published prompt-lookup results exist, but not a matched P100/Qwen2.5-14B extraction comparison:** PR #18471 reports approximately **181→446 tok/s** for a favorable GPT-OSS source-editing example and **11.77→21.00 tok/s** for heavily offloaded Qwen3-235B. Output lengths differed; these establish opportunity, not a transferable speedup. [Author’s measurements](https://github.com/ggml-org/llama.cpp/pull/18471).

**[inference] A reliable number for Qwen2.5-14B plus a 0.5B draft on P100: unknown.**

## 2. Parallel slots, continuous batching and KV memory

**[inference] Concurrent decoding is promising, but “26.9 tok/s × number of slots” is not a forecast.** Batching can amortize weight access and kernel launches and improve GPU occupancy. It also increases work per decoding step, attention traffic and power; individual-request latency may increase.

**[inference] Also soften the bottleneck claim:** `8.57 GB × 26.9 tok/s ≈ 230 GB/s` is an effective model-weight traffic estimate, not a measured DRAM bandwidth counter. Core-clock sensitivity supports investigating execution/dequantization costs, but does not uniquely identify shader arithmetic versus latency or mixed bottlenecks.

**[documented] Continuous batching is enabled by default in this server source.** Multiple slots require actual overlapping client requests to exercise it. [Server options](https://github.com/ggml-org/llama.cpp/blob/5190c2e/tools/server/README.md).

### Qwen2.5-14B KV calculation

**[documented] Its configuration has 48 layers, 8 KV heads and head dimension 128.** Q8_0 stores 32 values plus a two-byte scale per block. Sources: [model configuration](https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/blob/main/config.json), [GGML block definitions](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-common.h).

**[inference, calculated] For both K and V:**

\[
2 \times 48 \times 8 \times 128 = 98{,}304\text{ elements/token}.
\]

| KV types, K/V | Bytes/token | 4,096 tokens | 8,192 tokens |
|---|---:|---:|---:|
| f16/f16 | 196,608 — 192 KiB | 0.750 GiB | 1.500 GiB |
| q8_0/q8_0 | 104,448 — 102 KiB | 0.3984 GiB | 0.7969 GiB |

**[inference] These are KV payload sizes, excluding weights, compute buffers, allocator overhead and other state.** Four independent 8k contexts therefore require approximately 6 GiB of f16 KV or 3.1875 GiB of Q8_0 KV.

**[documented] Context allocation depends on unified-KV mode.** Without unified KV, the inspected source divides total context by maximum sequence count. With unified KV, sequences share the total pool. [Context initialization](https://github.com/ggml-org/llama.cpp/blob/5190c2e/src/llama-context.cpp).

**[inference] Use explicit settings for a controlled comparison:**

```text
--parallel 2 --ctx-size 8192 --no-kv-unified
```

This provides 4k per slot. For 8k per slot, use `--ctx-size 16384`. Verify `n_ctx_seq` in startup logs. Count actual prompt-plus-output **tokens**; the workload sizes supplied are characters.

**[inference] Keep f16 KV for the first batching test.** Then test:

```text
--cache-type-k q8_0 --cache-type-v q8_0
```

Q8_0’s reliable benefit is reduced memory consumption; faster execution and unchanged extraction accuracy remain measurements, not guarantees.

## 3. Other engines on sm_60

| Engine | P100 status and relevant evidence |
|---|---|
| **vLLM official** | **[documented] Unsupported by the current official GPU requirement: compute capability ≥7.5.** An older statement that the minimum is 7.0 is stale. [Installation requirements](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/). |
| **vLLM Pascal forks** | **[community] A P100-specific fork exists**, extending the P40/Pascal fork with sm_60-compatible fallbacks. Its README reports Qwen2.5-14B GPTQ INT8 at **12.4–13.4 tok/s on two P100s**, using CUDA 12.1/PyTorch 2.5.1. It explicitly labels itself work in progress. These numbers do not beat kala’s single-card Vulkan result, and quantization differs. Current maintenance guarantees are unknown. [HeikoKramer68/vllm-tesla-p100](https://github.com/HeikoKramer68/vllm-tesla-p100). |
| **ExLlamaV2** | **[documented] Uses packed FP16 `half2` arithmetic in its quantized GEMM kernels; the project is now archived.** **[community] P100 operation is demonstrated historically:** Llama-3.1-8B, EXL2 8 bpw, **29.58 tok/s**, with flash attention disabled, versus **21.48 tok/s** for that report’s GGUF Q8_0 configuration. This is not a current-release or Vulkan comparison. [Kernel source](https://github.com/turboderp-org/exllamav2/blob/master/exllamav2/exllamav2_ext/cuda/q_gemm_kernel.cuh), [project status](https://github.com/turboderp-org/exllamav2), [benchmark](https://www.reddit.com/r/LocalLLaMA/comments/1f6hjwf/battle_of_the_cheap_gpus_lllama_31_8b_gguf_vs/). |
| **ExLlamaV3** | **[documented] Current wheel-build architecture lists start at sm_75, excluding sm_60.** **[inference] A working current P100 configuration is unknown; adding sm_60 to the build list alone does not establish kernel compatibility.** [Build workflow](https://github.com/turboderp-org/exllamav3/blob/master/.github/workflows/build.yml), [Pascal support request](https://github.com/turboderp-org/exllamav3/issues/509). |
| **MLC-LLM** | **[community] Historical P100 operation is demonstrated for dense Qwen3-32B `q4f16_1`, on four cards, while the same reporter’s MoE failed.** That report used CUDA 12.4 with cu123 MLC nightly wheels. **[inference] Current-release support and a useful 7–14B P100 throughput result are unknown.** Its FP16-activation format does not prove a particular generated kernel uses GP100’s peak packed-FP16 rate. [Issue #3231](https://github.com/mlc-ai/mlc-llm/issues/3231). |
| **SGLang** | **[documented] Its CUDA-13 migration discussion says the existing `sgl-kernel` requirements already exclude Pascal.** I found no supported current P100 configuration or relevant benchmark. [Upstream RFC #20486](https://github.com/sgl-project/sglang/issues/20486), [older explicit Pascal request](https://github.com/sgl-project/sglang/issues/1062). |
| **Aphrodite / current Sonar repository** | **[documented] Current CUDA wheels require compute capability ≥8.0.** Old Aphrodite/P40 compatibility reports do not establish GP100 support today. [Current installation documentation](https://sonar.dphn.ai/getting-started/installation/), [repository](https://github.com/dphnAI/sonar). |
| **TensorRT-LLM** | **[documented] NVIDIA’s hardware matrix lists Ampere and newer families, not Pascal.** A working current P100 path and relevant numbers are unknown. [Support matrix](https://nvidia.github.io/TensorRT-LLM/reference/support-matrix.html#hardware). |
| **llama.cpp CUDA** | **[documented] The inspected source has an sm_60 path.** Quantized matrix-matrix MMQ dispatch rejects architectures below DP4A capability; `GGML_CUDA_FORCE_MMQ` does not override that earlier rejection. Quantized matrix-vector kernels can use software-emulated four-byte integer dot products. The cuBLAS fallback recognizes GP100 as fast-FP16 hardware and can dequantize operands to FP16 and use FP16 GEMM. [MMQ dispatch](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-cuda/mmq.cu), [DP4A fallback](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-cuda/common.cuh), [cuBLAS path](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-cuda/ggml-cuda.cu). |

**[inference] Therefore, “CUDA cannot exploit P100 FP16” is wrong; “CUDA must be faster because P100 has fast FP16” is equally unsupported.** Your existing Vulkan measurement remains the stronger local evidence.

### PyTorch and CUDA constraints

**[documented] The current PyTorch cutoff is 2.14 with CUDA 12.6 wheels.** PyTorch’s September 2026 announcement identifies these as the last published wheels covering sm_60; 2.15 drops the CUDA 12.6 binaries. Thus “all PyTorch after 2.5 lacks Pascal” is incorrect. [PyTorch release/packaging announcement](https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432).

**[documented] Engine extensions impose independent restrictions:** ExLlamaV3’s wheel matrix, for example, excludes sm_60 regardless of whether the surrounding PyTorch installation supports it. [ExLlamaV3 workflow](https://github.com/turboderp-org/exllamav3/blob/master/.github/workflows/build.yml).

**[inference] For any proposed environment, verify both the wheel and extensions.** This read-only check is useful but is not sufficient to certify the complete engine:

```bash
python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_arch_list())'
```

## 4. Model choice

**[inference] Optimize correct extraction records per second, not generated tokens per second.** With the earlier field-mapping failure rate, a smaller/faster model is beneficial only if it preserves the required semantic accuracy. Conversely, a slower model can win if it avoids retries.

### A focused shortlist

| Candidate | Evidence and reason to test |
|---|---|
| **Qwen2.5-14B-Instruct, current model** | **[inference] Keep as the reference.** First distinguish malformed field names from incorrect semantic mappings; these need different remedies. |
| **Qwen3.5-9B** | **[documented]** Official model card reports **IFEval 91.5** and **IFBench 64.5**. It is a dense model with hybrid Gated DeltaNet/attention layers. **[inference]** Strong first smaller-model candidate, but neither benchmark predicts this task’s accuracy or P100 speed. Its architecture also changes KV/state behavior. [Model card](https://huggingface.co/Qwen/Qwen3.5-9B). |
| **Gemma 4 12B Unified** | **[documented]** A current candidate—not merely Gemma 3—with 11.95B parameters. Google reports **MMLU-Pro 77.2%** and **GPQA Diamond 78.8%**, and documents llama.cpp integration. **[inference]** Worth a quality comparison; these are reasoning benchmarks, not exact-quote extraction tests. Compatibility with the installed May build is unverified, so treat it as a newer-build candidate. [Model card](https://ai.google.dev/gemma/docs/core/model_card_4), [developer guide](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/). |
| **Gemma 3 12B IT** | **[documented]** Google reports **FACTS Grounding 75.8** and **IFEval 88.9**. **[inference]** Useful older control because grounding is closer to your task than coding benchmarks, although it still does not measure verbatim extraction. [Model card](https://ai.google.dev/gemma/docs/core/model_card_3). |
| **Qwen3-14B / smaller Qwen3 dense models** | **[documented]** Qwen3 supports an explicit non-thinking mode. **[inference]** A reasonable same-family control, but I found no evidence making it preferable to Qwen3.5-9B for this particular task. [Qwen3-14B card](https://huggingface.co/Qwen/Qwen3-14B). |
| **Existing Qwen2.5-Coder-14B Q4_K_M** | **[inference]** Cheap to evaluate because it is already present. Coding specialization does not establish extraction superiority; changing model and quantization together also prevents attributing the result to either alone. |
| **Existing Qwen2.5-VL-3B** | **[inference]** Possible routing/classification candidate. Its quality on your labels is unknown; do not extrapolate extraction reliability from model size or vision capability. |

**[inference] Do not rank the vendor benchmark numbers above as a controlled head-to-head test.** Evaluation protocols, reasoning budgets and quantization differ from kala.

**[documented] Qwen3.5 thinks by default and supports disabling this through the chat template:**

```text
--chat-template-kwargs '{"enable_thinking":false}'
```

Its documentation says `/nothink` is not the supported Qwen3.5 switch. **[inference]** Benchmark non-thinking mode first for routing and extraction, then measure whether reasoning improves difficult cases enough to justify extra tokens. [Qwen3.5 instructions](https://huggingface.co/Qwen/Qwen3.5-9B#instruct-or-non-thinking-mode), [llama.cpp template argument](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp).

### Qwen3.6-35B-A3B on 16+12 GB

**[documented] It has 35B total parameters and approximately 3B activated per token, with hybrid attention and MoE layers.** The active count does not eliminate storage for inactive experts. [Official model card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B).

**[community] There is directly relevant dual-P100 evidence:** TheTriumphantFox reports Qwen3.6-35B-A3B Q4 at **256.68 prompt tok/s and 60.93 generation tok/s** after disabling Vulkan integer-dot/MMVQ paths, on two **16 GB** P100s. [Report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-15/qwen3.8-p100-tuning/REPORT.md).

**[inference] That makes your already-downloaded MoE worth testing, but not a 61 tok/s promise.** Differences include the 12 GB card, its bandwidth, PCIe topology, context, engine version and cooling. The 21.2 GB file leaves aggregate room in 28 GB, but each device must separately fit its layers, KV/state and temporary buffers.

**[inference] Start with layer split and an approximately capacity-proportional split, then inspect actual allocations:**

```text
--split-mode layer --tensor-split 4,3
```

The ratio is a starting allocation preference, not a guarantee of balanced execution or successful loading.

**[inference] For hundreds of independent requests, also test a different use of the second GPU: one complete 14B replica per card.** If the model plus a modest context fits the 12 GB card, independent replicas avoid inter-GPU transfers during inference and may outperform splitting that same 14B model for aggregate throughput. This is especially relevant to the x4 slot.

## 5. Other changes likely to matter

### Constrain structure and validate quotations

**[documented] llama.cpp converts a supported subset of JSON Schema into a sampling grammar.** Explicit property names, `required`, enums and `additionalProperties: false` can constrain output structure. The schema is **not automatically explained to the model in its prompt**. [Grammar documentation](https://github.com/ggml-org/llama.cpp/blob/5190c2e/grammars/README.md).

**[inference] This could eliminate the syntactic portion of the 21% field-name problem, but cannot fix values assigned to the wrong valid field.** Describe the schema’s semantics in the prompt as well as enforcing its structure.

**[inference] Validate each decoded JSON quote with an exact substring check against the original chunk.** A grammar cannot ordinarily guarantee this relationship. An alternative is selecting pre-labelled source spans and copying their text deterministically; that guarantees textual fidelity while leaving span-selection correctness to evaluation.

**[inference] Check repetition penalties.** Penalizing text repeated from the prompt conflicts with verbatim quotation. A useful controlled request configuration is:

```json
{
  "repeat_penalty": 1.0,
  "presence_penalty": 0.0,
  "frequency_penalty": 0.0,
  "dry_multiplier": 0.0
}
```

**[documented] These controls exist in the server API.** Their effectiveness depends on the active sampler configuration. [Server API](https://github.com/ggml-org/llama.cpp/blob/5190c2e/tools/server/README.md).

### Reuse a fixed prompt prefix

**[documented] With `cache_prompt: true`, llama-server compares against cached prompt tokens and evaluates the unseen suffix.** [Server API](https://github.com/ggml-org/llama.cpp/blob/5190c2e/tools/server/README.md).

**[inference] Put stable instructions, schema explanations and examples before the changing chunk.** Keep their serialization stable. With multiple slots, verify cache hits per slot rather than assuming one warmed prefix automatically warms every slot.

**[inference, calculated from your measurements] At 250 prompt tok/s, avoiding 500 repeated prefix tokens saves roughly two seconds per request before overhead.** This can matter more than decode optimization for short classifications.

### Quantization and batch sizes

**[inference] There is no verified Vulkan ranking for kala among Q4_0, Q4_K_S, Q4_K_M, IQ4_XS and Q8_0.** Test Q4_0 and Q4_1 as execution-cost candidates, IQ4_XS as another candidate, and Q4_K_M as a quality control. Smaller files need not execute faster.

**[community] A useful CUDA-specific P100 study supports that caution:** for one matrix shape, it reports GEMV times of **110.7 µs for Q4_1, 127.7 µs for Q4_0, 152.0 µs for Q4_K and 253 µs for Q6_K**. The repository acknowledges changed builds, mixed weight variants and AI-assisted research notes. These results justify experiments; they do not establish a Vulkan ordering. [Study and limitations](https://github.com/JVrachnis/pascal-llm-serving).

**[community] Smaller prompt batches have helped another dual-P100 Vulkan setup:** TheTriumphantFox found batch 256 faster than tested larger sizes for a different dense model. **[inference]** Compare `-b 512 -ub 256` with current `-b 1024 -ub 512`; retain FA initially to isolate the effect. [Report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-15/qwen3.8-p100-tuning/REPORT.md).

**[inference] Speculation and batching gains need not multiply.** Both increase the amount of work processed together. Measure their combination rather than multiplying separate speedups.

## Ranked “test on kala” list

**[inference] Use the same labelled extraction set throughout.** Record end-to-end time, valid-and-correct records, uncached prompt tokens, generated tokens, speculative acceptance, peak VRAM and energy. Until cooling is fixed, use matched cool starts and short comparisons; then repeat the winning configurations over a sustained batch.

All expected effects below are hypotheses to measure.

| Rank | What to run/change | Expected effect and risk | New code on kala? |
|---:|---|---|---|
| **1** | Enforce the real JSON schema; validate decoded quotes; test neutral repetition penalties. | **[inference]** Fewer malformed results and retries. Semantic mapping errors remain; constraints can expose a weak prompt. | **No new engine.** Client validation may need a small change. |
| **2** | Stable shared prefix and `"cache_prompt": true`; confirm cache-hit timings. | **[inference]** Lower repeated prefill cost, especially for routing. Benefit depends on prefix size and slot reuse. | **No.** |
| **3** | `--spec-type ngram-simple --spec-ngram-simple-size-n 8 --spec-ngram-simple-size-m 16`; compare `none` and 12/48. | **[inference]** Faster long quotations. Short quotes or rejected drafts may yield no gain or regress. | **No.** |
| **4** | `--parallel 2 --ctx-size 8192 --no-kv-unified`, with two simultaneous requests; then four slots if context permits. | **[inference]** Higher aggregate throughput. Risks: reduced per-slot context, latency and higher power. Test speculation separately first. | **No.** |
| **5** | Add `--cache-type-k q8_0 --cache-type-v q8_0` to the winning concurrency configuration. | **[inference]** More memory headroom. Speed and quality effects unknown. | **No.** |
| **6** | Compare `-b 512 -ub 256` with `-b 1024 -ub 512`, keeping FA on. | **[inference]** Possible prefill improvement or smaller scratch allocation. Model-specific regression possible. | **No.** |
| **7** | Evaluate Qwen3.5-9B and Gemma 4 12B against current Qwen2.5-14B; disable thinking where supported. Include the already-present Coder model as a cheap control. | **[inference]** Potentially better quality per elapsed second. Main risks are semantic regressions and architecture/build compatibility. | **New weights; newer engine may be needed**, especially Gemma 4 12B. |
| **8** | Compare same-source Q4_0/Q4_1/IQ4_XS with current Q4_K_S, using the same quality set. | **[inference]** Possible reduction in kernel cost. Quantization can worsen extraction; avoid attributing differences between different fine-tunes to quantization. | **Weights only** if compatible GGUFs are available. |
| **9** | Once installed: compare two independent 14B replicas against Qwen3.6-35B-A3B layer split, initially `--tensor-split 4,3`. | **[inference]** Replicas target batch throughput; MoE targets a different speed/quality tradeoff. Risks: 12 GB allocation limits and transfer overhead. | **Possibly no new engine** for replicas; MoE/backend compatibility must be checked. |
| **10** | Only after n-gram results: `--spec-type draft-simple --model-draft /path/to/Qwen2.5-0.5B-Instruct.gguf --spec-draft-n-max 3`. | **[inference]** May help predictable non-quote output. Draft overhead, compatibility and low acceptance can erase the gain. | **New weights, no new engine expected.** |

**[inference] I would defer an engine migration until these tests establish what the existing engine leaves on the table.** None of the alternative-engine evidence above demonstrates a clear win over kala’s measured Vulkan baseline for this workload.