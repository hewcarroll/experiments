# Two requests at a time on an Intel Arc B580

**Date:** October 30, 2026 · **Status:** done · **Write-up:** https://hewcarroll.com/experiments/darwin-two-slots/

My desktop, darwin, runs a 12-billion-parameter model on an Intel Arc B580 that also drives my screens. The model
server has always had two slots but my batch scripts only ever sent it one request at a time so I wrote a small tool
that keeps both slots busy and measured what that's worth. Checking the card's memory along the way I found that a
program starting up on it is told 90% of the card is free, even while my model server holds three quarters of it.

## Results in short

- Sent two at a time the same eight jobs finished in 101.5 seconds instead of 154.5. That's 1.52 times the
  throughput for 4 W more at the GPU package, which works out to 32% less energy per generated token (2.26 J against
  3.32 J).
- The clock's median was 2850 MHz in both modes and the package peaked at 63 to 64 °C either way. Neither mode needed
  more VRAM, since the server reserves each slot's cache when it starts.
- Sharing the card made each job 19 to 31% slower on its own, a fine trade for a batch but not for one person
  waiting on one answer.
- Intel's xe kernel driver reports zero VRAM in use to any program without the CAP_PERFMON or CAP_SYS_ADMIN
  privilege, as its header documents. For a program that hasn't allocated anything yet Mesa then budgets 90% of the
  card, whatever other programs hold, and llama.cpp reports that budget as free memory: 10,994 MiB of 12,216 MiB
  while my model server held 9,145 MiB. With its default `--fit on` a second llama.cpp planned to load about 9,968
  MiB onto a card with at most 3,071 MiB left.

## What is new here, as far as I could find

- Throughput and energy per token for llama.cpp's parallel slots on a B580. The B580 results I found were all single
  requests.
