#!/usr/bin/env python3
"""Fit a first-order thermal model to kala's P100 trace: dT/dt = (Ta + R*P(t) - T) / tau.
Simulate with the measured power, grid-search Ta, R, tau for least squared error, then predict
how long the card takes to reach 79 C from 45 C at a constant power draw. Usage: thermal_fit.py tele.csv"""
import datetime as dt
import sys

t, T, P = [], [], []
for line in open(sys.argv[1]):
    p = [x.strip() for x in line.split(",")]
    if len(p) < 9:
        continue
    t.append(dt.datetime.strptime(p[0], "%Y/%m/%d %H:%M:%S.%f").timestamp())
    T.append(float(p[1]))
    P.append(float(p[4]))


def sse(Ta, R, tau):
    Ts, err = T[0], 0.0
    for i in range(1, len(t)):
        h = t[i] - t[i - 1]
        Ts += h * (Ta + R * P[i - 1] - Ts) / tau
        err += (Ts - T[i]) ** 2
    return err


best = None
for Ta in [x * 0.5 for x in range(20, 81)]:          # 10..40 C
    for R in [x * 0.01 for x in range(40, 131)]:      # 0.40..1.30 C/W
        for tau in range(80, 501, 10):                # 80..500 s
            e = sse(Ta, R, tau)
            if best is None or e < best[0]:
                best = (e, Ta, R, tau)
e, Ta, R, tau = best
rms = (e / (len(t) - 1)) ** 0.5
print(f"fit: Ta={Ta:.1f} C  R={R:.2f} C/W  tau={tau} s  rms error={rms:.2f} C over {len(t)} samples")
print(f"steady state at 79 C needs P <= {(79 - Ta) / R:.0f} W")
import math
for Pw in (185, 150, 125, 100, 80):
    Teq = Ta + R * Pw
    if Teq <= 79:
        print(f"{Pw:>4} W: equilibrium {Teq:.0f} C, never throttles")
    else:
        print(f"{Pw:>4} W: equilibrium {Teq:.0f} C, reaches 79 C from 45 C in {tau * math.log((Teq - 45) / (Teq - 79)):.0f} s")
