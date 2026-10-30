#!/bin/bash
# One test window on kala's real 14B (Hew approved 2026-10-29: stop/restart production as needed; b11988 allowed).
# Stops the production llama-server, runs each config as a cool-started short burst on :1234 (bound like production,
# so the uptime monitor's probe is still answered), and ALWAYS restarts production on exit.
# Usage: run_14b_window.sh WINDOW SPEC_TYPE        WINDOW = lms | up ; SPEC_TYPE e.g. ngram-simple
set -u
WIN="$1"; SPEC="${2:-ngram-simple --spec-ngram-simple-size-n 4 --spec-ngram-simple-size-m 16}"
D="$HOME/scratch-p100-2026-10-29"
OUT="$D/w14b"; mkdir -p "$OUT"
LMS="$HOME/.lmstudio/extensions/backends/llama.cpp-linux-x86_64-vulkan-avx2-2.17.0"
UP="$D/b11988/llama-b11988"
MODEL="$HOME/.lmstudio/models/bartowski/Qwen2.5-14B-Instruct-GGUF/Qwen2.5-14B-Instruct-Q4_K_S.gguf"
PORT=1234
COOL_C=55
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json VK_DRIVER_FILES=/usr/share/vulkan/icd.d/nvidia_icd.json

nvidia-smi --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,clocks_event_reasons.active,utilization.gpu,utilization.memory,pstate \
  --format=csv,noheader,nounits -lms 500 > "$OUT/tele-$WIN.csv" &
LOGGER=$!
SRV=""
RESTORED=0
restore() {
  [ "$RESTORED" -eq 1 ] && return
  RESTORED=1
  [ -n "$SRV" ] && { kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; }
  kill "$LOGGER" 2>/dev/null
  systemctl --user start llama-server.service
  for _ in $(seq 1 180); do curl -sf http://127.0.0.1:1234/health >/dev/null && break; sleep 1; done
  echo "production: $(systemctl --user is-active llama-server.service), health $(curl -s http://127.0.0.1:1234/health) $(date +%T)"
}
trap restore EXIT
trap 'restore; exit 1' HUP INT TERM

wait_cool() {
  for _ in $(seq 1 120); do
    t=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits)
    [ "$t" -lt "$COOL_C" ] && return
    sleep 5
  done
  echo "still ${t}C after 10 min, continuing"
}

run_cfg() {  # label, build dir, env ("-" for none), workloads file, concurrency, server args...
  local label="$1" bdir="$2" envs="$3" wl="$4" conc="$5"; shift 5
  local envarr=(); [ "$envs" != "-" ] && read -r -a envarr <<< "$envs"
  env "${envarr[@]}" LD_LIBRARY_PATH="$bdir" "$bdir/llama-server" -m "$MODEL" --device Vulkan0 -ngl 999 --jinja \
      -t 8 -b 1024 -ub 512 --host 0.0.0.0 --port $PORT "$@" > "$OUT/srv-$label.log" 2>&1 &
  SRV=$!
  local up=0
  for _ in $(seq 1 240); do curl -sf "http://127.0.0.1:$PORT/health" >/dev/null && { up=1; break; }; sleep 1; done
  if [ $up -eq 0 ]; then echo "FAILED to start: $label"; kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""; return; fi
  python3 -I "$D/chatload.py" "http://127.0.0.1:$PORT" "$D/workloads-freewrite.json" "warm-$label" "$OUT/warm" > /dev/null
  wait_cool
  echo "$label start $(date +%T) at $(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits) C"
  python3 -I "$D/chatload.py" "http://127.0.0.1:$PORT" "$wl" "$label" "$OUT/replies" "$conc" >> "$OUT/results.jsonl"
  kill "$SRV"; wait "$SRV" 2>/dev/null; SRV=""
}

echo "window $WIN: stopping production $(date +%T)"
systemctl --user stop llama-server.service
sleep 3
case "$WIN" in
  lms)
    run_cfg lms_base   "$LMS" - "$D/workloads-14b.json"       1 --parallel 1 -c 8192
    run_cfg lms_spec   "$LMS" - "$D/workloads-14b.json"       1 --parallel 1 -c 8192 --spec-type $SPEC
    run_cfg lms_par4   "$LMS" - "$D/workloads-freewrite.json" 4 --parallel 4 -c 16384
    ;;
  up)
    run_cfg up_nodot      "$UP" GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1 "$D/workloads-14b.json"       1 --parallel 1 -c 8192
    run_cfg up_dot        "$UP" -                                     "$D/workloads-14b-short.json" 1 --parallel 1 -c 8192
    run_cfg up_nodot_spec "$UP" GGML_VK_DISABLE_INTEGER_DOT_PRODUCT=1 "$D/workloads-14b.json"       1 --parallel 1 -c 8192 --spec-type $SPEC
    ;;
esac
echo "window $WIN done $(date +%T)"
