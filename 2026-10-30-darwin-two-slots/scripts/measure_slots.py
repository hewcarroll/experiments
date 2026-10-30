#!/usr/bin/env python3
"""Compare one-at-a-time with two-at-a-time batches on darwin's llama-server (Intel Arc B580, 2 slots).

Runs the jobs in scripts/jobs.json through llm-batch in alternating order (j1, j2, j2, j1, j1, j2), each run with its own
marker in the system prompt so the server's prompt cache can't favour a later run. While it runs, a sampler records the
GPU package energy counter, package and VRAM temperatures, the GPU clock and the model server's resident VRAM twice a
second. For each run it saves the llm-batch output, its stderr, and the slice of the server log the run produced.

Usage (from the experiment folder): python3 -I scripts/measure_slots.py OUT_DIR
Needs: ~/llm/bin/llm-batch and llm-task, a running user service `darwin-llm` (llama-server with -np 2), the xe hwmon.
Read-only towards the system: it only sends requests to the running server and reads sysfs and /proc.
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
LLM_BATCH = os.path.expanduser("~/llm/bin/llm-batch")
SERVER_LOG = os.path.expanduser("~/llm/logs/darwin-llm.log")
ORDER = [(1, 1), (1, 2), (2, 2), (2, 1), (3, 1), (3, 2)]   # (repetition, workers)
SETTLE_S = 20


def xe_hwmon():
    for h in glob.glob("/sys/class/hwmon/hwmon*"):
        if open(f"{h}/name").read().strip() == "xe":
            return h
    sys.exit("no xe hwmon found")


HW = xe_hwmon()
T_PKG = T_VRAM = None
for f in glob.glob(f"{HW}/temp*_label"):
    lab = open(f).read().strip()
    if lab == "pkg":
        T_PKG = f.replace("_label", "_input")
    elif lab == "vram":
        T_VRAM = f.replace("_label", "_input")
ENERGY = next(f.replace("_label", "_input") for f in glob.glob(f"{HW}/energy*_label") if open(f).read().strip() == "pkg")
FREQ = glob.glob("/sys/class/drm/card*/device/tile0/gt0/freq0/act_freq")[0]
PID = subprocess.run(["systemctl", "--user", "show", "-p", "MainPID", "--value", "darwin-llm"],
                     capture_output=True, text=True).stdout.strip()


def read_int(path):
    with open(path) as f:
        return int(f.read().strip())


def vram_mib():
    total = 0
    for fd in glob.glob(f"/proc/{PID}/fdinfo/*"):
        try:
            for line in open(fd):
                if line.startswith("drm-resident-vram0:"):
                    total += int(line.split()[1])
        except OSError:
            pass
    return round(total / 1024)


def log_lines():
    with open(SERVER_LOG, "rb") as f:
        return sum(1 for _ in f)


stop = threading.Event()


def sampler():
    with open(f"{OUT}/telemetry.csv", "w") as out:
        out.write("time,energy_uj,pkg_temp_c,vram_temp_c,gpu_mhz,server_vram_mib\n")
        while not stop.is_set():
            out.write(f"{time.time():.2f},{read_int(ENERGY)},{read_int(T_PKG) / 1000:.0f},{read_int(T_VRAM) / 1000:.0f},"
                      f"{read_int(FREQ)},{vram_mib()}\n")
            out.flush()
            stop.wait(0.5)


threading.Thread(target=sampler, daemon=True).start()
jobs = json.load(open("scripts/jobs.json"))
summary = []
time.sleep(5)
for rep, workers in ORDER:
    tag = f"r{rep}-j{workers}"
    with open(f"{OUT}/jobs-{tag}.jsonl", "w") as f:
        for j in jobs:
            f.write(json.dumps(dict(j, system=f"Run {tag}. " + j["system"])) + "\n")
    v0, e0, l0, t0 = vram_mib(), read_int(ENERGY), log_lines(), time.time()
    p = subprocess.run([LLM_BATCH, "--node", "darwin", "--jobs", f"{OUT}/jobs-{tag}.jsonl",
                        "--out", f"{OUT}/results-{tag}.jsonl", "-j", str(workers)], capture_output=True, text=True)
    t1, e1, l1, v1 = time.time(), read_int(ENERGY), log_lines(), vram_mib()
    open(f"{OUT}/llm-batch-{tag}.txt", "w").write(p.stderr)
    with open(SERVER_LOG, "rb") as f:
        lines = f.readlines()[l0:l1]
    open(f"{OUT}/server-log-{tag}.log", "wb").write(b"".join(lines))
    res = [json.loads(l) for l in open(f"{OUT}/results-{tag}.jsonl") if l.strip()]
    gen = sum(r.get("gen_tok") or 0 for r in res)
    joules = (e1 - e0) / 1e6
    row = {"run": tag, "workers": workers, "start": round(t0, 2), "wall_s": round(t1 - t0, 2), "jobs": len(res),
           "exit0": sum(r["exit"] == 0 for r in res), "quote_fail": sum(r["quote_fail"] for r in res),
           "gen_tokens": gen, "gen_tok_s": round(gen / (t1 - t0), 2), "gpu_pkg_joules": round(joules, 1),
           "joules_per_gen_token": round(joules / gen, 3) if gen else None, "server_vram_mib": [v0, v1]}
    summary.append(row)
    print(json.dumps(row), flush=True)
    time.sleep(SETTLE_S)
stop.set()
json.dump(summary, open(f"{OUT}/summary.json", "w"), indent=1)
