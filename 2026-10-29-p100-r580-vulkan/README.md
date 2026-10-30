# Tuning a throttling Tesla P100 from the driver up

**Date:** October 29, 2026 · **Status:** ongoing (cooling fix next) · **Write-up:**
https://hewcarroll.com/experiments/p100-r580-vulkan/

My server, kala, runs a 14-billion-parameter model on a passively cooled Tesla P100. It generates 27 tokens a second
for about a minute, then throttles to 7. I went through every software layer I could reach, from the NVIDIA driver
up to the inference engine, to find out what software can and can't do about it.

## Results in short

- Under sustained load the card reaches 79 °C in about 70 seconds and the driver walks the core clock down to its
  405 MHz floor. Generation falls from 26.9 to 6.8 tok/s, prompt processing from 250 to 94 tok/s. The heatsink as
  cooled at the time sheds about 69 W at that temperature; the card draws about 185 W at full speed.
- Throttled, the card uses 40–50 % more energy per generated token (9.6–10.1 J against 6.7–7.0 J).
- NVIDIA driver R580 exposes no clock offsets on this card (an allowed range of 0 to 0 MHz), no clock locking, no
  target temperature and no lower power states. The power limit and application clocks work, but even their lowest
  settings sit above the throttled operating point, so they can't lift the ceiling.
- R580's Vulkan driver reports 4×8-bit integer dot products as *accelerated* on the P100, which has no DP4A
  instruction. Current llama.cpp builds trust that flag and take an int8 path that made prompts 10× slower here
  (185 → 18 tok/s) and generation 30 % slower. `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1` avoids it. LM Studio's Linux
  Vulkan runtime 2.17.0 has none of those kernels compiled in, so it is unaffected.
- Engine settings that helped: n-gram speculative decoding (`--spec-type ngram-simple
  --spec-ngram-simple-size-n 4 --spec-ngram-simple-size-m 16`) raised generation on a quote-heavy extraction job from
  27.5 to 34.8 tok/s with byte-identical output, and cost 2 % on free text. Four parallel slots gave 1.65× the
  combined throughput at the same power. The same speculation setting on upstream b11988 *halved* extraction speed.

## What is new here, as far as I could find

- The root cause of the slow Vulkan prompts that Pascal owners have reported: the driver's "accelerated" flag on a GPU
  without DP4A, and llama.cpp's choice of the int8 path because of it.
- That LM Studio's 2.17.0 Linux Vulkan runtime ships without int8 kernels (0 against 476 in upstream b11988).
- The R580 clock-offset range on a P100 (0 to 0), measured through NVML.
- N-gram speculation and parallel-slot results on a P100, and the b11988 speculation regression.
- Energy per token cool against throttled on a P100.

The prompt-speed collapse itself confirms an earlier report from TheTriumphantFox on two P100s under Ollama:
https://github.com/TheTriumphantFox/p100-model-tests

## Setup

| | |
|---|---|
| GPU | NVIDIA Tesla P100 PCIe 16 GB (GP100, sm_60), VBIOS 86.00.4D.00.01, PCIe 3.0 x16 |
| Cooling at test time | stock passive heatsink with a 3-fan shroud (the "before" condition) |
| Host | Intel i7-11700K, 31 GB RAM, ASUS PRIME B560M-A |
| OS | Pop!_OS 24.04, kernel 6.18.7 |
| Driver | NVIDIA 580.159.03, proprietary kernel module; Vulkan ICD 1.4.312 |
| Engine A | LM Studio llama.cpp Vulkan runtime 2.17.0 (`llama-server --version`: 5190c2e) |
| Engine B | llama.cpp b11988 (commit abb76ab38), official `llama-b11988-bin-ubuntu-vulkan-x64.tar.gz`, sha256 `28aecdd624c768e765402a4f75eac0ffb128afbe917883b803dd8ad237361848` |
| Model | Qwen2.5-14B-Instruct Q4_K_S (bartowski GGUF, 8.57 GB); stand-in tests used Qwen2.5-VL-3B-Instruct Q4_K_M as a text model |

## What's in this folder

| Path | Contents |
|---|---|
| `data/probe/` | `nvidia-smi -q`, the NVML probe output, `vulkaninfo`, the server unit and driver/build details (device serials and UUIDs removed) |
| `data/sustained-14b/` | 2 Hz GPU telemetry and per-request timings for the ten-request sustained run, plus the analysis |
| `data/settings-3b/`, `data/engine-3b/` | 3B stand-in runs: flash attention, batch size, FP16, speculation modes, parallel slots |
| `data/engine-14b/` | 14B runs on both engines with telemetry, results, a summary and every model reply |
| `logs/` | the raw `llama-server` log of every test server, the run logs, and the production server's journal for the sustained run |
| `screenshots/` | PNG captures of terminal output; `screenshots/source/` holds the exact text each one was rendered from |
| `scripts/` | everything used to run and analyse the tests |
| `methods/` | the research briefs and reports from Codex, and the local models' quote-checked extractions |

