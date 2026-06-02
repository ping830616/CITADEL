import csv
import json
import math
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .cfg import TIER1_ALT_CORE_FIELDS

_NUM_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z%/_]+)?")


def _to_float_with_unit(v) -> float:
    if v is None:
        return math.nan
    if isinstance(v, (int, float)):
        return float(v)

    s = str(v).strip()
    m = _NUM_RE.search(s)
    if not m:
        return math.nan

    val = float(m.group(1))
    unit = (m.group(2) or "").lower()

    # Power
    if unit == "mw":
        return val / 1000.0
    # Frequency -> MHz
    if unit == "hz":
        return val / 1_000_000.0
    if unit == "khz":
        return val / 1000.0
    if unit == "ghz":
        return val * 1000.0

    return val


def _norm_key(k: str) -> str:
    k = str(k).strip().lower()
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r"[^a-z0-9]+", "_", k)
    return k.strip("_")


def _flatten(obj, prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = _norm_key(k)
            p = f"{prefix}_{nk}" if prefix else nk
            out.update(_flatten(v, p))
        return out
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}_{i}" if prefix else str(i)
            out.update(_flatten(v, p))
        return out

    f = _to_float_with_unit(obj)
    if prefix and not math.isnan(f):
        out[prefix] = f
    return out


def _parse_line_to_kv(line: str) -> Dict[str, float]:
    line = line.strip()
    if not line:
        return {}

    # Preferred: JSON object per line
    try:
        obj = json.loads(line)
        if isinstance(obj, dict):
            return _flatten(obj)
    except Exception:
        pass

    # Fallback: key=value or key:value tokens separated by commas
    kv: Dict[str, float] = {}
    for part in re.split(r"\s*,\s*", line):
        part = part.strip()
        if not part:
            continue
        pair = None
        if "=" in part:
            pair = part.split("=", 1)
        elif ":" in part:
            pair = part.split(":", 1)
        if not pair:
            continue

        k = _norm_key(pair[0])
        v = _to_float_with_unit(pair[1])
        if k and not math.isnan(v):
            kv[k] = v
    return kv


def _pick(kv: Dict[str, float], exact: List[str], token_sets: List[List[str]]) -> float:
    for k in exact:
        if k in kv:
            return kv[k]
    for k, v in kv.items():
        for tokset in token_sets:
            if all(t in k for t in tokset):
                return v
    return math.nan


def extract_core(kv: Dict[str, float]) -> Dict[str, float]:
    out = {k: math.nan for k in TIER1_ALT_CORE_FIELDS}

    out["cpu_power_w"] = _pick(
        kv,
        exact=["cpu_power_w", "cpu_power"],
        token_sets=[["cpu", "power"]],
    )
    out["gpu_power_w"] = _pick(
        kv,
        exact=["gpu_power_w", "gpu_power"],
        token_sets=[["gpu", "power"]],
    )
    out["ane_power_w"] = _pick(
        kv,
        exact=["ane_power_w", "ane_power"],
        token_sets=[["ane", "power"], ["neural", "power"]],
    )

    out["cpu_temp_c"] = _pick(
        kv,
        exact=["cpu_temp_c", "cpu_temperature", "cpu_temp"],
        token_sets=[["cpu", "temp"], ["cpu", "temperature"]],
    )
    out["gpu_temp_c"] = _pick(
        kv,
        exact=["gpu_temp_c", "gpu_temperature", "gpu_temp"],
        token_sets=[["gpu", "temp"], ["gpu", "temperature"]],
    )
    out["soc_temp_c"] = _pick(
        kv,
        exact=["soc_temp_c", "soc_temperature", "soc_temp"],
        token_sets=[["soc", "temp"], ["soc", "temperature"], ["system", "temp"]],
    )

    out["cpu_avg_freq_mhz"] = _pick(
        kv,
        exact=["cpu_avg_freq_mhz", "cpu_frequency", "cpu_freq_mhz"],
        token_sets=[["cpu", "freq"], ["cpu", "frequency"]],
    )
    out["gpu_avg_freq_mhz"] = _pick(
        kv,
        exact=["gpu_avg_freq_mhz", "gpu_frequency", "gpu_freq_mhz"],
        token_sets=[["gpu", "freq"], ["gpu", "frequency"]],
    )

    out["cpu_usage_pct"] = _pick(
        kv,
        exact=["cpu_usage_pct", "cpu_usage", "cpu_percent", "cpu_pct"],
        token_sets=[["cpu", "usage"], ["cpu", "percent"], ["cpu", "pct"]],
    )
    out["gpu_usage_pct"] = _pick(
        kv,
        exact=["gpu_usage_pct", "gpu_usage", "gpu_percent", "gpu_pct"],
        token_sets=[["gpu", "usage"], ["gpu", "percent"], ["gpu", "pct"]],
    )

    out["cpu_residency_active_pct"] = _pick(
        kv,
        exact=["cpu_residency_active_pct"],
        token_sets=[["cpu", "active", "residency"], ["cpu", "residency", "active"]],
    )
    out["gpu_residency_active_pct"] = _pick(
        kv,
        exact=["gpu_residency_active_pct"],
        token_sets=[["gpu", "active", "residency"], ["gpu", "residency", "active"]],
    )

    out["fan_rpm"] = _pick(
        kv,
        exact=["fan_rpm", "fan_speed_rpm"],
        token_sets=[["fan", "rpm"], ["fan", "speed"]],
    )

    return out


