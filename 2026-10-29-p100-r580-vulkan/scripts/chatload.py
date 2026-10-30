#!/usr/bin/env python3
"""Replay chat workloads against a llama-server and record the server's own timings.
Usage: chatload.py URL WORKLOADS.json LABEL OUT_DIR [CONCURRENCY]
Each workload: {"name", "system", "user", "max_tokens"}. With CONCURRENCY > 1 every workload is sent
CONCURRENCY times at once (to measure aggregate throughput of parallel slots).
Prints one JSON line per request, plus one "aggregate" line per workload; saves each reply for identity checks."""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request

url, wl_path, label, out_dir = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
conc = int(sys.argv[5]) if len(sys.argv) > 5 else 1
os.makedirs(out_dir, exist_ok=True)
workloads = json.load(open(wl_path))


def one(w, k, results):
    body = json.dumps({"messages": [{"role": "system", "content": w["system"]},
                                    {"role": "user", "content": w["user"]}],
                       "temperature": 0, "seed": 1, "max_tokens": w["max_tokens"], "cache_prompt": False}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        out = json.load(r)
    wall = time.time() - t0
    text = out["choices"][0]["message"]["content"] or ""
    results[k] = (t0, wall, out.get("timings", {}), text)


for w in workloads:
    results = [None] * conc
    threads = [threading.Thread(target=one, args=(w, k, results)) for k in range(conc)]
    t_start = time.time()
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    span = time.time() - t_start
    gen_total = 0
    for k, (t0, wall, tm, text) in enumerate(results):
        sha = hashlib.sha256(text.encode()).hexdigest()[:12]
        if k == 0:
            open(os.path.join(out_dir, f"{label}--{w['name']}.txt"), "w").write(text)
        gen_total += tm.get("predicted_n", 0)
        print(json.dumps({"label": label, "workload": w["name"], "k": k, "conc": conc, "start": round(t0, 1),
                          "wall_s": round(wall, 2), "prompt_n": tm.get("prompt_n"),
                          "pp_tok_s": round(tm.get("prompt_per_second", 0), 1), "gen_n": tm.get("predicted_n"),
                          "tg_tok_s": round(tm.get("predicted_per_second", 0), 2),
                          "draft_n": tm.get("draft_n"), "draft_accepted": tm.get("draft_n_accepted"),
                          "sha": sha}), flush=True)
    print(json.dumps({"label": label, "workload": w["name"], "aggregate": True, "conc": conc,
                      "span_s": round(span, 2), "gen_total": gen_total,
                      "agg_tok_s": round(gen_total / span, 2) if span else None}), flush=True)