## How to replicate

The scripts were written for one machine; set the paths at the top of each before running.

1. **Probe the driver (read-only).**

   ```bash
   nvidia-smi -q
   python3 -I scripts/nvml_probe.py
   vulkaninfo | grep -E 'deviceName|driverInfo|shaderFloat16 |integerDotProduct4x8BitPacked'
   ```

2. **Measure sustained throttling.** Serve the model the way kala does, then run ten requests back to back while
   sampling the GPU twice a second:

   ```bash
   llama-server -m Qwen2.5-14B-Instruct-Q4_K_S.gguf --device Vulkan0 -ngl 999 --jinja -c 8192 --parallel 1 \
     -t 8 -b 1024 -ub 512 --port 1234
   bash scripts/run_live14b.sh mytag 10 512
   python3 -I scripts/analyze.py tele-mytag.csv load-mytag.jsonl
   python3 -I scripts/thermal_fit.py tele-mytag.csv
   ```

3. **Check for the int8 trap.** Run any llama.cpp Vulkan build twice on the same prompt, once with
   `GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1`, and compare the `prompt eval time` lines in the server log.
   `strings libggml-vulkan.so | grep -cE '^(matmul|mul_mat_vec)_[a-z0-9_]+_q8_1'` shows whether a build has the int8
   kernels at all.

4. **Compare engine settings.** `scripts/run_flags.sh` (flash attention, batch, FP16) and `scripts/run_layer2.sh`
   (speculation modes, parallel slots) use a small stand-in model on a second port. `scripts/run_14b_window.sh lms|up`
   runs the 14B tests; it stops and restarts a systemd user service called `llama-server`, so adapt it first. Every
   configuration waits for the GPU to cool below 55 °C and runs a burst short enough to finish before the throttle.

5. **Re-render the screenshots** from their source text: `node ../tools/render-terminal.mjs OUT.png "Title"
   screenshots/source/NAME.txt`.

## Not yet tested: settings that need root

The power limit and application clocks can only be changed as root. They reset at reboot. Before each run, wait for
the card to idle at 44–47 °C, then send one request from cool; finish with one 10-minute sustained run at 125 W.

```bash
sudo nvidia-smi -i 0 -pm 1              # keep settings while testing
sudo nvidia-smi -i 0 -pl 175            # run 1: power cap
sudo nvidia-smi -i 0 -pl 125            # run 2: lowest cap
sudo nvidia-smi -i 0 -pl 250            # back to the default cap
sudo nvidia-smi -i 0 -ac 715,1037       # run 3: clock cap (on Pascal this also turns boost off)
sudo nvidia-smi -i 0 -rac               # undo the clock cap; -ac 715,1189 would leave boost off
sudo nvidia-smi -i 0 -pm 0
```

Expected: no change to the throttled steady state, possibly less energy per token in bursts. The deciding numbers are
energy per token and sustained tokens per second.

## Limits

One card, one model, one cooling setup. Settings were compared in cool-started bursts, which compares settings, not
sustained speed. Some settings were screened on the 3B model first. Community numbers cited in the write-up were not
rerun here. Since driver 580.65.06, nvidia-smi reports clocks from before thermal slowdowns are applied, so throttling
was read from the clock-event reason bits and the measured token rates rather than the clock column alone.

## How it was done

I picked the question, approved every change to the production server and decided what got published. Claude Code
(Anthropic's Claude Opus 5.5) ran the probes and tests, wrote the scripts and did the analysis. Codex (OpenAI's
gpt-6-astra) wrote sourced research briefs and attacked the conclusions in three rounds; it caught an arithmetic error
in the first energy figures, which was fixed. Local models on my own machines (Qwen2.5-14B on this P100, Gemma 4 12B
and Qwen3.6-35B-A3B) pulled facts out of the sources, and every quote they returned was checked word for word against
the source text. Their raw output is in `methods/`.

## Sources

- NVIDIA, *Tesla P100 PCIe GPU Accelerator Product Brief* (PB-08248-001): thermal limits and airflow table.
  https://images.nvidia.com/content/tesla/pdf/NV-tesla-p100-pcie-PB-08248-001-v01.pdf
- NVIDIA, *Mixed-Precision Programming with CUDA 8* (DP4A on GP102/GP104/GP106; FP16 at 2× on P100).
  https://developer.nvidia.com/blog/mixed-precision-programming-cuda-8/
- NVIDIA data center driver 580.65.06 release notes (clock reporting change).
  https://docs.nvidia.com/datacenter/tesla/pdf/NVIDIA_Data_Center_GPU_Driver_Release_Notes_580_v1.0.pdf
- TheTriumphantFox, P100 model tests (Vulkan flags on two P100s).
  https://github.com/TheTriumphantFox/p100-model-tests
