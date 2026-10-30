#!/usr/bin/env python3
"""Read-only NVML capability probe for GPU 0. Calls only Get* functions; changes nothing."""
import ctypes as C

nvml = C.CDLL("libnvidia-ml.so.1")
ERR = {0: "OK", 1: "UNINITIALIZED", 2: "INVALID_ARGUMENT", 3: "NOT_SUPPORTED", 4: "NO_PERMISSION",
       6: "NOT_FOUND", 7: "INSUFFICIENT_SIZE", 13: "FUNCTION_NOT_FOUND", 15: "GPU_IS_LOST", 25: "ARGUMENT_VERSION_MISMATCH",
       999: "UNKNOWN"}


def err(rc):
    return ERR.get(rc, f"rc={rc}")


def call(name, *args):
    try:
        fn = getattr(nvml, name)
    except AttributeError:
        return "SYMBOL_MISSING"
    return fn(*args)


assert nvml.nvmlInit_v2() == 0
dev = C.c_void_p()
assert nvml.nvmlDeviceGetHandleByIndex_v2(0, C.byref(dev)) == 0

drv = C.create_string_buffer(96)
nvml.nvmlSystemGetDriverVersion(drv, 96)
print("driver", drv.value.decode())

# --- clock offsets (the Linux 'undervolt' path) ---
for fn in ("nvmlDeviceGetGpcClkVfOffset", "nvmlDeviceGetMemClkVfOffset"):
    v = C.c_int()
    rc = call(fn, dev, C.byref(v))
    print(fn, err(rc) if rc != 0 else v.value)
for fn in ("nvmlDeviceGetGpcClkMinMaxVfOffset", "nvmlDeviceGetMemClkMinMaxVfOffset"):
    a, b = C.c_int(), C.c_int()
    rc = call(fn, dev, C.byref(a), C.byref(b))
    print(fn, err(rc) if rc != 0 else (a.value, b.value))


class ClockOffset(C.Structure):  # nvmlClockOffset_v1_t
    _fields_ = [("version", C.c_uint), ("type", C.c_int), ("pstate", C.c_int),
                ("clockOffsetMHz", C.c_int), ("minClockOffsetMHz", C.c_int), ("maxClockOffsetMHz", C.c_int)]


for ctype, cname in ((0, "GRAPHICS"), (2, "MEM")):
    co = ClockOffset()
    co.version = C.sizeof(ClockOffset) | (1 << 24)
    co.type, co.pstate = ctype, 0
    rc = call("nvmlDeviceGetClockOffsets", dev, C.byref(co))
    print(f"nvmlDeviceGetClockOffsets({cname},P0)", err(rc) if rc != 0 else
          (co.clockOffsetMHz, co.minClockOffsetMHz, co.maxClockOffsetMHz))

# --- performance states ---
ps = (C.c_int * 16)()
rc = call("nvmlDeviceGetSupportedPerformanceStates", dev, ps, 16)
states = [p for p in ps if p != 32] if rc == 0 else []
print("SupportedPerformanceStates", err(rc) if rc != 0 else [f"P{p}" for p in states])
for p in states:
    for ctype, cname in ((0, "GRAPHICS"), (1, "SM"), (2, "MEM")):
        lo, hi = C.c_uint(), C.c_uint()
        rc = call("nvmlDeviceGetMinMaxClockOfPState", dev, ctype, p, C.byref(lo), C.byref(hi))
        print(f"  P{p} {cname} min/max", err(rc) if rc != 0 else (lo.value, hi.value))


class Str2048(C.Structure):  # nvmlDevicePerfModes_v1_t / nvmlDeviceCurrentClockFreqs_v1_t
    _fields_ = [("version", C.c_uint), ("str", C.c_char * 2048)]


for fn in ("nvmlDeviceGetPerformanceModes", "nvmlDeviceGetCurrentClockFreqs"):
    s = Str2048()
    s.version = C.sizeof(Str2048) | (1 << 24)
    rc = call(fn, dev, C.byref(s))
    print(fn, err(rc) if rc != 0 else s.str.decode(errors="replace"))

# --- thresholds ---
names = ["SHUTDOWN", "SLOWDOWN", "MEM_MAX", "GPU_MAX", "ACOUSTIC_MIN", "ACOUSTIC_CURR", "ACOUSTIC_MAX", "GPS_CURR"]
for i, n in enumerate(names):
    t = C.c_uint()
    rc = call("nvmlDeviceGetTemperatureThreshold", dev, i, C.byref(t))
    print("TemperatureThreshold", n, err(rc) if rc != 0 else t.value)

