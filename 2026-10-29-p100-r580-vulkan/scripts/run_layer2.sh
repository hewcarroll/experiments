#!/bin/bash
# Stand-in test of llama-server speculative decoding and parallel slots on kala's P100, using the INSTALLED
# LM Studio build and the small Qwen2.5-VL-3B text model on a temporary server at 127.0.0.1:18081.
# The production server on :1234 is not touched. Each config starts only when the GPU is below COOL_C.
set -u
D="$HOME/scratch-p100-2026-10-29"
B="$HOME/.lmstudio/extensions/backends/llama.cpp-linux-x86_64-vulkan-avx2-2.17.0"
M="$HOME/.lmstudio/models/vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
PORT=18081
COOL_C=55
OUT="$D/layer2"
mkdir -p "$OUT"
export LD_LIBRARY_PATH="$B" VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json

nvidia-smi --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,clocks_event_reasons.active,utilization.gpu,utilization.memory,pstate \
  --format=csv,noheader,nounits -lms 500 > "$OUT/tele-layer2.csv" &
LOGGER=$!
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; kill "$LOGGER" 2>/dev/null; }
trap cleanup EXIT

wait_cool() {
  for _ in $(seq 1 120); do
    t=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)
    [ "$t" -lt "$COOL_C" ] && return
    sleep 5
  done
  echo "still ${t}C after 10 min, continuing"
}

start_srv() {  # label, server args...
  local label="$1"; shift
  "$B/llama-server" -m "$M" --device Vulkan0 -ngl 999 --jinja -t 8 -b 1024 -ub 512 \
      --host 127.0.0.1 --port $PORT "$@" > "$OUT/srv-$label.log" 2>&1 &
  SRV=$!
  for _ in $(seq 1 120); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && return 0; sleep 1; done
  echo "FAILED to start: $label"; kill "$SRV" 2>/dev/null; SRV=""; return 1
}

stop_srv() { kill "$SRV"; wait "$SRV" 2>/dev/null; SRV=""; }

run_spec() {  # label, server args...
  local label="$1"; shift
  start_srv "$label" --parallel 1 -c 8192 "$@" || return
  wait_cool
  echo "$label start $(date +%T)"
  python3 -I "$D/chatload.py" "http://127.0.0.1:$PORT" "$D/workloads-freewrite.json" "warm-$label" "$OUT/warm" > /dev/null
  python3 -I "$D/chatload.py" "http://127.0.0.1:$PORT" "$D/workloads-collective.json" "$label" "$OUT/replies" >> "$OUT/results.jsonl"
  stop_srv
}

: > "$OUT/results.jsonl"
run_spec spec_none
run_spec ngram_simple     --spec-type ngram-simple
run_spec ngram_simple_n4  --spec-type ngram-simple --spec-ngram-simple-size-n 4 --spec-ngram-simple-size-m 16
run_spec ngram_map_k      --spec-type ngram-map-k
run_spec ngram_mod        --spec-type ngram-mod
run_spec ngram_cache      --spec-type ngram-cache

# parallel slots: 4 slots x 4096 context, free-writing workload sent 1, 2 and 4 at a time
if start_srv par4 --parallel 4 -c 16384; then
  for c in 1 2 4; do
    wait_cool
    echo "par4 conc=$c start $(date +%T)"
    python3 -I "$D/chatload.py" "http://127.0.0.1:$PORT" "$D/workloads-freewrite.json" "par4_c$c" "$OUT/replies" "$c" >> "$OUT/results.jsonl"
  done
  stop_srv
fi
run_spec spec_none2
echo "done $(date +%T)"