- What the xe driver's documented privilege rule does further up, traced through the kernel header, Mesa and
  llama.cpp: Mesa's budget ignores other programs and llama.cpp's automatic fit plans from it. The rule itself is in
  the kernel header. The closest Mesa issues I found
  ([#5173](https://gitlab.freedesktop.org/mesa/mesa/-/issues/5173),
  [#6937](https://gitlab.freedesktop.org/mesa/mesa/-/issues/6937)) are older budget bugs with other causes, and I
  found nothing on the llama.cpp tracker.

## Setup

| | |
|---|---|
| GPU | Intel Arc B580 12 GB (Battlemage, BMG G21) on the xe kernel driver, also running the desktop |
| Driver | Mesa 26.1.6 ANV (`26.1.6-1pop0~1787580452~24.04~a5619ea`), Vulkan 1.4.354 |
| Kernel | 6.16.3, Pop!_OS 24.04 |
| Engine | llama.cpp b11747, official Vulkan build |
| Model | Gemma 4 12B, Google's QAT Q4_0 GGUF (`gemma-4-12b-it-qat-q4_0.gguf`), text only, reasoning off |
| Host | AMD Ryzen 5 5500, 48 GB RAM |

The server runs as a systemd user service with this command:

```bash
llama-server -m gemma-4-12b-it-qat-q4_0.gguf -ngl 99 -fa off -c 24576 -np 2 -ub 512 -b 2048 \
  -ctxcp 0 -cram 0 --reasoning off --host 127.0.0.1 --port 1235
```

`-c 24576 -np 2` gives two slots of 12,288 tokens each. The server log confirms `n_slots = 2, n_ctx_slot = 12288,
kv_unified = 'false'`. Flash attention is off because on this card it made Gemma 4's prompt processing about six times
slower in an earlier test.

## What's in this folder

| Path | Contents |
|---|---|
| `inputs/` | the eight text chunks the jobs read, cut from my P100 write-up (CC BY 4.0) with the line wrapping removed |
| `scripts/` | `llm-batch` and `llm-task` as they ran (my other machines' addresses replaced with placeholders), `jobs.json`, `measure_slots.py` and `summarize.py` |
| `data/run-2026-10-30b/` | the measured run: `summary.json`, `telemetry.csv`, and for each of the six runs its jobs, every answer, the `llm-batch` output and the slice of the server log it produced |
| `data/run-2026-10-30/` | a first full run with two workload bugs, quotes broken by hard-wrapped input and answers cut off at 800 tokens. Kept for the record and not used for any number here |
| `screenshots/` | PNG captures of terminal output. `screenshots/source/` holds the exact text each one was rendered from |

## The test

Each job asks the model to pull facts out of one section of my P100 write-up and return them as JSON with a quote
from the source for every fact. Then `llm-task --quotes-from` checks each quote word for word against the text the
model was given. Temperature was 0 and an answer could run to 1,600 tokens.

`measure_slots.py` runs the batch six times in the order one, two, two, one, one, two so that neither mode always
went first or last. Every run's prompts carry their own marker (`Run r1-j2.` and so on) so the server can't reuse a
cached prompt from an earlier run, with 20 seconds of rest between runs. Twice a second a sampler reads the GPU
package's energy counter and temperatures from the xe hwmon, the actual GPU clock from sysfs and the model server's
resident VRAM from `/proc/PID/fdinfo`. It only reads from the system and sends requests to the running server.

## Results

| Run | Mode | Wall time | Tokens generated | Tokens/s | GPU package energy | Energy per token | Package power |
|---|---|---:|---:|---:|---:|---:|---:|
| r1-j1 | one at a time | 154.23 s | 5,255 | 34.07 | 17,415.6 J | 3.314 J | 113 W |
| r1-j2 | two at a time | 101.98 s | 5,286 | 51.84 | 11,911.5 J | 2.253 J | 117 W |
| r2-j2 | two at a time | 100.52 s | 5,177 | 51.50 | 11,742.1 J | 2.268 J | 117 W |
| r2-j1 | one at a time | 154.28 s | 5,250 | 34.03 | 17,421.7 J | 3.318 J | 113 W |
| r3-j1 | one at a time | 155.07 s | 5,286 | 34.09 | 17,521.2 J | 3.315 J | 113 W |
| r3-j2 | two at a time | 102.01 s | 5,286 | 51.82 | 11,917.9 J | 2.255 J | 117 W |

Means: one at a time 154.5 s (standard deviation 0.4 s), 34.1 tok/s and 3.316 J per token. Two at a time 101.5 s
(standard deviation 0.7 s), 51.7 tok/s and 2.259 J per token. In every run the clock's median was 2850 MHz, the model
server held 9,145 MiB before and after, seven of eight jobs exited 0 and no quote failed in the 42 complete answers.

The eighth job, `engine-summary`, runs past the 1,600-token limit every time and its JSON comes back cut short and
`llm-task` exits 1 in both modes alike. Its tokens still count toward the throughput because the card generated them.

Time per job, mean of three runs:

| Job | One at a time | Two at a time | Slower by |
|---|---:|---:|---:|
| results | 6.5 s | 8.5 s | 30.7% |
| whats-new | 12.1 s | 14.5 s | 19.6% |
| setup | 13.9 s | 16.5 s | 18.6% |
| replicate | 16.5 s | 20.0 s | 21.4% |
| root-plan | 15.4 s | 18.9 s | 22.4% |
| limits-methods | 9.9 s | 12.9 s | 30.5% |
| engine-summary | 46.4 s | 57.5 s | 24.1% |
| sustained-analysis | 33.8 s | 42.6 s | 26.1% |

Two runs in the same mode gave identical answers 17 of 21 times (81%), comparing the saved JSON that `llm-task`
prints after parsing, and two runs in different modes 49 of 63
times (78%). With each run's marker already changing the prompt slightly I can't tell a gap that small from chance.

At this size generating a token is mostly a matter of reading the model's weights out of VRAM. With two requests in
flight the card can use each read of the weights for both of them, which cuts the memory traffic behind every token
and is the usual explanation for gains like this one. I measured time and energy here, not the memory traffic itself.

## The free memory the card reports

`llama-cli --list-devices` says `Vulkan0: Intel(R) Arc(tm) B580 Graphics (BMG G21) (12216 MiB, 10994 MiB free)`. The
kernel's per-client accounting (`drm-resident-vram0` in `/proc/PID/fdinfo`) says the model server alone holds 9,145
MiB, which leaves 3,071 MiB at most before the desktop takes its share.

The gap runs through three layers:

1. **Kernel.** `struct drm_xe_mem_region` in the xe uAPI header documents `used` and `cpu_visible_used` as requiring
   CAP_PERFMON or CAP_SYS_ADMIN, and says that without them "the value here will always equal zero".
2. **Mesa.** `src/intel/dev/xe/intel_device_info.c` computes free VRAM from those two fields: the CPU-visible part as
   its size minus `cpu_visible_used` and the rest as its size minus (`used` minus `cpu_visible_used`). With both at
   zero all of it counts as free. On the B580, with full CPU access to VRAM, it's all the CPU-visible part. The same
   file's system-memory branch notes "if running without elevated privileges Xe reports used == 0".
   `anv_get_memory_budget()` in `src/intel/vulkan/anv_physical_device.c` then reports a heap budget of the heap's
   usage plus 90% of that free memory ("report at most 90% of the available heap memory"), rounded down to a MiB.
   For a program that hasn't allocated anything yet that's 90% of 12,216 MiB, which is 10,994 MiB. A program that
   already holds U MiB is offered min(12,216, U + 10,994) and told U less than that is free, which still leaves out
   everything other programs hold.
3. **llama.cpp.** `ggml_backend_vk_get_device_memory()` in `ggml/src/ggml-vulkan/ggml-vulkan.cpp` sets free memory to
   the heap budget minus the heap usage from `VK_EXT_memory_budget`.

Recent llama.cpp builds act on that number. `--fit` is on by default and picks the GPU layers and context size from
free memory, leaving a 1,024 MiB margin. `llama-fit-params` runs the same fit as a dry run: it loads the model with
`no_alloc` and without its tensor data, so it estimates memory without loading the model's weights (the Vulkan
backend still starts up). Next to my running model server it chose
`-c 139008 -ngl -1`, every layer on the GPU, and its own estimate for that is 6,637 MiB of model, 2,652 MiB of context
and 679 MiB of compute on the card, about 9,968 MiB in all (each figure is rounded down). I didn't let a second model load for real because my desktop
runs on the same card.

The i915 uAPI header carries the same note for `unallocated_size`, which suggests Arc A-series cards on i915 behave
the same way. I haven't tested one. Until this is fixed anyone running llama.cpp on an Intel Arc card under Linux should
turn the fit off with `--fit off` or set `-ngl` and `-c` themselves whenever anything else is using the card.

## How to replicate

1. **Serve a model with two slots,** for example with the command above, and put `scripts/llm-batch` and
   `scripts/llm-task` in `~/llm/bin`. In `llm-task` the `darwin` node is `http://127.0.0.1:1235`. Edit `NODES` to
   match your server.
2. **Measure,** from this folder: `python3 -I scripts/measure_slots.py data/my-run`. It needs a running user service
   called `darwin-llm` and an xe hwmon, so on another setup change `PID`, `SERVER_LOG` and the sampler paths at the top.
3. **Summarize:** `python3 -I scripts/summarize.py data/my-run` prints the tables above.
4. **Check your free-memory figure.** With something else holding VRAM, compare
   `llama-cli --list-devices 2>&1 | grep Vulkan` with
   `grep -h drm-resident-vram0 /proc/PID/fdinfo/* | awk '{s+=$2} END {print s/1024 " MiB"}'` for that program, then
   see what the fit would do with `llama-fit-params -m MODEL.gguf -np 1`.
5. **Re-render the screenshots** from their source text:
   `node ../tools/render-terminal.mjs OUT.png "Title" screenshots/source/NAME.txt`.

If your Arc card shows the same gap, or doesn't, please open an issue on this repository with both numbers and your
card, kernel and Mesa versions.

## Limits

One card, one model and one kind of job, with three runs of each mode. The energy figures come from the GPU package's
own counter and leave out the card's memory, fans and power losses as well as the rest of the PC. My desktop ran on the
same card the whole time as it always does. I didn't test what happens when a second model actually tries to load.
Giving the server CAP_PERFMON should make the free figure honest but it hands the server a broad privilege. I haven't
tried it. During run r2-j1 another program on darwin sent the server a 26-token request that took a quarter of a
second (it's in that run's server log). That run's time matches the other two. Each run's energy comes from counter
readings at its start and end, which the script saves only as their difference. The 2 Hz telemetry brackets every total.

## How it was done

I asked whether darwin could get more out of the hardware it already has, approved the change and decided what got
published. Claude Code (Anthropic's Claude Opus 5.5) wrote `llm-batch` and the measurement scripts, ran the tests,
traced the free-memory number through the kernel, Mesa and llama.cpp source and drafted this write-up in my voice.
Codex (OpenAI's gpt-6-astra) then checked every number against the raw data and every code claim against the source.
It caught five mistakes in the first draft, all fixed here. Its brief and review are in `methods/`. The model under
test did the extraction work being measured.

## Sources

- Linux xe uAPI header, `include/uapi/drm/xe_drm.h`, `struct drm_xe_mem_region` (as shipped in linux-libc-dev 6.16.3).
- Linux i915 uAPI header, `include/uapi/drm/i915_drm.h`, `struct drm_i915_memory_region_info`.
- Mesa, tag `mesa-26.1.6`: `src/intel/dev/xe/intel_device_info.c` lines 115 and 131–132, and
  `src/intel/vulkan/anv_physical_device.c` lines 3110–3172.
  https://gitlab.freedesktop.org/mesa/mesa/-/tree/mesa-26.1.6
- llama.cpp, tag `b11747`: `ggml/src/ggml-vulkan/ggml-vulkan.cpp` lines 15311–15315, `common/fit.cpp` and
  `tools/fit-params/fit-params.cpp`. https://github.com/ggml-org/llama.cpp/tree/b11747
