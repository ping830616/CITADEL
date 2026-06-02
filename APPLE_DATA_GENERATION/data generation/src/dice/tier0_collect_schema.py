import csv, time, json, math
from pathlib import Path
import psutil
from dataclasses import dataclass
from typing import Dict, Any, Optional

def _nan(): return float("nan")

def _rate(curr, prev, dt):
    if prev is None or dt <= 0: return _nan()
    return (curr - prev) / dt

def _safe(obj, name):
    try:
        v = getattr(obj, name)
        return float(v)
    except Exception:
        return _nan()

@dataclass
class Prev:
    disk_total: Optional[Any] = None
    net_total: Optional[Any] = None
    ts: Optional[float] = None

def sample_raw(prev: Prev, dt_default: float) -> Dict[str, float]:
    ts = time.time()
    dt = (ts - prev.ts) if prev.ts else dt_default
    out: Dict[str, float] = {}

    # CPU
    out["cpu_pct"] = float(psutil.cpu_percent(interval=None))
    ct = psutil.cpu_times_percent(interval=None)
    for k in ["user","system","idle","nice","iowait","irq","softirq","steal"]:
        out[f"cpu_times_{k}_pct"] = _safe(ct, k)

    # per-cpu
    try:
        per = psutil.cpu_percent(interval=None, percpu=True)
        for i, v in enumerate(per):
            out[f"cpu{i}_pct"] = float(v)
    except Exception:
        pass

    # load
    try:
        l1,l5,l15 = psutil.getloadavg()
        out["load1"] = float(l1); out["load5"] = float(l5); out["load15"] = float(l15)
    except Exception:
        out["load1"]=_nan(); out["load5"]=_nan(); out["load15"]=_nan()

    # cpu_stats
    try:
        cs = psutil.cpu_stats()
        out["ctx_switches"] = float(cs.ctx_switches)
        out["interrupts"] = float(cs.interrupts)
        out["soft_interrupts"] = float(getattr(cs,"soft_interrupts",_nan()))
        out["syscalls"] = float(getattr(cs,"syscalls",_nan()))
    except Exception:
        pass

    # freq
    try:
        cf = psutil.cpu_freq()
        out["cpu_freq_current_mhz"] = float(cf.current) if cf else _nan()
        out["cpu_freq_min_mhz"] = float(cf.min) if cf else _nan()
        out["cpu_freq_max_mhz"] = float(cf.max) if cf else _nan()
    except Exception:
        pass

    # memory
    vm = psutil.virtual_memory()
    for k in ["total","available","used","free","active","inactive","wired","cached"]:
        out[f"mem_{k}_bytes"] = _safe(vm, k)
    out["mem_percent"] = float(vm.percent)

    sm = psutil.swap_memory()
    for k in ["total","used","free","sin","sout"]:
        out[f"swap_{k}_bytes"] = _safe(sm, k)
    out["swap_percent"] = float(sm.percent)

    # disk totals
    disk = psutil.disk_io_counters(perdisk=False)
    out["disk_read_Bps"]  = _rate(disk.read_bytes,  prev.disk_total.read_bytes if prev.disk_total else None, dt)
    out["disk_write_Bps"] = _rate(disk.write_bytes, prev.disk_total.write_bytes if prev.disk_total else None, dt)
    out["disk_read_IOPS"]  = _rate(disk.read_count,  prev.disk_total.read_count if prev.disk_total else None, dt)
    out["disk_write_IOPS"] = _rate(disk.write_count, prev.disk_total.write_count if prev.disk_total else None, dt)
    prev.disk_total = disk

    # network totals
    net = psutil.net_io_counters(pernic=False)
    out["net_sent_Bps"] = _rate(net.bytes_sent, prev.net_total.bytes_sent if prev.net_total else None, dt)
    out["net_recv_Bps"] = _rate(net.bytes_recv, prev.net_total.bytes_recv if prev.net_total else None, dt)
    out["net_sent_Pps"] = _rate(net.packets_sent, prev.net_total.packets_sent if prev.net_total else None, dt)
    out["net_recv_Pps"] = _rate(net.packets_recv, prev.net_total.packets_recv if prev.net_total else None, dt)
    prev.net_total = net

    # misc
    out["pids_count"] = float(len(psutil.pids()))
    out["uptime_s"] = float(ts - psutil.boot_time())

    prev.ts = ts
    return out

def build_schema(probe_rows: list) -> list:
    """
    Keep keys that are non-NaN at least once in the probe.
    This prevents persistent NaN columns in Tier-0.
    """
    keys = sorted({k for r in probe_rows for k in r.keys()})
    keep = []
    for k in keys:
        good = any((k in r) and (not math.isnan(r[k])) for r in probe_rows)
        if good:
            keep.append(k)
    return keep

def collect_with_schema(out_csv: str, hz: int, duration_s: int, schema: list):
    dt = 1.0 / hz
    samples = hz * duration_s
    prev = Prev()
    t0 = time.time()

    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["idx","ts_unix_s","t_rel_s"] + schema)
        w.writeheader()

        prev = Prev()
        for i in range(samples):
            ts = time.time()
            raw = sample_raw(prev, dt)
            row = {k: raw.get(k, _nan()) for k in schema}
            w.writerow({"idx": i, "ts_unix_s": ts, "t_rel_s": ts - t0, **row})
            elapsed = time.time() - ts
            time.sleep(max(0.0, dt - elapsed))

def build_and_save_global_schema(schema_path: str, hz: int, probe_s: int = 10):
    """
    Build a Tier-0 global schema using a short probe sampling.
    """
    dt = 1.0 / hz
    n = hz * probe_s
    prev = Prev()
    probe_rows = []
    for _ in range(n):
        probe_rows.append(sample_raw(prev, dt))
        time.sleep(dt)
    schema = build_schema(probe_rows)
    Path(schema_path).write_text(json.dumps({"schema": schema, "probe_s": probe_s, "hz": hz}, indent=2))
    return schema

def load_schema(schema_path: str) -> list:
    obj = json.loads(Path(schema_path).read_text())
    return obj["schema"]
