#!/usr/bin/env python3
"""Summarize a measure_slots.py run: per-run table, the mean for each mode, and the telemetry ranges per run.
Usage: python3 -I scripts/summarize.py data/run-2026-10-30"""
import csv
import json
import statistics
import sys

d = sys.argv[1]
runs = json.load(open(f"{d}/summary.json"))
tele = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(f"{d}/telemetry.csv"))]

print(f"{'run':<8}{'wall s':>8}{'gen tok':>9}{'tok/s':>8}{'J':>8}{'J/tok':>8}{'pkg W':>7}{'pkg C':>9}{'vram C':>9}{'MHz':>11}{'VRAM MiB':>14}  ok")
for r in runs:
    t0, t1 = r["start"], r["start"] + r["wall_s"]
    w = [x for x in tele if t0 <= x["time"] <= t1]
    watts = r["gpu_pkg_joules"] / r["wall_s"]
    pk = (min(x["pkg_temp_c"] for x in w), max(x["pkg_temp_c"] for x in w))
    vr = (min(x["vram_temp_c"] for x in w), max(x["vram_temp_c"] for x in w))
    mhz = sorted(x["gpu_mhz"] for x in w)
    print(f"{r['run']:<8}{r['wall_s']:>8}{r['gen_tokens']:>9}{r['gen_tok_s']:>8}{r['gpu_pkg_joules']:>8}{r['joules_per_gen_token']:>8}"
          f"{watts:>7.0f}{f'{pk[0]:.0f}-{pk[1]:.0f}':>9}{f'{vr[0]:.0f}-{vr[1]:.0f}':>9}{f'{mhz[len(mhz) // 2]:.0f} med':>11}"
          f"{f'{r['server_vram_mib'][0]}->{r['server_vram_mib'][1]}':>14}  {r['exit0']}/{r['jobs']} exit 0, {r['quote_fail']} quote fail")

for wk in (1, 2):
    rs = [r for r in runs if r["workers"] == wk]
    print(f"workers={wk}: wall {statistics.mean(r['wall_s'] for r in rs):.1f} s "
          f"(sd {statistics.pstdev(r['wall_s'] for r in rs):.1f}), {statistics.mean(r['gen_tok_s'] for r in rs):.1f} tok/s, "
          f"{statistics.mean(r['joules_per_gen_token'] for r in rs):.3f} J/token")
a = [r for r in runs if r["workers"] == 1]
b = [r for r in runs if r["workers"] == 2]
print(f"speedup (mean wall j1 / j2): {statistics.mean(r['wall_s'] for r in a) / statistics.mean(r['wall_s'] for r in b):.2f}x; "
      f"energy per token j2 vs j1: {statistics.mean(r['joules_per_gen_token'] for r in b) / statistics.mean(r['joules_per_gen_token'] for r in a) - 1:+.0%}")

# Per-job time in each mode, and how often two runs gave byte-identical answers (jobs that exited 0 in both runs).
# Each run's prompts carry their own marker, so even two one-at-a-time runs see slightly different prompts.
res = {r["run"]: {x["id"]: x for x in map(json.loads, filter(str.strip, open(f"{d}/results-{r['run']}.jsonl")))} for r in runs}
ids = list(next(iter(res.values())))
print(f"\n{'job':<20}{'1 at a time s':>15}{'2 at a time s':>15}")
for i in ids:
    m = {wk: statistics.mean(res[r["run"]][i]["seconds"] for r in runs if r["workers"] == wk) for wk in (1, 2)}
    print(f"{i:<20}{m[1]:>15.1f}{m[2]:>15.1f}")


def agree(pairs):
    same = total = 0
    for a, b in pairs:
        for i in ids:
            x, y = res[a][i], res[b][i]
            if x["exit"] == 0 and y["exit"] == 0:
                total += 1
                same += x["stdout"].strip() == y["stdout"].strip()
    return f"{same}/{total} ({same / total:.0%})"


j1 = [r["run"] for r in runs if r["workers"] == 1]
j2 = [r["run"] for r in runs if r["workers"] == 2]
within = lambda rs: [(a, b) for n, a in enumerate(rs) for b in rs[n + 1:]]
print(f"\nidentical answers: one-at-a-time runs with each other {agree(within(j1))}, "
      f"two-at-a-time runs with each other {agree(within(j2))}, across the two modes {agree([(a, b) for a in j1 for b in j2])}")
