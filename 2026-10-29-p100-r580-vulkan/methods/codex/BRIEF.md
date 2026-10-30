# Research brief: Tesla P100 on NVIDIA R580 + Vulkan: faster, more efficient, cooler?

You are one member of a research group. Claude (Anthropic) is coordinating and will verify everything you say,
so precision and sources matter more than coverage. Read-only: do not modify anything.

## The machine ("kala"), verified today, 2026-10-29

- GPU: **Tesla P100-PCIE-16GB** (GP100, sm_60, HBM2 16 GB, PCIe 3.0 x16 link at Gen3 x16), VBIOS 86.00.4D.00.01,
  board 900-2H400-0100-030. Passively cooled card; owner added a 3-fan shroud (and has bought 120 mm "blower" fan kits).
- Driver: **NVIDIA 580.159.03, proprietary kernel module** (not the open modules), Pop!_OS 24.04, kernel 6.18.7.
  CUDA (driver API) 13.0. Vulkan ICD api_version 1.4.312. Persistence mode is Disabled. ECC is Enabled.
- nvidia-smi -q today: GPU Shutdown Temp 85 C, GPU Slowdown Temp 82 C, GPU Max Operating Temp N/A,
  Memory Current Temp N/A. Power limit default 250 W, min 125 W, max 250 W. Application clocks 1189 MHz graphics /
  715 MHz memory (default 1189); max clocks 1328 MHz; supported graphics clocks 544–1328 MHz in ~12.7 MHz steps,
  memory fixed at 715 MHz. Auto Boost N/A. Performance state P0 even at idle (405 MHz idle clock).
- Idle today: 44 C, 28 W (on Oct 20 it idled at 71–78 C at 37–50 W, before cooling changes).
- Oct 20 and Oct 24 measurements (older cooling): under sustained inference the SM clock fell from 1189 MHz to
  405–630 MHz within ~20 s while the temperature held ~79 C at only 56–100 W. Clock event reason bit 0x20
  (SW Thermal Slowdown). Back-to-back 400-token answers: 28 → 27 → 18 → 8 → 8 tok/s.
- Workload: **llama.cpp Vulkan backend** (LM Studio's bundled build 2.17.0, `llama-server --version` reports commit
  5190c2e), serving Qwen2.5-14B-Instruct **Q4_K_S** (8.57 GB), full offload, 8k context, 1 slot,
  `-t 8 -b 1024 -ub 512`, no explicit `-fa` flag. Cool-GPU speed ~29 tok/s generation, ~200 tok/s prompt.
- CUDA was tried on Oct 20: llama.cpp official b11747 CUDA 12.8 build ran on sm_60 but generated *slower*
  (8–12 vs 12–24 tok/s, a noisy comparison). LM Studio's CUDA 12 build had no sm_60 kernels.
- The owner bought a **second P100 (PCIe 12 GB)**, not yet installed. It will sit in a chipset PCIe 3.0 x4 slot.
  PSU is a 750 W Seasonic; CPU is an i7-11700K. Board: ASUS PRIME B560M-A.

## Decisions already made (do not re-argue)
- Stay on the R580 branch: it is the last branch that supports Pascal. Do not suggest 590+.
- Vulkan is the current backend; CUDA alternatives are in scope only if you have evidence they beat Vulkan on sm_60.
- No hardware purchase recommendations beyond cooling accessories (the GPU choice is settled).

## The question
What, if anything, can be done **in software / driver / firmware settings** (R580 driver knobs, nvidia-smi / NVML,
kernel module parameters, Vulkan driver behaviour, llama.cpp Vulkan settings and build choice, model quantization
choice) to make this P100 (a) faster, (b) more energy-efficient, or (c) run cooler? Also list the cooling
practices that NVIDIA itself documents for the passive P100 PCIe card (airflow, inlet temperature), because the
software knobs interact with them.

Please answer each of these specifically:
1. **R580 + Pascal status**: support timeline for Pascal on R580 (end-of-life / legacy / LTSB dates), and any
   documented R580.x changes, regressions or bugs affecting Pascal compute or Vulkan performance.
2. **Clock and power knobs that actually work on a Tesla P100 under R580**: `nvidia-smi -ac` (application clocks),
   `-pl` (power limit), `-pm` (persistence), `-e` (ECC), `-lgc`/`-rgc` (lock clocks: which architectures?),
   `-acp` (application clock permission), NVML `nvmlDeviceSetGpcClkVfOffset` / `nvmlDeviceSetClockOffsets`
   (clock offsets: supported on Pascal datacenter parts?), nvidia-settings Coolbits (needs X / display?).
   For each: is it supported on GP100, does it need root, does it persist across reboot.
3. **Undervolting**: is there any supported or known-working way to reduce the voltage at a given clock on a
   Pascal Tesla under Linux (e.g. clock offset + capped clocks)? Evidence it works on GP100 specifically?
4. **Thermal slowdown behaviour**: what exactly triggers "SW Thermal Slowdown" on P100 (GPU temp vs memory/HBM2
   temp, thresholds), and NVIDIA's documented airflow/inlet requirements for the P100 PCIe (product brief /
   thermal design guide numbers, with the document name).
5. **ECC on HBM2**: does disabling ECC on P100 HBM2 change usable memory or bandwidth? Documented numbers?
6. **Vulkan on Pascal (NVIDIA driver)**: which features does the NVIDIA Vulkan driver expose on GP100 that
   matter to llama.cpp: `shaderFloat16`, 16-bit storage, `VK_KHR_shader_integer_dot_product` (and whether
   4x8-bit dot is reported as *accelerated* on GP100, which lacks DP4A), subgroup size control, cooperative
   matrix (expected: none). Does GP100's 2x FP16 rate get used through Vulkan?
7. **llama.cpp Vulkan backend tuning for a device with fp16 but no int-dot and no matrix cores**:
   relevant environment variables (`GGML_VK_*`) and flags (`-fa`, `-ub`, `-b`), whether flash attention has a
   scalar path, which quant types run fastest on such devices (Q4_0 vs Q4_K_S vs Q4_K_M vs IQ4_XS vs Q8_0),
   and any upstream performance changes since mid-2026 that would make a newer build faster than commit 5190c2e
   on Pascal. Cite llama.cpp source files, PRs or issues.
8. **Measured P100 numbers by others**: llama.cpp (Vulkan or CUDA) or other engines (exllamav2, vLLM, MLC)
   on a P100 for a ~14B Q4 model, with links. Note which engines exploit P100 FP16.
9. **Idle power**: can a Tesla P100 idle lower than ~25–30 W in P0 while a Vulkan/CUDA context is open, or only
   with no context? Any documented deeper P-states on P100?
10. Anything else in R580 / Vulkan land that we did not ask about but that would plausibly help.

## Sourcing rule
Every external number or claim needs a source (URL, plus document name/section when possible). Prefer primary
sources: NVIDIA docs (nvidia-smi man page, NVML API reference, driver release notes, P100 product brief / data
sheet), Khronos/gpuinfo.org device reports, llama.cpp repo files/PRs/issues. Mark community reports (Reddit,
forums) as such. If you cannot find a source, say "unsourced" or "unknown"; do not guess. Flag anything you
believe but could not verify. Distinguish clearly between "documented", "community-reported", and "inference".

## Output format
Markdown. One section per question (1–10). For each claim: the claim, the source URL, and a confidence tag
(documented / community / inference). End with a ranked list: "Top changes worth testing on kala", each with
the exact command or setting, whether it needs root, the expected effect, and how to revert it.
