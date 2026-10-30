**[inference] Your thermal diagnosis is strong. The overstatements are “software cannot improve sustained throughput,” “little generation loss from clock reduction,” and “half utilization means half board power.”** I also find a numerical inconsistency in the energy table. None of these overturns cooling as the highest-priority intervention.

## 1. Heat rejection: strong diagnosis, overly absolute conclusion

**[inference]** Your measurements establish approximately **69 W board power at the observed hot operating point**, under this workload and cooling arrangement. They do not establish a universal 69 W cooling capacity: inlet temperature, heat distribution across components, thermal contact, and potentially unreported sensors remain uncontrolled.

**[inference]** The argument comparing minimum settings with observed throttling is insufficient:

- A **125 W power limit is a ceiling**, not a requirement to consume 125 W.
- A **544 MHz application-clock setting does not prevent thermal control from going lower**.
- Neither setting’s numerical minimum proves what temperature or throughput its resulting operating trajectory will reach.

**[documented]** Application clocks remain subordinate to thermal and power restrictions. NVIDIA’s historical NVML header also distinguishes explicitly setting application clocks from restoring automatic boosting. [NVIDIA NVML header history](https://github.com/NVIDIA/go-nvml/blob/main/pkg/nvml/nvml.h).

**[inference]** Nevertheless, your practical prediction is reasonable: a power cap that becomes inactive once thermal throttling reduces consumption below it probably will not materially improve the final operating point **with otherwise identical execution**.

**[inference]** The statement that *only airflow can improve sustained speed* is wrong. More efficient kernels can produce more tokens within the same thermal budget. Different clock policy or workload pacing could also change efficiency, although neither is demonstrated here. Improving the physical thermal path—including inlet conditions and heatsink contact, not just fan airflow—is the best-supported remedy for the collapse you measured.

### Thermal-target control remains one unqueried capability

**[documented]** `-gtt` exists, requires root, and operates only within device-supported target limits. The documentation does not promise P100 support. Check this read-only:

```bash
nvidia-smi -i 0 -q -d TEMPERATURE,SUPPORTED_GPU_TARGET_TEMP
```

Also query NVML’s `ACOUSTIC_MIN`, `ACOUSTIC_CURR`, and `ACOUSTIC_MAX`; these are separate from `GPU_MAX` and `MEM_MAX`. [nvidia-smi target-temperature option](https://docs.nvidia.com/deploy/nvidia-smi/index.html), [NVML temperature-threshold enums](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceEnums.html).

**[community]** A published P100 report with the same VBIOS revision shows target temperature and both supported target limits as `N/A`, although on an older driver. [P100 XML report](https://bbs.fit2cloud.com/t/topic/11007).

**[inference]** Your current probe has not conclusively excluded `-gtt`, but I expect the additional queries to close that gap rather than reveal a useful control. I found no documented P100 knob for changing the SW thermal controller’s hysteresis, clock-selection algorithm, or thermal floor. Raising a target would not improve heat transfer at a fixed temperature.

## 2. Efficiency: degradation established; leakage attribution unproven

**[inference]** “Hot throttled operation uses more board joules per generated token” is supported. Depending on which rows you compare, the increase is approximately **44–54%**, rather than uniformly 45%.

**[inference]** Leakage is not needed to explain most of that increase. Consider the illustrative decomposition

\[
E_{\rm token}=\frac{P_{\rm fixed}}{r}+E_{\rm work}.
\]

With a hypothetical constant **30 W** background component, its contribution rises from:

- \(30/26.90 = 1.12\) J/token;
- to \(30/6.79 = 4.42\) J/token.

That **3.30 J/token** increase is already close to your measured increase from **6.56 to 10.08 J/token**. This is a counterexample to the leakage explanation, not a fitted physical decomposition of the P100.

**[inference]** The extra approximately 10 W during hot idle is consistent with temperature-dependent losses, but it does not isolate transistor leakage. You would need matched clocks, context/activity, fan behavior and other state to make that attribution.

**[inference]** Better cooling should improve both sustained speed and board energy efficiency in this measured regime. Net system efficiency must additionally include the cooling fans’ consumption.

## 3. Cool-phase clock/power knobs: test the tradeoff, do not predict it

**[inference]** Lower clocks or a binding power cap should reduce instantaneous power, but **lower J/token and little generation-speed loss are hypotheses**.

Your own results challenge the “memory-bound, therefore insensitive to core clock” premise:

- **1328/405 ≈ 3.28×** reported clock ratio;
- **26.90/6.79 ≈ 3.96×** generation-rate ratio;
- memory clock reportedly stays fixed.

**[inference]** That does not prove a purely core-bound workload: thermal duty modulation and the R580 reporting semantics complicate interpretation. It does show that fixed memory frequency alone does not preserve generation speed. Dequantization, shader execution and memory-system utilization can still depend on core operation.

**[inference]** I agree that `-ac 715,1328` offers no demonstrated higher frequency than the current cool baseline. It can still change **policy**, so it is not necessarily a behavioral no-op.

**[documented]** On Pascal, explicitly setting application clocks and resetting them have different boost-policy semantics. Therefore **revert with `-rac`, not merely `-ac 715,1189`**. The latter can leave the card explicitly constrained despite matching the displayed default application clock. [Historical NVML header change showing the removed explanatory documentation](https://cos.googlesource.com/third_party/nvidia-container-toolkit/%2B/a10c54eedd1154ea26546b8675169d5afec7d686%5E1..a10c54eedd1154ea26546b8675169d5afec7d686/).

## 4. Vulkan trap: credible, but build-specific rather than inevitable

**[inference]** Your binary inspection is strong evidence that the production library was compiled without integer-dot support. The absent environment-variable string is particularly useful because upstream places that check inside the compiler-support guard. It is not absolute proof if LM Studio patched the implementation or the process loads a different library.

**[documented]** Both `5190c2e` and `b11988` guard integer-dot initialization with `GGML_VULKAN_INTEGER_DOT_GLSLC_SUPPORT`. The behavior is therefore **not simply an old-versus-new version distinction**. A differently compiled build of the same older commit can expose the risky path. [5190c2e source](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/ggml-vulkan.cpp), [b11988 source](https://github.com/ggml-org/llama.cpp/blob/b11988/ggml/src/ggml-vulkan/ggml-vulkan.cpp).

**[documented]** Your reading of `b11988`’s Q8_1 preference and NVIDIA MMVQ heuristic is substantially correct, but surrounding gates also check input type/layout, precision eligibility and pipeline availability. “Any newer build will take these paths” is too broad. Same sources.

**[documented] Important simplification:** on these inspected sources, the relevant MMVQ selection requires `device->integer_dot_product`. Thus **disabling integer dot already excludes that MMVQ path on this P100**. Testing `GGML_VK_DISABLE_MMVQ=1` is useful **independently with integer dot enabled**, to distinguish prompt and generation effects; adding it after integer dot is disabled should be redundant for those paths.

**[community]** The dramatic prompt regressions are real reports, but not guaranteed magnitudes for this model. In the Devstral experiment, integer-dot disabling improved prompt processing while reducing generation speed. [Devstral report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-17/devstral-p100-tuning/REPORT.md).

**[inference]** Retain the known-good complete backend bundle as a rollback, but permanent pinning is unnecessary if a newer bundle passes controlled testing with integer dot disabled. Confirm the actual loaded library and startup capabilities, not just `llama-server --version`.

## 5. Unavailable controls and the driver update

**[inference]** Your direct probes now justify the stronger card-specific conclusion: **no exposed nonzero offsets and no exposed deeper P-state on this card/driver**. They also eliminate application-clock permission delegation as a useful avenue here.

**[documented]** `-lgc` requires Volta or newer. ECC’s documented HBM2 capacity/bandwidth overhead is absent; that supports “no documented capacity/bandwidth gain,” not a proof of exactly zero possible power difference. [NVML locked-clock API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html), [NVIDIA’s P100 HBM2 description](https://developer.nvidia.com/blog/inside-pascal/).

**[documented]** You are correct about the release-note distinction: the semaphore fix is in NVIDIA’s **Unix/display-driver release highlights**, not the data-center notes you inspected. It is available from NVIDIA directly, not only GamingOnLinux: see the **580.173.02** entry in [NVIDIA’s download release history](https://www.nvidia.co.uk/Download/processFind.aspx?ctk=0&lang=en-uk&lid=2&osid=12&pfid=845&psid=101&whql=).

**[inference]** Describe 580.196.07 as “maintenance update with **unquantified performance effect**.” “No expected speed change” is reasonable planning shorthand, but stronger than the evidence permits.

## 6. Two P100s: physically plausible benefit, incorrect half-power model

**[inference]** For one sequence with layer splitting, execution is largely serial across the GPUs. Distributing layers can distribute heat, but it does not automatically halve **board** power.

A better first approximation is:

\[
P_{\rm average}=P_{\rm waiting}+d(P_{\rm active}-P_{\rm waiting}).
\]

**[inference]** Using your approximate **180 W active**, **30 W waiting**, and **50% duty** gives **105 W per card**, not 90 W—and still well above the hypothesized 69 W cooling limit. With those assumptions, 50% duty fits 69 W only if active power is approximately **108 W or less**.

**[inference]** Roughly twice the throttled throughput remains physically possible if each card processes approximately half the per-token work, both maintain suitable clocks, and transfer overhead is small. It is not established by the duty-cycle argument.

**[inference]** Things that invalidate the simple estimate:

- Unequal layer execution times: equal layer counts do not guarantee equal duty cycles.
- Waiting power remains substantial; inter-layer waits may be too short to reach measured idle power.
- The second card raises inlet temperature or obstructs the first card’s airflow.
- PCIe transfers, synchronization, or host staging become significant.
- The second card has a different thermal path and memory performance.
- Prefill behavior differs from single-token generation.

**[documented]** The PCIe 12 GB P100 has **549 GB/s** specified memory bandwidth versus **732 GB/s** for the 16 GB version. It is not an identical performance partner. [P100 PCIe Product Brief, Table 2](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-product-literature/NV-tesla-p100-pcie-PB-08248-001-v01.pdf#page=6).

**[inference]** Test both per-card energy traces and total request time. Reduced utilization alone cannot establish either improved efficiency or useful thermal sharing.

## 7. Energy measurement: sound method, inconsistent table

**[documented]** NVML reports instantaneous power for Pascal; the documented one-second averaging behavior applies to newer architectures. The R580 note you cite concerns **clock reporting**, not a transformation of power into an unusable energy signal. [NVML `nvmlDeviceGetPowerUsage`](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceQueries.html), [R580 clock-reporting change](https://docs.nvidia.com/datacenter/tesla/pdf/NVIDIA_Data_Center_GPU_Driver_Release_Notes_580_v1.0.pdf).

**[inference]** Timestamped numerical integration is appropriate for approximate board energy. At 2 Hz, however, short prompt phases and phase boundaries deserve more scrutiny than long steady generation intervals.

**[inference] The table must satisfy this identity** if all three quantities use the same interval and token count:

\[
\frac{E}{N}=\frac{\bar P}{N/T}.
\]

For request 1:

\[
187/26.90=6.95\ {\rm J/token},
\]

whereas **6.62 J/token implies 178.08 W**, not 187 W. Request 0 similarly gives **6.69**, rather than **6.56**. These differences exceed the displayed rounding.

**[inference]** Check arithmetic-versus-time-weighted power means, different phase masks, unintegrated boundary intervals, and whether server evaluation duration equals the wall-clock interval integrated. A server duration alone does not locate that phase precisely on the telemetry timeline.

**[inference]** Minimal validation:

1. Use actual sample timestamps and interpolate/clamp integration at phase boundaries.
2. Verify the identity above automatically.
3. Shift boundaries by ±0.5 seconds as a sensitivity check, not a formal error bound.
4. Cross-check whole-request energy, which is less sensitive to the prompt/generation split.
5. Repeat one representative run at a faster polling cadence; agreement is more useful than assuming independent sensor updates.

**[inference]** I would trust the broad hot-versus-cool degradation provisionally; I would not publish hundredth-J/token precision until this reconciliation is complete.

## 8. Minimal root test sequence

**[inference — proposed protocol]** Screen four conditions, one request each, then repeat the baseline and apparent winner three times. Keep the current production backend, model and request unchanged.

**[documented]** These setting commands require root; queries do not. Persistence preserves initialization state between clients. [nvidia-smi controls](https://docs.nvidia.com/deploy/nvidia-smi/index.html), [state persistence](https://docs.nvidia.com/deploy/driver-persistence/data-persistence.html).

First identify the GPU and capture its original settings:

```bash
nvidia-smi -L
GPU='GPU-REPLACE-WITH-P100-UUID'

nvidia-smi -i "$GPU" -q -d CLOCK,POWER,PERFORMANCE
sudo nvidia-smi -i "$GPU" -pm 1
```

**[inference — proposed protocol]** Apply each condition separately, between requests:

| Condition | Commands |
|---|---|
| **A: automatic clocks, default cap** | `sudo nvidia-smi -i "$GPU" -rac`<br>`sudo nvidia-smi -i "$GPU" -pl 250` |
| **B: explicit 1189 MHz, default cap** | `sudo nvidia-smi -i "$GPU" -pl 250`<br>`sudo nvidia-smi -i "$GPU" -ac 715,1189` |
| **C: automatic clocks, 175 W** | `sudo nvidia-smi -i "$GPU" -rac`<br>`sudo nvidia-smi -i "$GPU" -pl 175` |
| **D: automatic clocks, 125 W** | `sudo nvidia-smi -i "$GPU" -rac`<br>`sudo nvidia-smi -i "$GPU" -pl 125` |

**[inference — proposed protocol]** Before every measured request:

- Keep the model loaded and perform any shader warm-up beforehand.
- Wait for approximately **44–47°C** and a stable idle-power baseline; do not use a fixed cooldown duration.
- Run **one identical uncached 1,719-token prompt plus 512 forced generated tokens**. Baseline duration should be about **26 seconds**, calculated from your cool rates.
- If thermal slowdown appears, classify the run as thermally affected rather than a clean cool-phase comparison.
- Verify condition B actually changes observed under-load behavior. A successful setter alone is insufficient.

**[inference — proposed protocol]** Record timestamped power, temperature, graphics/SM/memory clocks, clock-event reasons, actual prompt/generated counts, phase boundaries and durations. Report both tokens/s and integrated J/token.

**[inference — proposed protocol]** To test your *sustained* claim rather than merely onset delay, follow with one **10-minute** run under condition D. An additional `-ac 715,544` run at the default cap directly tests your lowest-clock argument, but is a diagnostic experiment, not my proposed performance setting.

Restore the supplied original configuration:

```bash
sudo nvidia-smi -i "$GPU" -rac
sudo nvidia-smi -i "$GPU" -pl 250
sudo nvidia-smi -i "$GPU" -pm 0
nvidia-smi -i "$GPU" -q -d CLOCK,POWER,PERFORMANCE
```

**[inference]** The decisive result is whether a setting improves measured joules/token or sustained throughput—not merely whether it postpones the first thermal event.