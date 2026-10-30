# Round 2: challenge Claude's conclusions (Claude Opus 5.5 here)

Thanks for round 1. I verified most of your sources (R580 LTSB EOL June 2028 in NVIDIA's table; 580.196.07 dated
2026-10-21 in releases.json; the 580.65.06 clock-reporting note; -acp removed in nvidia-smi v465; the two
TheTriumphantFox P100 reports; issue #18895's `int dot: 1` P100 line; NVIDIA's CUDA 8 blog listing DP4A on
GP102/GP104/GP106 only). I could not find the 580.173.02 Vulkan-semaphore fix in NVIDIA's *data-center* release
notes; GamingOnLinux reports it for the Unix driver.

Since then I measured kala directly. Please try to break my conclusions below. Read-only; use web search only if
you need to check a claim. Be concrete and say which of my numbers or inferences you think are wrong and why.

## New measurements (kala, 2026-10-29, R580.159.03, proprietary module)

**NVML probe (read-only calls):** `nvmlDeviceGetGpcClkMinMaxVfOffset` = (0, 0); `MemClk` min/max offset (0, 0);
`nvmlDeviceGetClockOffsets(GRAPHICS, P0)` = 0 with min/max 0/0; `nvmlDeviceGetPerformanceModes` string says
`nvclockeditable=0, memclockeditable=0`. Supported P-states: P0 only (graphics 405–1328 MHz, memory fixed 715).
Temperature thresholds: SHUTDOWN 85, SLOWDOWN 82; GPU_MAX and MEM_MAX NOT_SUPPORTED; memory temperature field
NOT_SUPPORTED. `nvmlDeviceGetTotalEnergyConsumption` NOT_SUPPORTED. `nvmlDeviceGetAPIRestriction(SET_APPLICATION_CLOCKS)`
NOT_SUPPORTED. Power-limit constraints 125–250 W. Persistence off. ECC on.

**vulkaninfo (R580.159.03, P100):** shaderFloat16 = true, storageBuffer16BitAccess = true, shaderInt8 = true,
shaderIntegerDotProduct = true, integerDotProduct4x8BitPacked{Unsigned,Signed,MixedSignedness}Accelerated = **true**
(8-bit unpacked variants false), subgroupSize 32 (min = max = 32), subgroupSizeControl = true, no
VK_KHR_cooperative_matrix, maxComputeSharedMemorySize 49152, maxMemoryAllocationSize 0xffe00000.

**Production llama.cpp build:** LM Studio's bundled 2.17.0 Vulkan backend (`llama-server --version` = 5190c2e).
Its `libggml-vulkan.so` contains no `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT` string and no `*_q8_1` matmul or
mul_mat_vec shader names (only `quantize_q8_1*`), while `matmul_q4_k_f16*` shaders are present. I read that as: built
without `GGML_VULKAN_INTEGER_DOT_GLSLC_SUPPORT`, so production never takes the int-dot path. In upstream b11988
source, `ggml_vk_mul_mat_b_type()` returns Q8_1 first whenever `can_quantize_y && available(Q8_1)`, and
`ggml_vk_should_use_mmvq()` returns true on NVIDIA for most quant types when k > 4096 (Q8_0/MXFP4 only on
NVIDIA_PRE_TURING); the P100 is classified NVIDIA_PRE_TURING because it lacks VK_KHR_cooperative_matrix.

**Sustained load on the live 14B** (Qwen2.5-14B-Instruct Q4_K_S, 1,719-token uncached prompt + 512 forced tokens,
10 requests back to back, telemetry at 2 Hz):

| req | prompt tok/s | gen tok/s | gen-phase SM clock (median) | gen-phase power avg | gen J/token | prompt J/token |
|---|---|---|---|---|---|---|
| 0 | 243.4 | 26.90 | 1328 | 180 W | 6.56 | 0.53 |
| 1 | 250.0 | 26.90 | 1328 | 187 W | 6.62 | 0.62 |
| 2 | 249.6 | 26.57 | 1328 | 184 W | 6.95 | 0.59 |
| 3 | 217.5 | 14.64 | 632 | 97 W | 6.52 | 0.54 |
| 4 | 131.5 | 8.40 | 405 | 75 W | 8.78 | 0.58 |
| 5 | 105.1 | 7.75 | 405 | 72 W | 9.20 | 0.72 |
| 6 | 99.6 | 7.32 | 405 | 70 W | 9.50 | 0.71 |
| 7 | 97.6 | 6.99 | 405 | 69 W | 9.83 | 0.72 |
| 8 | 101.3 | 6.97 | 405 | 69 W | 9.79 | 0.72 |
| 9 | 93.7 | 6.79 | 405 | 69 W | 10.08 | 0.73 |

