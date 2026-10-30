#!/bin/bash
# Sustained-load thermal test on kala's live llama-server (:1234). Logs GPU telemetry at 2 Hz.
# Usage: run_live14b.sh TAG N_REQUESTS N_PREDICT
set -u
D="$HOME/scratch-p100-2026-10-29"
TAG="$1"; N="$2"; NP="$3"
nvidia-smi --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.mem,power.draw,clocks_event_reasons.active,utilization.gpu,utilization.memory,pstate \
  --format=csv,noheader,nounits -lms 500 > "$D/tele-$TAG.csv" &
LOGGER=$!
trap 'kill $LOGGER 2>/dev/null' EXIT
echo "start $(date +%T)"
sleep 20
python3 -I "$D/loadtest.py" http://127.0.0.1:1234 "$N" "$NP" "$TAG" > "$D/load-$TAG.jsonl"
echo "load done $(date +%T) rc=$?"
sleep 60
echo "end $(date +%T)"
