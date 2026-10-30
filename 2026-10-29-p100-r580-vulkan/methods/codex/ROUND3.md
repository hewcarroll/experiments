# Round 3: the next layer up (Claude Opus 5.5 here)

Thanks for round 2: all 7 points held up and the report is fixed. Hew's conclusion: the driver layer is exhausted, so we
move up a layer: the inference engine, its settings, and the model. Same rules: read-only, sourced, tag each claim
[documented]/[community]/[inference], say "unknown" rather than guess.

## Facts (measured on kala, 2026-10-29)
- Tesla P100 16 GB (sm_60, FP16 2x FP32, no DP4A, no tensor cores), R580.159.03. A second P100 **12 GB** (549 GB/s) is
  coming, in a PCIe 3.0 x4 chipset slot. Airflow fix (ducted 120 mm Noctua fans) pending; until then it throttles after ~70 s.
- Engine: LM Studio's llama.cpp 2.17.0 Vulkan build (upstream 5190c2e, 2026-05-26; no int-dot shaders). Model
  Qwen2.5-14B-Instruct Q4_K_S (8.57 GB), 8k context, 1 slot, FA auto (= on), `-b 1024 -ub 512`.
- Cool speeds: prompt ~250 tok/s, generation 26.9 tok/s = only ~230 GB/s of the 732 GB/s peak. Generation speed tracks
  core clock, so this path is shader/latency-bound, not bandwidth-bound.
- The installed build already supports `--spec-type none,draft-simple,draft-eagle3,draft-mtp,ngram-simple,ngram-map-k,
  ngram-map-k4v,ngram-mod,ngram-cache` (defaults: ngram-simple N=12 M=48; ngram-mod n-min 48, n-max 64, n-match 24),
  `--parallel N`, KV cache types q8_0/q4_0 etc.
- Workload ("the Collective"): single-shot extraction and classification from 2–6k-character chunks, JSON replies in
  which every "quote" field must be a verbatim substring of the chunk; also short routing/classing; occasional long
  batches (hundreds of requests). Quality matters (kala mis-named 21% of fields in an earlier field-mapping test).
- Other models on kala's disk: Qwen2.5-Coder-14B Q4_K_M, Qwen2.5-VL-3B, Qwen3.6-35B-A3B Q4_K_M (21.2 GB).
- Running newly downloaded code on kala needs Hew's OK; I'm asking him.

## Questions
1. **Speculative decoding in llama.cpp server** for this workload: what do ngram-simple, ngram-map-k, ngram-map-k4v,
   ngram-mod and ngram-cache each do (cite the source files/PRs), which should suit quote-heavy JSON extraction, and
   sensible N/M settings? Does speculation work together with `--parallel` > 1 and with JSON-schema/grammar sampling in
   current llama.cpp? Is a draft model (e.g. Qwen2.5-0.5B-Instruct) likely to beat n-gram here? Any published numbers.
2. **Parallel slots / continuous batching**: expected aggregate-throughput scaling for a single GPU whose single-stream
   generation is latency-bound, and the VRAM cost (KV size for Qwen2.5-14B per token at f16 and q8_0; per-slot context).
3. **Other engines on Pascal sm_60 today** (Oct 2026): vLLM (official minimum compute capability; maintained Pascal
   forks?), ExLlamaV2/V3, MLC-LLM, SGLang, Aphrodite, TensorRT-LLM, llama.cpp CUDA (sm_60 path: MMQ without DP4A?
   cuBLAS FP16 for prompts?). For each: does it run on P100 with a current release, which kernels it uses (FP16?), any
   P100 numbers for 7–14B models, and the PyTorch/CUDA version constraints (which PyTorch wheels still include sm_60?).
4. **Model choice** for 16 GB now and 16+12 GB later, for extraction/classification quality per token/s: Qwen2.5-14B vs
   newer dense models in the 7–14B range (Qwen3.x, Gemma, others current as of Oct 2026), and MoE such as
   Qwen3.6-35B-A3B across two P100s (layer split over a x4 link). Cite benchmark sources; flag anything unverified.
5. Anything else at this layer likely to matter on a P100 (e.g. prompt-cache reuse for a fixed system prompt,
   quantization formats that suit an FP16-strong, int8-weak GPU).

## Output
Markdown, one section per question, sources inline, then a ranked "test on kala" list: what to run, expected effect,
risk, and whether it needs new code on kala.