# --- clock event reasons the driver can report ---
mask = C.c_ulonglong()
rc = call("nvmlDeviceGetSupportedClocksEventReasons", dev, C.byref(mask))
if rc == "SYMBOL_MISSING":
    rc = call("nvmlDeviceGetSupportedClocksThrottleReasons", dev, C.byref(mask))
bits = {0x1: "GpuIdle", 0x2: "ApplicationsClocksSetting", 0x4: "SwPowerCap", 0x8: "HwSlowdown",
        0x10: "SyncBoost", 0x20: "SwThermalSlowdown", 0x40: "HwThermalSlowdown", 0x80: "HwPowerBrakeSlowdown",
        0x100: "DisplayClockSetting"}
print("SupportedClocksEventReasons", err(rc) if rc != 0 else
      f"0x{mask.value:x} " + ",".join(n for b, n in bits.items() if mask.value & b))

# --- violation (throttle) time since driver load, per policy ---


class Violation(C.Structure):
    _fields_ = [("referenceTime", C.c_ulonglong), ("violationTime", C.c_ulonglong)]


for code, n in ((0, "POWER"), (1, "THERMAL"), (2, "SYNC_BOOST"), (3, "BOARD_LIMIT"), (4, "LOW_UTILIZATION"),
                (5, "RELIABILITY"), (10, "TOTAL_APP_CLOCKS"), (11, "TOTAL_BASE_CLOCKS")):
    v = Violation()
    rc = call("nvmlDeviceGetViolationStatus", dev, code, C.byref(v))
    print("ViolationStatus", n, err(rc) if rc != 0 else f"{v.violationTime / 1e9:.1f} s")

# --- permissions / power ---
for code, n in ((0, "SET_APPLICATION_CLOCKS"), (1, "SET_AUTO_BOOSTED_CLOCKS")):
    st = C.c_int()
    rc = call("nvmlDeviceGetAPIRestriction", dev, code, C.byref(st))
    print("APIRestriction", n, err(rc) if rc != 0 else ("root-only" if st.value else "any user"))
lo, hi = C.c_uint(), C.c_uint()
rc = call("nvmlDeviceGetPowerManagementLimitConstraints", dev, C.byref(lo), C.byref(hi))
print("PowerLimitConstraints W", err(rc) if rc != 0 else (lo.value / 1000, hi.value / 1000))
e = C.c_ulonglong()
rc = call("nvmlDeviceGetTotalEnergyConsumption", dev, C.byref(e))
print("TotalEnergyConsumption", err(rc) if rc != 0 else f"{e.value / 1000:.1f} J since driver load")
cur, pend = C.c_int(), C.c_int()
rc = call("nvmlDeviceGetAutoBoostedClocksEnabled", dev, C.byref(cur), C.byref(pend))
print("AutoBoostedClocks", err(rc) if rc != 0 else (cur.value, pend.value))
cur, pend = C.c_int(), C.c_int()
rc = call("nvmlDeviceGetEccMode", dev, C.byref(cur), C.byref(pend))
print("EccMode current/pending", err(rc) if rc != 0 else (cur.value, pend.value))
bw = C.c_uint()
rc = call("nvmlDeviceGetMemoryBusWidth", dev, C.byref(bw))
print("MemoryBusWidth", err(rc) if rc != 0 else bw.value)
cores = C.c_uint()
rc = call("nvmlDeviceGetNumGpuCores", dev, C.byref(cores))
print("NumGpuCores", err(rc) if rc != 0 else cores.value)

# --- field values: memory temperature and a few others ---


class FieldValue(C.Structure):  # nvmlFieldValue_t
    _fields_ = [("fieldId", C.c_uint), ("scopeId", C.c_uint), ("timestamp", C.c_longlong),
                ("latencyUsec", C.c_longlong), ("valueType", C.c_int), ("nvmlReturn", C.c_int),
                ("value", C.c_ulonglong)]


fields = {82: "FI_DEV_MEMORY_TEMP", 83: "FI_DEV_TOTAL_ENERGY_CONSUMPTION"}
arr = (FieldValue * len(fields))()
for i, f in enumerate(fields):
    arr[i].fieldId = f
rc = call("nvmlDeviceGetFieldValues", dev, len(fields), arr)
for i, (f, n) in enumerate(fields.items()):
    print("FieldValue", f, n, err(arr[i].nvmlReturn) if arr[i].nvmlReturn != 0 else arr[i].value)

nvml.nvmlShutdown()
