#!/usr/bin/env python3
"""Sustained-load test against a llama-server: N requests back to back, fixed prompt, forced output length.
Prints one JSON line per request with the server's own timings. Usage: loadtest.py URL N N_PREDICT [label]"""
import json
import sys
import time
import urllib.request

url, n, n_predict = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
label = sys.argv[4] if len(sys.argv) > 4 else ""

para = ("The municipal water utility maintains 412 miles of distribution main, 3,180 hydrants and 41 lift stations. "
        "Each asset record carries an install year, a material code, a diameter and a condition score from one to five. "
        "Inspection crews log defects against the asset identifier, and the work order system schedules repairs by risk. ")
prompt = "Summarize the following operations notes in detail, section by section.\n\n" + para * 24

for i in range(n):
    body = json.dumps({"prompt": prompt, "n_predict": n_predict, "temperature": 0, "ignore_eos": True,
                       "cache_prompt": False, "seed": 1}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/completion", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.load(r)
    t = out.get("timings", {})
    print(json.dumps({"label": label, "i": i, "start": round(t0, 1), "wall_s": round(time.time() - t0, 2),
                      "prompt_n": t.get("prompt_n"), "pp_tok_s": round(t.get("prompt_per_second", 0), 1),
                      "gen_n": t.get("predicted_n"), "tg_tok_s": round(t.get("predicted_per_second", 0), 2)}),
          flush=True)
