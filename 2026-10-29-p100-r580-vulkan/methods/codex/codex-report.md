**The most promising software tests are Vulkan kernel-path selection, explicit flash attention, power caps, and a newer R580 maintenance release.** I found no verified GP100 undervolting method or documented benefit from disabling HBM2 ECC. Kala’s previous thermal collapse remains the largest demonstrated performance loss.

Nothing was modified. Commands below are proposed experiments. **[documented]** means NVIDIA/Khronos documentation or upstream source; **[community]** means a third-party measurement; **[inference]** means an interpretation or test hypothesis. Unknowns are stated explicitly.

## 1. R580 + Pascal support status

- **[documented] R580 is Pascal’s final driver branch; CUDA 12.x is its final toolkit family.** The driver reporting “CUDA 13.0” does not establish CUDA 13 compilation/library support for `sm_60`. NVIDIA lists these separately in its [CUDA Toolkit, Driver, and Architecture Matrix](https://docs.nvidia.com/datacenter/tesla/drivers/latest/cuda-toolkit-driver-and-architecture-matrix.html).
- **[documented] NVIDIA’s data-center support table identifies R580 as an LTSB with EOL in June 2028.** Its LTSB policy provides approximately three years of maintenance, including bug and critical-security fixes. This is the appropriate branch lifecycle reference for Tesla; do not substitute a GeForce or workstation support deadline. Sources: [Supported Drivers and CUDA Toolkit Versions, Table 2](https://docs.nvidia.com/datacenter/tesla/drivers/latest/supported-drivers-and-cuda-toolkit-versions.html), [Driver Lifecycle](https://docs.nvidia.com/datacenter/tesla/drivers/latest/driver-lifecycle.html).
- **Unknown:** I found no separate public, P100-specific R580 maintenance schedule establishing an earlier “security-only” transition.

Relevant changes:

| Release | Finding and relevance |
|---|---|
| **580.65.06** | **[documented]** Fixed intermittent llama.cpp Vulkan crashes on exit. Already incorporated in kala’s driver. [NVIDIA release announcement](https://forums.developer.nvidia.com/t/580-release-feedback-discussion/341205). |
| **580.65.06** | **[documented]** Changed NVML/nvidia-smi/nvidia-settings clock reporting to values before thermal and idle slowdowns. **[inference]** Assess throughput and clock-event reasons alongside clock readings; reported frequency alone is insufficient. [Data Center Release Notes, §1.2](https://docs.nvidia.com/datacenter/tesla/pdf/NVIDIA_Data_Center_GPU_Driver_Release_Notes_580_v1.0.pdf). |
| **580.173.02** | **[documented]** Fixed delayed wakeups when multiple threads wait on one Vulkan semaphore, which could reduce application performance. This is newer than kala’s driver. **[inference]** Relevant enough to test, but no P100/llama.cpp speedup is published. [NVIDIA release highlights, 25 June 2026 entry](https://www.nvidia.co.uk/Download/processFind.aspx?ctk=0&lang=en-uk&lid=2&osid=12&pfid=845&psid=101&whql=). |
| **580.196.07** | **[documented]** Released 21 October 2026; a current R580 maintenance candidate. No documented GP100-specific inference acceleration found. [NVIDIA driver archive](https://developer.nvidia.com/datacenter-driver-archive), [release notes](https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-580-196-07/index.html). |

**Unknown:** I found no verified R580 regression specifically explaining kala’s sustained GP100 inference slowdown. The measured thermal-event bit and throughput collapse are stronger evidence than a driver-regression hypothesis.

## 2. Clock and power controls that actually apply

The distinction between **architecture eligibility** and **a feature implemented on this particular board** matters, especially for clock offsets.

| Control | GP100 status | Root/privileges | Survives reboot? | Source/confidence |
|---|---|---|---|---|
| `nvidia-smi -ac MEM,GRAPHICS` | Supported application-clock mechanism; use kala’s enumerated pairs. Thermal/power controls can override it. | Root by default; potentially delegable through NVML restrictions. | No. | **[documented]** [NVML `nvmlDeviceSetApplicationsClocks`](https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlDeviceCommands.html). |
| `-rac` | Resets application clocks. | Same permission considerations. | Reset restores defaults. | **[documented]** Same NVML reference. |
| `-pl WATTS` | Supported; kala reports 125–250 W. | Root. | No. | **[documented]** [NVML `nvmlDeviceSetPowerManagementLimit`](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html); range from user measurements. |
| `-pm 1` / `-pm 0` | Supported on Linux. Keeps the GPU initialized between clients. | Root. | No. | **[documented]** [NVML `nvmlDeviceSetPersistenceMode`](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html). |
| `-e 0` / `-e 1` | Supported ECC configuration; change takes effect after reboot. | Root. | **Yes**, until changed again. | **[documented]** [NVML ECC command](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html), [board-state persistence](https://docs.nvidia.com/deploy/driver-persistence/data-persistence.html). |
| `-lgc` / `-rgc` | **Not the GP100 mechanism:** GPU locked-clock API requires Volta or newer. | Root where supported. | No where supported. | **[documented]** [NVML locked-clock API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html). |
| `-acp` | **Removed**, not a usable R580 permission knob. | N/A. | N/A. | **[documented]** [nvidia-smi changelog, v460→v465](https://docs.nvidia.com/deploy/nvidia-smi/index.html). |
| `nvmlDeviceSetAPIRestriction` | API alternative for application-clock permission, subject to device support. | Root to change restrictions. | No. | **[documented]** [NVML API restrictions](https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlDeviceCommands.html), [state lifetime](https://docs.nvidia.com/deploy/driver-persistence/data-persistence.html). |
| `nvmlDeviceSetGpcClkVfOffset` | Documentation says Maxwell onward, but permits `NVML_ERROR_NOT_SUPPORTED`. **Successful GP100 support unverified.** | GP100 behavior unverified; do not assume unprivileged access. | GP100 behavior unknown. | **[documented/unknown]** [legacy offset API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html). |
| `nvmlDeviceSetClockOffsets` | Maxwell-or-newer *fully supported devices*, with a device-specific unsupported return. **Not proof that Tesla P100 accepts offsets.** | Privileged user. | GP100 behavior unknown. | **[documented/unknown]** [current offset API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceQueries.html). |
| nvidia-settings / Coolbits | NVIDIA documents clock-offset Coolbits support for **certain GeForce GPUs**, not a GP100 Tesla guarantee. Uses an NVIDIA X server/NV-CONTROL; a physical monitor is not inherently required. | System X configuration generally needs root; authorized X clients need not be root. | Saved X configuration can persist; do not assume runtime offsets persist. | **[documented/inference]** [R580 X configuration, `Coolbits` and `AllowEmptyInitialConfiguration`](https://download.nvidia.com/XFree86/Linux-x86_64/580.65.06/README/xconfigoptions.html). |

**[documented]** Application clocks, their permissions, and software power caps have GPU-initialization lifetime: they can disappear when the last client exits and the GPU deinitializes. Persistence mode can preserve that state between jobs; it does not make it reboot-persistent. [NVIDIA, Data Persistence](https://docs.nvidia.com/deploy/driver-persistence/data-persistence.html).

**[inference]** Persistence mode should not materially accelerate an already-running, continuously loaded llama-server. Its practical benefit here is avoiding reinitialization between runs and keeping experiment settings stable.

## 3. Undervolting

**Unknown: no supported or reproducibly demonstrated GP100 Linux method was verified for lowering voltage at a fixed clock.**

- **[documented]** NVML’s offset APIs expose clock offsets, not an arbitrary Tesla voltage-curve editor; their architecture descriptions retain device-specific support checks. [GPC offset API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html), [clock-offset API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceQueries.html).
- **[documented]** Coolbits’ voltage-related option documents **overvoltage on certain GeForce GPUs**. It does not establish Tesla undervolting support. [NVIDIA Coolbits documentation](https://download.nvidia.com/XFree86/Linux-x86_64/580.65.06/README/xconfigoptions.html).
- **[community]** One Linux undervolting discussion explicitly reports the NVML-based approach working on a 4090 but not on a P100/T10. This is limited negative evidence, not proof that every possible approach fails. [Community discussion](https://www.reddit.com/r/linux_gaming/comments/1fm17ea/undervolting_nvidia_gpu_in_2024/).
- **[inference]** Reducing `-pl` or application clocks may select a lower-power operating point. That is useful power management, but it is **not evidence of lower voltage at the same frequency**.

I would not present “positive clock offset plus capped clocks” as a known-working P100 recipe.

## 4. Thermal slowdown and NVIDIA’s cooling requirements

**[documented]** NVML defines `SW Thermal Slowdown` as software clock reduction to keep GPU and memory temperatures within their respective maximum operating limits. The bit does **not identify which sensor caused the reduction**. [NVML clock-event reasons, `nvmlClocksEventReasonSwThermalSlowdown`](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html).

**[documented]** NVIDIA’s *Tesla P100 PCIe GPU Accelerator Product Brief*, **PB-08248-001_v01, October 2016**, supplies these values:

| Thermal parameter | Value |
|---|---:|
| GPU maximum operating temperature | **80°C** |
| GPU slowdown temperature, described as 50% clock slowdown | **82°C** |
| GPU shutdown temperature | **85°C** |
| Board operating environment | **0–45°C** |

Source: [Product Brief, printed p.4, Tables 4–5](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-product-literature/NV-tesla-p100-pcie-PB-08248-001-v01.pdf#page=7).

**[inference]** Kala’s slowdown around 79–80°C is consistent with GPU thermal control around the documented 80°C operating limit. Sampling and control behavior can explain a displayed temperature just below that limit. This does **not prove HBM2 overheating**.

**Unknown:** I found no public P100-specific HBM2 throttle threshold or documentation allowing the triggering sensor to be recovered from bit `0x20`. Memory-temperature `N/A` does not settle that question.

**[documented]** The same brief gives the following inlet/airflow reference points, applying to both memory variants:

| Heatsink inlet | Minimum airflow |
|---|---:|
| 30°C | 12 CFM |
| 35°C | 15 CFM |
| 40°C | 19 CFM |
| 45°C | 26 CFM |
| 50°C | 37 CFM |
| Powered card, including idle | At least 12 CFM |

These assume **fully ducted flow through the heatsink**, accounting for bypass. The heatsink accepts either longitudinal direction. Only the 35/40/45°C rows are marked NVIDIA-qualified; the table is a qualification reference, not an absolute specification. Its 50°C row does not override the stated operating environment. Source: [Product Brief, printed pp.5–6, “System Airflow Requirements,” Table 6 and notes](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/tesla-product-literature/NV-tesla-p100-pcie-PB-08248-001-v01.pdf#page=8).

**[inference]** Fan free-air ratings and fan count do not establish delivered heatsink airflow. A sealed duct, controlled bypass, and cool inlet air are the relevant engineering targets. I did not obtain a separate public P100 system thermal-design guide; the numbers above come from the product brief.

## 5. ECC on HBM2

**[documented] NVIDIA explicitly states that P100 HBM2 ECC has no memory-capacity overhead and no bandwidth penalty.** Therefore, disabling ECC is not a documented way to recover capacity or bandwidth. [NVIDIA, “Inside Pascal,” HBM2 discussion](https://developer.nvidia.com/blog/inside-pascal/).

**Unknown:** No verified P100 ECC-on/off power or llama.cpp throughput comparison was found. The documented capacity/bandwidth statement does not establish an exact zero-watt ECC cost.

**[inference]** Keep ECC enabled for these experiments. There is no sourced performance justification here for disabling it.

## 6. Vulkan features exposed on GP100

**The important correction is that “GP100 has no DP4A” does not imply “the Vulkan driver reports integer dot products as unaccelerated.”**

A published P100 startup log reports:

```text
fp16: 1 | bf16: 0 | warp size: 32 | int dot: 1 | matrix cores: none
```

**[community]** Source: [llama.cpp issue #18895](https://github.com/ggml-org/llama.cpp/issues/18895), build `9789e28459`. It is not an exact `580.159.03` device report.

| Feature | What can be established |
|---|---|
| `shaderFloat16` | **[community + documented]** Reported `fp16: 1`; that build explicitly checks `shaderFloat16`. [Corresponding backend source](https://github.com/ggml-org/llama.cpp/blob/9789e28459/ggml/src/ggml-vulkan/ggml-vulkan.cpp). |
| 16-bit storage | **[documented]** llama.cpp requires `storageBuffer16BitAccess`; its FP16 capability detection also checks the relevant extensions. Kala’s functioning backend is consistent with this. Other 16-bit-storage fields remain unverified. [5190c2e backend](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/ggml-vulkan.cpp). |
| Integer-dot extension and acceleration | **[documented + inference]** The reported `int dot: 1` is gated by `integerDotProduct4x8BitPackedSignedAccelerated` in that source. Thus at least one P100 NVIDIA-driver configuration reports that accelerated property as true. Exact R580.159.03 values, including unsigned/mixed variants, need measurement. [Corresponding source](https://github.com/ggml-org/llama.cpp/blob/9789e28459/ggml/src/ggml-vulkan/ggml-vulkan.cpp). |
| Subgroups | **[community]** Size 32 is reported. **Unknown:** exact GP100 `subgroupSizeControl`, minimum/maximum sizes, and required-size support on kala’s driver. |
| Cooperative matrices | **[community]** The report says `matrix cores: none`. No verified GP100 cooperative-matrix execution path was found. |

**[documented]** GP100 provides packed FP16 arithmetic at twice its FP32 rate; the integer DP4A/DP2A instructions belong to other Pascal variants, not GP100. [NVIDIA, “Mixed-Precision Programming with CUDA 8”](https://developer.nvidia.com/blog/mixed-precision-programming-cuda-8/).

**[documented]** llama.cpp Vulkan has FP16 shader variants, including scalar flash attention. However, its ordinary matrix-vector shader generation also uses FP32 arithmetic; FP16 storage or `fp16: 1` does not mean every operation runs at packed-half throughput. [Shader generator at 5190c2e](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/vulkan-shaders/vulkan-shaders-gen.cpp).

**[inference]** Vulkan can use GP100 FP16, but a blanket “2× generation speed” claim is unsupported. Establishing actual packed instruction use in a particular kernel would require shader/compiler inspection or profiling.

For a read-only check, inspect the P100 device section of `vulkaninfo`, including:

```text
shaderFloat16
storageBuffer16BitAccess
uniformAndStorageBuffer16BitAccess
shaderIntegerDotProduct
integerDotProduct4x8BitPackedSignedAccelerated
integerDotProduct4x8BitPackedUnsignedAccelerated
integerDotProduct4x8BitPackedMixedSignednessAccelerated
subgroupSizeControl
minSubgroupSize
maxSubgroupSize
cooperativeMatrix
```

The ICD’s API-version string is not a substitute for those device properties. Their meanings are defined in [Khronos Vulkan feature/property documentation](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceShaderIntegerDotProductProperties.html).

## 7. llama.cpp Vulkan tuning and build choice

**[documented]** `5190c2e` is an upstream commit from **26 May 2026**. [Commit](https://github.com/ggml-org/llama.cpp/commit/5190c2e).

### Environment variables worth distinguishing

These exist in the inspected [5190c2e Vulkan backend](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/ggml-vulkan.cpp):

| Setting | Assessment |
|---|---|
| `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1` | **[documented]** Disables integer-dot selection. **[inference]** High-value A/B test on GP100. |
| `GGML_VK_DISABLE_MMVQ=1` | **[documented]** Disables the quantized matrix-vector path. Test independently, then together with the preceding setting. |
| `GGML_VK_DISABLE_F16=1` | **[documented]** Diagnostic FP16-off comparison. No evidence supporting it as a normal P100 optimization. |
| `GGML_VK_DISABLE_ASYNC=1`, `GGML_VK_DISABLE_FUSION=1`, `GGML_VK_DISABLE_GRAPH_OPTIMIZE=1` | **[documented]** Diagnostic switches. No verified general GP100 improvement. |
| `GGML_VK_DISABLE_COOPMAT`, `GGML_VK_DISABLE_COOPMAT2` | **[inference]** No benefit when the device already has no applicable cooperative-matrix path. |
| `GGML_VK_VISIBLE_DEVICES` | **[documented]** Useful for selecting GPUs after installing the second card. |

**[documented]** Several switches are tested by environment-variable presence. **Unset them to revert; `=0` can still activate the switch.** Same source.

There is unusually relevant community evidence:

| Two-P100 Vulkan experiment | Prompt tok/s | Generation tok/s |
|---|---:|---:|
| Devstral 24B Q8_0, defaults | 11.02 | 12.42 |
| Integer dot disabled | 255.98 | 10.18 |
| MMVQ disabled | 11.06 | 10.07 |
| Both disabled | 255.83 | 10.18 |

**[community]** Ollama 0.34.0, two 16 GB P100s, 2,048-token configured context, two uncached roughly 1,190-token prompts and 128-token generations. [Report and adjacent raw results](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-17/devstral-p100-tuning/REPORT.md).

**[community]** The same tester’s 27B Q4_K_M experiment improved from **11.71/11.09** prompt/generation tok/s to **139.28/14.79** with both flags. [Separate report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-15/qwen3.8-p100-tuning/REPORT.md).

**[inference]** These justify testing, not copying the reported speedups. Kala already achieves much better prompt throughput than those pathological defaults, and the Q8_0 example demonstrates a generation-speed tradeoff.

### Flash attention and batches

- **[documented] Scalar flash attention exists.** `FA_SCALAR` and `flash_attn.comp` provide a path without cooperative matrices. [Backend selection](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/ggml-vulkan.cpp), [scalar shader](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/vulkan-shaders/flash_attn.comp).
- **[documented]** The upstream server default at this commit is **AUTO**. Missing `-fa` therefore does not establish that FA is off; inspect the actual initialization log. Test explicit `-fa on` and `-fa off`. [Common defaults](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/common.h), [argument definitions](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp).
- **[documented]** `-b` is the logical batch limit; `-ub` controls physical microbatching. **[inference]** Test `-ub 128,256,512` while keeping `-b 1024`, primarily for prompt processing. No universal improvement to single-slot generation follows from a smaller batch. [Argument definitions](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp).

### Quantization

**Unknown:** No controlled GP100 Vulkan comparison of all five requested formats on the same 14B model was found.

| Format | Test hypothesis—not a measured ranking |
|---|---|
| **Q4_0** | **[inference]** Worth comparing because of its simpler quantization/dequantization structure. Check output quality as well as speed. |
| **Q4_K_S** | Existing baseline; retain it until another format wins under matched conditions. |
| **Q4_K_M** | **[documented]** Uses higher precision for selected tensors, including Q6_K in relevant cases. **[inference]** Do not assume it is a speed upgrade over S. |
| **IQ4_XS** | **[inference]** Potential memory-traffic advantage competes with decoding and kernel-selection costs; benchmark on each build. |
| **Q8_0** | **[inference]** Simpler decoding does not guarantee faster generation when more weight bytes must be read. Check actual model-plus-KV-cache fit before comparing. |

Sources for representation and mixed-tensor selection: [quantization implementation](https://github.com/ggml-org/llama.cpp/blob/5190c2e/src/llama-quant.cpp), [Vulkan shader generation](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/vulkan-shaders/vulkan-shaders-gen.cpp).

### Changes after mid-2026

- **[documented] [PR #28415](https://github.com/ggml-org/llama.cpp/pull/28415)**, merged **23 September 2026**, adds dedicated IQ4_XS MMQ/MMV kernels. The added integer-dot path means applicability depends on kernel selection; **no GP100 speedup was established**.
- **[documented] [PR #29882](https://github.com/ggml-org/llama.cpp/pull/29882)**, merged **26 October 2026**, replaces RMS-normalization workgroup reduction with subgroup reductions. Published tests cover other GPUs, not P100.
- **[inference]** A newer optimized Vulkan build is worth comparing. Neither PR supports a numerical P100 improvement prediction.

## 8. Measurements by others

These are useful reference points, **not matched backend comparisons**.

| Report | Model/backend | Reported result | Limitations |
|---|---|---|---|
| **[community] [LocalScore P100-PCIE-16GB](https://www.localscore.ai/accelerator/3387)** | Qwen2.5-14B-Instruct Q4_K_M | **181 prompt, 19.2 generation tok/s** | Summary lacks enough driver/backend/context detail to reproduce or compare directly with kala. |
| **[community] [“The P100 isn’t dead yet”](https://www.reddit.com/r/LocalLLaMA/comments/1krrp2f/the_p100_isnt_dead_yet_qwen3_benchmarks/)** | Qwen3-14B GPTQ Int4; author identifies vLLM | Approximately **200 prompt, 45 generation tok/s**, at **150 W** power limit | Different model/quantization; insufficient version, context and configuration detail. |
| **[community] [Same thread](https://www.reddit.com/r/LocalLLaMA/comments/1krrp2f/the_p100_isnt_dead_yet_qwen3_benchmarks/)** | Qwen3-14B Q6_K, llama.cpp CUDA | **228.02 prompt, 16.24 generation tok/s** | Q6 rather than Q4; cannot establish CUDA superiority. |
| **[community] [llama.cpp Vulkan discussion #10879](https://github.com/ggml-org/llama.cpp/discussions/10879)** | P100, Llama 7B Q4_0, Vulkan | Generation **63.16** FA-off versus **66.48** FA-on tok/s | Smaller model and older build; evidence that scalar FA can help, not a 14B forecast. |

FP16 implementation evidence:

- **[documented] llama.cpp CUDA** explicitly recognizes fast FP16 on `sm_60`, excluding `sm_61` from that fast-path classification. [CUDA `common.cuh`](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-cuda/common.cuh).
- **[documented] ExLlamaV2** contains quantized GEMM kernels using `half2` and `__hfma2`. That establishes packed-half arithmetic in the implementation, not a verified 14B P100 result. [Pinned quantized GEMM source](https://github.com/turboderp-org/exllamav2/blob/7dc12af3a81f34ac3f27cd7602ed539b638933ca/exllamav2/exllamav2_ext/cuda/q_gemm_kernel.cuh).
- **Unknown:** I did not verify a comparable P100 14B Q4 benchmark for ExLlamaV2 or MLC, or the exact FP16 kernel path behind the quoted vLLM result.

**[inference]** The available evidence does not justify replacing kala’s Vulkan baseline with CUDA.

## 9. Idle power and P-states

- **[community]** A P100 owner reports idle draw just below **30 W**, including with empty VRAM, and contrasts it with P40 low-power-state behavior. [P100/P40 idle-power investigation](https://jankyai.droidgram.com/reducing-idle-power-consumption-for-nvidia-p100-and-p40-gpus/).
- **[community]** The Qwen3 P100 benchmark author reports approximately **26 W idle**. [Report](https://www.reddit.com/r/LocalLLaMA/comments/1krrp2f/the_p100_isnt_dead_yet_qwen3_benchmarks/).
- **Unknown:** No NVIDIA documentation or sufficiently reproducible measurement was found establishing a GP100 deep P-state that gives substantially lower idle power with an open inference context. Nor was a reliable below-25-W result established merely by closing all contexts.
- **[documented]** NVIDIA’s Linux runtime D3 power-management mechanism requires **Turing or newer**, so `NVreg_DynamicPowerManagement` is not a supported P100 solution. [R580 Runtime D3 documentation](https://download.nvidia.com/XFree86/Linux-x86_64/580.159.03/README/dynamicpowermanagement.html).

**[inference]** Kala’s P0 label alone is not evidence of full-speed operation: its measured idle clock is 405 MHz. Forcing the lowest application clock of 544 MHz is not an obvious idle improvement over an already lower automatic clock.

**[inference]** Closing llama-server and testing `-pm 0` is a legitimate measurement, but no substantial saving should be promised.

## 10. Other plausible considerations

- **[documented/inference]** GSP firmware tuning is not a useful GP100 path. NVIDIA describes GSP use for Turing and later; `NVreg_EnableGpuFirmware=0` is not a demonstrated P100 optimization. [R580 GSP documentation](https://download.nvidia.com/XFree86/Linux-x86_64/580.159.03/README/gsp.html).
- **[documented]** R580.105.08 introduced `CUDA_DISABLE_PERF_BOOST=1` to suppress CUDA’s automatic higher-power-state boost. **Unknown:** effectiveness on GP100. It is documented for CUDA, not a Vulkan idle-power setting. [NVIDIA release highlights, 580.105.08 entry](https://www.nvidia.co.uk/Download/processFind.aspx?ctk=0&lang=en-uk&lid=2&osid=12&pfid=845&psid=101&whql=).
- **[inference]** Keep a single-GPU baseline after adding the second P100. A model already fitting the first card does not automatically benefit from splitting across the chipset x4 connection. Explicit device selection makes that comparison possible. [llama.cpp device/split arguments](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp).
- **Unknown:** No verified firmware update for the stated board/VBIOS was found that improves inference performance or permits supported undervolting.
- **[inference]** Evaluate **energy per completed request**, not watts alone. For a steady generation interval, approximate GPU joules/token as mean GPU watts divided by tokens/second. Include prompt processing for actual workloads; GPU telemetry excludes external fan and other system consumption.

## Top changes worth testing on kala

First establish a sustained baseline with the improved cooling. Use repeated requests long enough to exceed the previously observed thermal-collapse interval. Record prompt and generation speeds separately, temperatures, power and clock-event reasons.

A read-only monitor, requiring no root:

```bash
nvidia-smi -i 0 -q -d PERFORMANCE,TEMPERATURE,POWER,CLOCK -l 2
```

Confirm GPU index 0 identifies the intended P100. Syntax: [nvidia-smi documentation](https://docs.nvidia.com/deploy/nvidia-smi/index.html).

For the launch examples below, this Bash setup represents the supplied workload; replace the two paths:

```bash
SERVER='/path/to/llama-server'
MODEL='/path/to/Qwen2.5-14B-Instruct-Q4_K_S.gguf'
base=(-m "$MODEL" -ngl 99 -c 8192 -np 1 -t 8 -b 1024 -ub 512)
```

| Rank | Exact command or setting | Root? | Expected effect and evidence | Revert |
|---|---|---|---|---|
| **1** | `env GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1 "$SERVER" "${base[@]}"` | No | **[community/inference]** May improve prompt processing; generation can regress. Strongest directly relevant P100 software experiment. [P100 report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-17/devstral-p100-tuning/REPORT.md). | Restart without the variable; remove any globally exported copy. |
| **2** | `env GGML_VK_DISABLE_MMVQ=1 "$SERVER" "${base[@]}"`; subsequently test both variables together | No | **[community/inference]** Model-dependent generation improvement or regression. Test independently to identify the cause. Same report and [Q4 report](https://github.com/TheTriumphantFox/p100-model-tests/blob/main/results/2026-09-15/qwen3.8-p100-tuning/REPORT.md). | Restart with both variables unset. |
| **3** | Append `-fa on`; compare with `-fa off` | No | **[documented/inference]** Scalar FA is available; potential attention/memory benefit. May already be enabled automatically. [FA source](https://github.com/ggml-org/llama.cpp/blob/5190c2e/ggml/src/ggml-vulkan/ggml-vulkan.cpp). | Remove explicit flag or use `-fa auto`. |
| **4** | `sudo nvidia-smi -i 0 -pm 1`, then separate runs with `sudo nvidia-smi -i 0 -pl 175`, `-pl 150`, and `-pl 125` | Yes | **[documented/inference]** Lower heat and potentially better joules/token when the cap binds. Kala’s old throttled 56–100 W readings are already below all these caps, so they are not an immediate cure for that state. [Power API](https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlDeviceCommands.html). | `sudo nvidia-smi -i 0 -pl 250`; restore `-pm 0` if desired. |
| **5** | Change `-ub 512` to `-ub 256`, then `-ub 128`, retaining `-b 1024` | No | **[inference]** Potential prompt-processing improvement and smaller temporary allocations; no guaranteed generation gain. [Batch definitions](https://github.com/ggml-org/llama.cpp/blob/5190c2e/common/arg.cpp). | Restore `-b 1024 -ub 512`. |
| **6** | Test a newer upstream Vulkan build containing commit `70c5f2632466b583075862bb02151d641550870c`; configure `-DGGML_VULKAN=ON -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release` | No, assuming dependencies installed | **[documented/inference]** Includes the later RMS-normalization work; P100 improvement unknown. [PR #29882](https://github.com/ggml-org/llama.cpp/pull/29882). | Run the retained `5190c2e` binary. |
| **7** | Driver setting: **R580.196.07, proprietary kernel modules**, with matching user-space packages | Yes; reboot | **[documented/inference]** Includes the later Vulkan semaphore fix; no promised P100 speedup. Distribution package availability was not verified. [R580 release history](https://www.nvidia.co.uk/Download/processFind.aspx?ctk=0&lang=en-uk&lid=2&osid=12&pfid=845&psid=101&whql=). | Restore the matched 580.159.03 package set and reboot. |
| **8** | After confirming thermal headroom: `sudo nvidia-smi -i 0 -ac 715,1328` | Yes | **[inference]** Tests additional core throughput against the measured 1189 MHz setting; can increase heat or worsen sustained speed. Application clocks remain subordinate to thermal/power control. [Application-clock API](https://docs.nvidia.com/deploy/archive/R535/nvml-api/group__nvmlDeviceCommands.html). | `sudo nvidia-smi -i 0 -ac 715,1189`, or `-rac` for defaults. |
| **9** | Run the same model in **Q4_0**, keeping other settings identical; test **IQ4_XS** separately on the newer build | No | **[inference]** Possible shader/traffic advantage, with quality and build-dependent tradeoffs. No verified GP100 ordering. [Quantization source](https://github.com/ggml-org/llama.cpp/blob/5190c2e/src/llama-quant.cpp), [IQ4_XS PR](https://github.com/ggml-org/llama.cpp/pull/28415). | Restore the original Q4_K_S model path. |

For each comparison, keep the model, prompt length, cache reuse, context depth and cooling conditions controlled. Retain a change only if it improves the relevant sustained metric: generation speed, full-request latency, or joules per request. **[inference]**