- Idle before load: 44–45 C, 28–31 W, 405 MHz. Under load from cold: 1328 MHz (event reasons none), 139–203 W,
  temperature rose ~2 C per 5 s and reached 79 C after ~70 s. Then SW Thermal Slowdown (0x20) walked the clock down
  to 405 MHz; steady state 405 MHz at ~67–70 W and 78–80 C for the remaining ~8 minutes.
- Cool-down after load: 78 -> 73 C in 50 s at ~38–40 W idle. Idle power is ~10 W higher at 75 C than at 45 C.
- J/token = sum(power x dt) over the phase window / tokens, with phase windows from the server's own timings.
- Owner had improved something since Oct 20 (idle was 71–78 C then); fans/shroud details unknown to me.

## My draft conclusions — attack these

1. **Sustained throughput is capped by heat rejection (~69 W at 79 C), and no R580 / NVML / Vulkan setting can
   raise that cap.** The minimum power limit (125 W) and the lowest settable application clock (544 MHz) are both
   above the throttled steady state (405 MHz, ~69 W), so neither can hold the card below the 80 C max operating
   temperature under sustained load. The only fix for sustained speed is airflow through the fin stack
   (NVIDIA brief: >= 12 CFM fully ducted at 30 C inlet, 15 at 35 C, 19 at 40 C).
2. **Throttled operation is also less efficient**: ~9.5–10 J/generated token vs ~6.6 cool (+45%), plausibly
   because leakage rises with temperature. So better cooling buys speed AND efficiency.
3. **Cool-phase knobs** (need root, not yet tested): an explicit `nvidia-smi -ac 715,<clk>` (NVML says setting
   application clocks disables auto boost on Pascal and newer) or `-pl 125..175` should cut watts and J/token in
   short bursts and delay the throttle onset, with little loss in memory-bound generation but some loss in prompt
   speed. They do not change the sustained cap. `-ac 715,1328` adds nothing since the card already runs 1328 MHz.
4. **Biggest software trap**: any newer upstream / Ollama Vulkan build will take the int-dot (Q8_1 MMQ) and MMVQ
   paths on GP100 because the driver reports packed 4x8 dot as accelerated; per the community P100 reports that
   collapses prompt speed ~10–20x. Use `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1` and test `GGML_VK_DISABLE_MMVQ=1`
   with any newer build. Production is safe today only because its build lacks the int-dot shaders; keep the unit
   pinned to that backend directory.
5. ECC off: no gain. Undervolt / clock offsets / -lgc: unavailable on this card. Deeper P-states: none.
   R580.196.07: optional maintenance update, no expected speed change.
6. **Inference about the 2nd P100**: splitting a model by layers across two cards means each card works about half
   the time during generation, so each card dissipates about half the heat; if each card's cooling sheds ~69 W at
   79 C, the pair might sustain roughly 2x the throttled single-card throughput even for models that fit on one card.

## Questions
- Which of 1–6 are wrong, overstated, or missing a better-supported alternative? Especially: is there any
  driver-side mechanism that changes the steady state that I am missing (e.g. how SW thermal capping chooses clocks,
  any thermal-target setting reachable on Tesla, `nvidia-smi --gpu-target-temp`/`-gtt` on Pascal)?
- Is my J/token method sound with 2 Hz power samples, given NVIDIA's note that reported values changed in R580?
- Is the 2nd-P100 inference (6) physically reasonable? What would invalidate it?
- What exact, minimal root test sequence would you give the owner to measure the cool-phase effect of -ac / -pl
  (commands, how long to run, what to record, how to revert)?

Answer in Markdown, short sections, each claim tagged [documented]/[community]/[inference] with sources where used.
