#!/bin/bash
# A/B llama.cpp Vulkan settings on kala's P100 with the INSTALLED LM Studio build (the production binary),
# using a second, temporary llama-server on 127.0.0.1:18081 with the small Qwen2.5-VL-3B text model.
# The production server on :1234 is not touched. The P100 throttles at 79 C after ~70 s of full load,
# so every config waits until the GPU is below COOL_C before it starts, and runs only a short burst.
set -u
D="$HOME/scratch-p100-2026-10-29"
B="$HOME/.lmstudio/extensions/backends/llama.cpp-linux-x86_64-vulkan-avx2-2.17.0"
M="$HOME/.lmstudio/models/vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
PORT=18081
COOL_C=55
export LD_LIBRARY_PATH="$B" VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json

nvidia-smi --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,clocks_event_reasons.active,utilization.gpu,utilization.memory,pstate \
  --format=csv,noheader,nounits -lms 500 > "$D/tele-flags.csv" &
LOGGER=$!
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; kill "$LOGGER" 2>/dev/null; }
trap cleanup EXIT

wait_cool() {
  for _ in $(seq 1 120); do
    t=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)
    [ "$t" -lt "$COOL_C" ] && { echo "cool at ${t}C $(date +%T)"; return; }
    sleep 5
  done
  echo "still ${t}C after 10 min, continuing"
}

run_cfg() {  # label, env assignments (space separated or "-"), extra server args...
  local label="$1" envs="$2"; shift 2
  local envarr=(); [ "$envs" != "-" ] && read -r -a envarr <<< "$envs"
  env "${envarr[@]}" "$B/llama-server" -m "$M" --device Vulkan0 -ngl 999 -c 4096 --parallel 1 -t 8 \
      --host 127.0.0.1 --port $PORT "$@" > "$D/srv-$label.log" 2>&1 &
  SRV=$!
  local up=0
  for _ in $(seq 1 120); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && { up=1; break; }; sleep 1; done
  if [ $up -eq 0 ]; then echo "FAILED to start: $label"; kill "$SRV" 2>/dev/null; SRV=""; return; fi
  wait_cool
  echo "$label start $(date +%T)"
  python3 -I "$D/loadtest.py" "http://127.0.0.1:$PORT" 1 16 "warm-$label" > /dev/null
  python3 -I "$D/loadtest.py" "http://127.0.0.1:$PORT" 3 128 "$label" >> "$D/load-flags.jsonl"
  kill "$SRV"; wait "$SRV" 2>/dev/null; SRV=""
}

: > "$D/load-flags.jsonl"
run_cfg base      -                       -b 1024 -ub 512
run_cfg fa_on     -                       -b 1024 -ub 512 -fa on
run_cfg fa_off    -                       -b 1024 -ub 512 -fa off
run_cfg ub256     -                       -b 1024 -ub 256
run_cfg no_f16    GGML_VK_DISABLE_F16=1   -b 1024 -ub 512
run_cfg base2     -                       -b 1024 -ub 512
echo "done $(date +%T)"
