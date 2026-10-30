#!/usr/bin/env python3
"""Join 2 Hz nvidia-smi telemetry with per-request llama-server timings.
Usage: analyze.py tele.csv load.jsonl
Per request: prompt phase = [start, start + prompt_ms], gen phase = [.. , + gen_ms] (server-reported).
Energy per token = sum(power * dt) over the phase / tokens in that phase (power sampled at ~2 Hz)."""
import collections
import datetime as dt
import json
import sys

REASONS = {0x1: "idle", 0x2: "app-clock", 0x4: "sw-power-cap", 0x8: "hw-slowdown", 0x20: "sw-thermal",
           0x40: "hw-thermal", 0x80: "hw-power-brake"}

rows = []
for line in open(sys.argv[1]):
    p = [x.strip() for x in line.split(",")]
    if len(p) < 9:
        continue
    t = dt.datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f").timestamp()
    rows.append({"t": t, "temp": int(p[1]), "sm": int(p[2]), "mem": int(p[3]), "w": float(p[4]),
                 "reason": int(p[5], 16), "util": int(p[6])})
reqs = [json.loads(l) for l in open(sys.argv[2]) if l.strip()]


def reason_names(mask):
    return "+".join(n for b, n in REASONS.items() if mask & b) or "none"


def window(t0, t1):
    return [r for r in rows if t0 <= r["t"] < t1]


def energy(t0, t1):
    """Time-weighted energy over [t0, t1]: each sample's power holds until the next sample (zero-order hold),
    clamped at the window edges so boundary intervals are counted (fix after Codex round 2)."""
    e = 0.0
    for i in range(len(rows) - 1):
        a, b = max(rows[i]["t"], t0), min(rows[i + 1]["t"], t1)
        if b > a:
            e += rows[i]["w"] * (b - a)
    return e


def summ(ws):
    if not ws:
        return "no samples"
    reasons = collections.Counter(reason_names(r["reason"]) for r in ws)
    sm = sorted(r["sm"] for r in ws)
    return (f"n={len(ws)} temp {min(r['temp'] for r in ws)}-{max(r['temp'] for r in ws)}C "
            f"sm {sm[0]}/{sm[len(sm) // 2]}/{sm[-1]} MHz(min/med/max) "
            f"power avg {sum(r['w'] for r in ws) / len(ws):.0f} W max {max(r['w'] for r in ws):.0f} W "
            f"util avg {sum(r['util'] for r in ws) / len(ws):.0f}% reasons {dict(reasons)}")


print("IDLE before :", summ(window(rows[0]["t"], reqs[0]["start"])))
print(f"{'req':>3} {'pp tok/s':>8} {'tg tok/s':>8} | prompt phase                     | generation phase")
for q in reqs:
    pp_s = q["prompt_n"] / q["pp_tok_s"] if q["pp_tok_s"] else 0
    tg_s = q["gen_n"] / q["tg_tok_s"] if q["tg_tok_s"] else 0
    a, b, c = q["start"], q["start"] + pp_s, q["start"] + pp_s + tg_s
    wp, wg = window(a, b), window(b, c)
    ep, eg = energy(a, b), energy(b, c)
    ew = energy(q["start"], q["start"] + q["wall_s"])
    # identity check: E/N must equal mean power / rate over the same window
    pg = eg / tg_s if tg_s else float("nan")
    print(f"{q['i']:>3} {q['pp_tok_s']:>8} {q['tg_tok_s']:>8} | {pp_s:5.1f}s {ep / q['prompt_n']:.2f} J/tok "
          f"| {tg_s:5.1f}s {eg / q['gen_n']:.2f} J/tok (P_tw {pg:.0f} W, check {pg / q['tg_tok_s']:.2f}) "
          f"| request {ew:.0f} J :: {summ(wg)}")
last = reqs[-1]
end_load = last["start"] + last["wall_s"]
print("LOAD overall:", summ(window(reqs[0]["start"], end_load)))
print("COOLDOWN    :", summ(window(end_load, rows[-1]["t"] + 1)))
cool = window(end_load, rows[-1]["t"] + 1)
if cool:
    print("cooldown temps every 10 s:", [r["temp"] for r in cool[::20]])
