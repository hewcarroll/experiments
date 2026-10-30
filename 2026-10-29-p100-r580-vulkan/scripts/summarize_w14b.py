#!/usr/bin/env python3
"""Summarize 14B window results and flag any request that ran into thermal throttling.
Usage: summarize_w14b.py results.jsonl tele1.csv [tele2.csv ...]"""
import datetime as dt
import json
import sys

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
tele = []
for path in sys.argv[2:]:
    for line in open(path):
        p = [x.strip() for x in line.split(",")]
        if len(p) < 9:
            continue
        tele.append((dt.datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f").timestamp(), int(p[1]),
                     int(p[2]), float(p[4]), int(p[5], 16)))


def thermal(t0, t1):
    w = [x for x in tele if t0 <= x[0] <= t1]
    if not w:
        return "no telemetry"
    hot = sum(1 for x in w if x[4] & 0x20)
    avg_w = sum(x[3] for x in w) / len(w)
    return f"{w[0][1]}->{max(x[1] for x in w)}C, {avg_w:.0f} W avg" + (f", THROTTLED {hot} samples" if hot else "")


base = {}
for r in rows:
    if not r.get("aggregate") and r["label"] in ("lms_base",):
        base[r["workload"]] = r["sha"]
print(f"{'config':<15}{'workload':<17}{'pp tok/s':>9}{'gen':>5}{'tg tok/s':>9}{'draft':>6}{'acc':>5}{'wall':>7}  same  thermal")
for r in rows:
    if r.get("aggregate"):
        if r["conc"] > 1:
            print(f"{r['label']:<15}{r['workload']:<17}{'':>9}{r['gen_total']:>5}{'':>9}{'':>6}{'':>5}{r['span_s']:>7}"
                  f"  AGGREGATE {r['agg_tok_s']} tok/s over {r['conc']} streams")
        continue
    same = ("yes" if base.get(r["workload"]) == r["sha"] else "NO") if r["workload"] in base else "-"
    print(f"{r['label']:<15}{r['workload']:<17}{r['pp_tok_s']:>9}{r['gen_n']:>5}{r['tg_tok_s']:>9}"
          f"{str(r['draft_n']):>6}{str(r['draft_accepted']):>5}{r['wall_s']:>7}  {same:<4}  "
          f"{thermal(r['start'], r['start'] + r['wall_s'])}")