def _start_macmon_process(macmon_bin: str) -> Tuple[subprocess.Popen, List[str]]:
    tried = []
    candidates = [
        [macmon_bin, "pipe"],
        [macmon_bin, "--pipe"],
    ]
    for cmd in candidates:
        tried.append(" ".join(cmd))
        try:
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            return p, tried
        except FileNotFoundError:
            continue
        except Exception:
            continue
    raise RuntimeError(
        f"Unable to start macmon. Tried: {tried}. "
        "Install macmon and ensure it is in PATH."
    )


def _reader_thread(proc: subprocess.Popen, state: dict):
    try:
        for line in iter(proc.stdout.readline, ""):
            kv = _parse_line_to_kv(line)
            if kv:
                with state["lock"]:
                    state["last_kv"] = kv
                    state["seen"] = True
    except Exception as e:
        with state["lock"]:
            state["reader_error"] = str(e)


def collect_samples_to_jsonl(
    out_jsonl: str,
    hz: int,
    duration_s: int,
    macmon_bin: str = "macmon",
    startup_timeout_s: float = 10.0,
):
    dt = 1.0 / hz
    samples_target = hz * duration_s

    proc, tried = _start_macmon_process(macmon_bin)

    state = {
        "last_kv": {},
        "seen": False,
        "reader_error": None,
        "lock": threading.Lock(),
    }
    th = threading.Thread(target=_reader_thread, args=(proc, state), daemon=True)
    th.start()

    # Wait for first parsed sample from macmon stream.
    t_wait = time.time()
    while time.time() - t_wait < startup_timeout_s:
        if proc.poll() is not None:
            break
        with state["lock"]:
            if state["seen"]:
                break
        time.sleep(0.05)

    with state["lock"]:
        seen = state["seen"]

    if not seen:
        stderr = ""
        try:
            if proc.poll() is None:
                proc.terminate()
            _, err = proc.communicate(timeout=2)
            stderr = (err or "").strip()
        except Exception:
            pass
        raise RuntimeError(
            "macmon started but no parseable telemetry was observed. "
            f"Tried commands: {tried}. stderr={stderr[:500]}"
        )

    out_path = Path(out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    non_empty = 0
    with out_path.open("w") as f:
        for i in range(samples_target):
            ts = time.time()
            with state["lock"]:
                snap = dict(state["last_kv"]) if state["last_kv"] else {}
            if snap:
                non_empty += 1
            row = {
                "idx": i,
                "ts_unix_s": ts,
                "t_rel_s": ts - t0,
                "metrics": snap,
            }
            f.write(json.dumps(row) + "\n")
            elapsed = time.time() - ts
            time.sleep(max(0.0, dt - elapsed))

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    if non_empty == 0:
        raise RuntimeError("macmon stream produced no usable samples.")


def convert_powermetrics_raw_to_jsonl(
    raw_txt: str,
    out_jsonl: str,
    hz: int,
    duration_s: int,
):
    """
    Fallback bridge for hosts where `macmon pipe` cannot subscribe.
    Re-encodes parsed powermetrics samples into the same JSONL shape used by
    the macmon collector so the downstream tier1_alt parser remains unchanged.
    """
    from .powermetrics_parse_full import split_samples, extract_kv

    samples_target = hz * duration_s
    text = Path(raw_txt).read_text(errors="ignore")
    blocks = split_samples(text)
    blocks = blocks[:samples_target] + [""] * max(0, samples_target - len(blocks))

    out_path = Path(out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    with out_path.open("w") as f:
        for i, b in enumerate(blocks):
            kv = extract_kv(b) if b else {}
            row = {
                "idx": i,
                "ts_unix_s": t0 + (i / float(hz)),
                "t_rel_s": i / float(hz),
                "metrics": kv,
            }
            f.write(json.dumps(row) + "\n")


def _read_jsonl_records(raw_jsonl: str) -> List[dict]:
    recs: List[dict] = []
    with open(raw_jsonl, "r", errors="ignore") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
            except Exception:
                continue
            if isinstance(obj, dict):
                recs.append(obj)
    return recs


def build_global_schema(raw_jsonl: str, out_schema_json: str, max_keys: int = 300) -> List[str]:
    recs = _read_jsonl_records(raw_jsonl)
    freq: Dict[str, int] = {}
    for r in recs[:2000]:
        kv = r.get("metrics", {})
        if not isinstance(kv, dict):
            continue
        for k, v in kv.items():
            try:
                fv = float(v)
            except Exception:
                continue
            if not math.isnan(fv):
                freq[k] = freq.get(k, 0) + 1

    keys = sorted(freq.keys(), key=lambda x: (-freq[x], x))[:max_keys]
    json.dump({"full_keys": keys, "max_full_keys": max_keys}, open(out_schema_json, "w"), indent=2)
    return keys


def load_schema(schema_json: str) -> List[str]:
    return json.load(open(schema_json))["full_keys"]


def parse_with_schema(
    raw_jsonl: str,
    out_core_csv: str,
    out_full_csv: str,
    schema_json: str,
    samples_target: int,
):
    recs = _read_jsonl_records(raw_jsonl)
    recs = recs[:samples_target] + [{"metrics": {}}] * max(0, samples_target - len(recs))

    keys = load_schema(schema_json)

    with open(out_core_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["idx"] + TIER1_ALT_CORE_FIELDS)
        w.writeheader()
        for i, r in enumerate(recs):
            kv = r.get("metrics", {}) if isinstance(r, dict) else {}
            core = extract_core(kv if isinstance(kv, dict) else {})
            w.writerow({"idx": i, **core})

    with open(out_full_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["idx"] + keys)
        w.writeheader()
        for i, r in enumerate(recs):
            kv = r.get("metrics", {}) if isinstance(r, dict) else {}
            kv = kv if isinstance(kv, dict) else {}
            row = {k: kv.get(k, math.nan) for k in keys}
            w.writerow({"idx": i, **row})
