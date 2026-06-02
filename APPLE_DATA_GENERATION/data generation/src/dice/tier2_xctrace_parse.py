import csv
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from .cfg import TIER2_CORE_FIELDS, TIER2_FULL_FIELDS, TIER2_LEGACY_CORE_FIELDS

_NUM_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*([A-Za-z%/_]+)?")
_TAG_PAIR_RE = re.compile(r"<([A-Za-z0-9_.:-]+)[^>]*>\s*([^<]+?)\s*</\1>")
_ATTR_PAIR_RE = re.compile(r'([A-Za-z0-9_.:-]+)\s*=\s*"([^"]+)"')
_DICT_PAIR_RE = re.compile(r"<key>([^<]+)</key>\s*<(?:real|integer|string)>([^<]+)</(?:real|integer|string)>")
_LINE_KV_RE = re.compile(r"^\s*([^:=]+?)\s*[:=]\s*(.+?)\s*$")

_BUCKET_NS = 200_000_000


def to_float_with_unit(s: str) -> float:
    if s is None:
        return math.nan
    m = _NUM_RE.search(str(s))
    if not m:
        return math.nan

    val = float(m.group(1))
    unit = (m.group(2) or "").lower()

    if unit == "mw":
        return val / 1000.0

    if unit == "hz":
        return val / 1_000_000.0
    if unit == "khz":
        return val / 1000.0
    if unit == "ghz":
        return val * 1000.0

    if unit in ("s", "sec", "secs", "second", "seconds"):
        return val * 1000.0
    if unit in ("us", "usec"):
        return val / 1000.0
    if unit in ("ns",):
        return val / 1_000_000.0

    if unit in ("kb", "kib"):
        return val * 1024.0
    if unit in ("mb", "mib"):
        return val * 1024.0 * 1024.0
    if unit in ("gb", "gib"):
        return val * 1024.0 * 1024.0 * 1024.0
    if unit in ("tb", "tib"):
        return val * 1024.0 * 1024.0 * 1024.0 * 1024.0

    return val


def norm_key(k: str) -> str:
    k = k.strip().lower()
    k = k.split(":")[-1]
    k = re.sub(r"\(.*?\)", "", k)
    k = re.sub(r"[^a-z0-9]+", "_", k)
    return k.strip("_")


def _strip_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _to_int_or_none(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _to_float_or_none(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    text = str(text).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_current_time_profile_export(raw_txt: str) -> bool:
    sample = Path(raw_txt).read_text(errors="ignore")[:65536]
    return "schema name=\"time-profile\"" in sample and "<sample-time" in sample


def split_samples(text: str) -> List[str]:
    for pat in (r"(?s)<row\b.*?</row>", r"(?s)<sample\b.*?</sample>", r"(?s)<event\b.*?</event>"):
        rows = re.findall(pat, text)
        if rows:
            return rows

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return [b for b in blocks if _NUM_RE.search(b)]


def extract_kv(block: str) -> Dict[str, float]:
    kv: Dict[str, float] = {}

    for k, v in _DICT_PAIR_RE.findall(block):
        nk = norm_key(k)
        fv = to_float_with_unit(v)
        if nk and (not math.isnan(fv)):
            kv[nk] = fv

    for tag, text_val in _TAG_PAIR_RE.findall(block):
        nk = norm_key(tag)
        fv = to_float_with_unit(text_val)
        if nk and (not math.isnan(fv)):
            kv[nk] = fv

    for k, v in _ATTR_PAIR_RE.findall(block):
        nk = norm_key(k)
        fv = to_float_with_unit(v)
        if nk and (not math.isnan(fv)):
            kv[nk] = fv

    for line in block.splitlines():
        m = _LINE_KV_RE.match(line)
        if not m:
            continue
        nk = norm_key(m.group(1))
        fv = to_float_with_unit(m.group(2))
        if nk and (not math.isnan(fv)):
            kv[nk] = fv

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


def extract_legacy_core(kv: Dict[str, float]) -> Dict[str, float]:
    out = {k: math.nan for k in TIER2_LEGACY_CORE_FIELDS}

    out["cpu_usage_pct"] = _pick(
        kv,
        exact=["cpu_usage_pct", "cpu_usage", "cpu_percent", "cpu_pct"],
        token_sets=[["cpu", "usage"], ["cpu", "percent"], ["cpu", "pct"]],
    )
    out["cpu_time_ms"] = _pick(
        kv,
        exact=["cpu_time_ms", "cpu_time"],
        token_sets=[["cpu", "time"]],
    )
    out["thread_count"] = _pick(
        kv,
        exact=["thread_count", "threads", "num_threads"],
        token_sets=[["thread", "count"], ["threads"]],
    )
    out["wakeups_per_s"] = _pick(
        kv,
        exact=["wakeups_per_s", "thread_wakeups_per_s"],
        token_sets=[["wake", "per", "s"], ["wakeups"]],
    )
    out["context_switches_per_s"] = _pick(
        kv,
        exact=["context_switches_per_s"],
        token_sets=[["context", "switch", "per", "s"], ["context", "switch"]],
    )
    out["page_faults_per_s"] = _pick(
        kv,
        exact=["page_faults_per_s", "faults_per_s"],
        token_sets=[["page", "fault"], ["fault", "per", "s"], ["fault"]],
    )
    out["phys_mem_bytes"] = _pick(
        kv,
        exact=["phys_mem_bytes", "physical_memory", "resident_size_bytes"],
        token_sets=[["phys", "mem"], ["physical", "mem"], ["resident", "size"]],
    )
    out["virt_mem_bytes"] = _pick(
        kv,
        exact=["virt_mem_bytes", "virtual_memory", "virtual_size_bytes"],
        token_sets=[["virt", "mem"], ["virtual", "mem"], ["virtual", "size"]],
    )
    out["io_read_Bps"] = _pick(
        kv,
        exact=["io_read_bps", "disk_read_bps", "bytes_read_per_s"],
        token_sets=[["read", "bps"], ["io", "read"], ["disk", "read"], ["bytes", "read"]],
    )
    out["io_write_Bps"] = _pick(
        kv,
        exact=["io_write_bps", "disk_write_bps", "bytes_written_per_s"],
        token_sets=[["write", "bps"], ["io", "write"], ["disk", "write"], ["bytes", "written"]],
    )
    out["energy_impact"] = _pick(
        kv,
        exact=["energy_impact"],
        token_sets=[["energy", "impact"], ["energy"]],
    )
    return out


def _new_bucket() -> Dict[str, object]:
    return {
        "samples_per_bucket": 0,
        "unique_process_ids": set(),
        "unique_thread_ids": set(),
        "core_sum": 0.0,
        "core_count": 0,
        "max_core_id": None,
        "total_weight_ns": 0.0,
        "weight_count": 0,
        "running_count": 0,
        "first_sample_time_ns": None,
        "last_sample_time_ns": None,
        "sentinel_count": 0,
    }


def _resolve_process_id(elem: ET.Element, process_ids: Dict[str, int]) -> Optional[int]:
    ref = elem.get("ref")
    if ref:
        return process_ids.get(ref)

    pid = None
    for child in elem:
        if _strip_tag(child.tag) == "pid":
            pid = _to_int_or_none(child.text)
            break
    if pid is None:
        pid = _to_int_or_none(elem.text)

    elem_id = elem.get("id")
    if elem_id and pid is not None:
        process_ids[elem_id] = pid
    return pid


def _resolve_thread_id(
    elem: ET.Element,
    thread_ids: Dict[str, int],
    process_ids: Dict[str, int],
) -> tuple[Optional[int], Optional[int]]:
    ref = elem.get("ref")
    if ref:
        return thread_ids.get(ref), None

    tid = None
    process_id = None
    for child in elem:
        child_tag = _strip_tag(child.tag)
        if child_tag == "tid":
            tid = _to_int_or_none(child.text)
        elif child_tag == "process":
            process_id = _resolve_process_id(child, process_ids)

    if tid is None:
        tid = _to_int_or_none(elem.text)

    elem_id = elem.get("id")
    if elem_id and tid is not None:
        thread_ids[elem_id] = tid
    return tid, process_id


def _resolve_int_ref(elem: ET.Element, cache: Dict[str, int]) -> Optional[int]:
    ref = elem.get("ref")
    if ref:
        return cache.get(ref)
    value = _to_int_or_none(elem.text)
    elem_id = elem.get("id")
    if elem_id and value is not None:
        cache[elem_id] = value
    return value


def _resolve_float_ref(elem: ET.Element, cache: Dict[str, float]) -> Optional[float]:
    ref = elem.get("ref")
    if ref:
        return cache.get(ref)
    value = _to_float_or_none(elem.text)
    elem_id = elem.get("id")
    if elem_id and value is not None:
        cache[elem_id] = value
    return value


def _resolve_text_ref(elem: ET.Element, cache: Dict[str, str]) -> Optional[str]:
    ref = elem.get("ref")
    if ref:
        return cache.get(ref)
    value = (elem.text or "").strip() or None
    elem_id = elem.get("id")
    if elem_id and value is not None:
        cache[elem_id] = value
    return value


def _bucket_to_full_row(bucket: Dict[str, object]) -> Dict[str, float]:
    samples = int(bucket["samples_per_bucket"])
    if samples <= 0:
        return {k: math.nan for k in TIER2_FULL_FIELDS}

    first_time = bucket["first_sample_time_ns"]
    last_time = bucket["last_sample_time_ns"]
    sample_span = math.nan
    if first_time is not None and last_time is not None:
        sample_span = float(max(last_time - first_time, 0))

    core_count = int(bucket["core_count"])
    weight_count = int(bucket["weight_count"])
    running_count = int(bucket["running_count"])

    return {
        "avg_core_id": (bucket["core_sum"] / core_count) if core_count > 0 else math.nan,
        "avg_weight_ns": (bucket["total_weight_ns"] / weight_count) if weight_count > 0 else math.nan,
        "first_sample_time_ns": float(first_time) if first_time is not None else math.nan,
        "last_sample_time_ns": float(last_time) if last_time is not None else math.nan,
        "max_core_id": float(bucket["max_core_id"]) if bucket["max_core_id"] is not None else math.nan,
        "running_count": float(running_count),
        "running_fraction": float(running_count / samples),
        "sample_span_ns": sample_span,
        "samples_per_bucket": float(samples),
        "sentinel_count": float(bucket["sentinel_count"]),
        "total_weight_ns": float(bucket["total_weight_ns"]),
        "unique_process_count": float(len(bucket["unique_process_ids"])),
        "unique_thread_count": float(len(bucket["unique_thread_ids"])),
    }


def _current_core_from_full_row(row: Dict[str, float]) -> Dict[str, float]:
    return {k: row.get(k, math.nan) for k in TIER2_CORE_FIELDS}


def _parse_current_time_profile_buckets(raw_txt: str, samples_target: int) -> List[Dict[str, float]]:
    sample_time_ids: Dict[str, int] = {}
    thread_ids: Dict[str, int] = {}
    process_ids: Dict[str, int] = {}
    core_ids: Dict[str, int] = {}
    state_ids: Dict[str, str] = {}
    weight_ids: Dict[str, float] = {}

    buckets: List[Dict[str, object]] = []
    first_time_ns: Optional[int] = None

    for _, elem in ET.iterparse(raw_txt, events=("end",)):
        if _strip_tag(elem.tag) != "row":
            continue

        sample_time_ns = None
        thread_id = None
        process_id = None
        core_id = None
        state = None
        weight_ns = None

        for child in elem:
            tag = _strip_tag(child.tag)
            if tag == "sample-time":
                sample_time_ns = _resolve_int_ref(child, sample_time_ids)
            elif tag == "thread":
                resolved_thread_id, nested_process_id = _resolve_thread_id(child, thread_ids, process_ids)
                if resolved_thread_id is not None:
                    thread_id = resolved_thread_id
                if nested_process_id is not None:
                    process_id = nested_process_id
            elif tag == "process":
                resolved_process_id = _resolve_process_id(child, process_ids)
                if resolved_process_id is not None:
                    process_id = resolved_process_id
            elif tag == "core":
                core_id = _resolve_int_ref(child, core_ids)
            elif tag in ("thread-state", "state"):
                state = _resolve_text_ref(child, state_ids)
            elif tag == "weight":
                weight_ns = _resolve_float_ref(child, weight_ids)

        elem.clear()

        if sample_time_ns is None:
            continue

        if first_time_ns is None:
            first_time_ns = sample_time_ns
        bucket_idx = max(0, int((sample_time_ns - first_time_ns) // _BUCKET_NS))
        if bucket_idx >= samples_target:
            continue

        while len(buckets) <= bucket_idx:
            buckets.append(_new_bucket())
        bucket = buckets[bucket_idx]
        bucket["samples_per_bucket"] += 1
        if process_id is not None:
            bucket["unique_process_ids"].add(process_id)
        if thread_id is not None:
            bucket["unique_thread_ids"].add(thread_id)
        if core_id is not None:
            bucket["core_sum"] += float(core_id)
            bucket["core_count"] += 1
            current_max = bucket["max_core_id"]
            bucket["max_core_id"] = core_id if current_max is None else max(int(current_max), core_id)
        if weight_ns is not None:
            bucket["total_weight_ns"] += float(weight_ns)
            bucket["weight_count"] += 1
        if state is not None and state.lower() == "running":
            bucket["running_count"] += 1
        if bucket["first_sample_time_ns"] is None:
            bucket["first_sample_time_ns"] = sample_time_ns
        bucket["last_sample_time_ns"] = sample_time_ns

    rows = [_bucket_to_full_row(bucket) for bucket in buckets]
    if len(rows) < samples_target:
        rows.extend({k: math.nan for k in TIER2_FULL_FIELDS} for _ in range(samples_target - len(rows)))
    return rows[:samples_target]


def build_global_schema(raw_txt: str, out_schema_json: str, max_keys: int = 300) -> List[str]:
    if _is_current_time_profile_export(raw_txt):
        keys = list(TIER2_FULL_FIELDS)
        json.dump({"full_keys": keys, "max_full_keys": len(keys)}, open(out_schema_json, "w"), indent=2)
        return keys

    text = open(raw_txt, "r", errors="ignore").read()
    blocks = split_samples(text)
    freq: Dict[str, int] = {}
    for b in blocks[:500]:
        kv = extract_kv(b)
        for k, v in kv.items():
            if not math.isnan(v):
                freq[k] = freq.get(k, 0) + 1
    keys = sorted(freq.keys(), key=lambda x: (-freq[x], x))[:max_keys]
    json.dump({"full_keys": keys, "max_full_keys": max_keys}, open(out_schema_json, "w"), indent=2)
    return keys


def load_schema(schema_json: str) -> List[str]:
    return json.load(open(schema_json))["full_keys"]


def parse_with_schema(raw_txt: str, out_core_csv: str, out_full_csv: str, schema_json: str, samples_target: int):
    if _is_current_time_profile_export(raw_txt):
        rows = _parse_current_time_profile_buckets(raw_txt, samples_target=samples_target)
        with open(out_core_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["idx"] + TIER2_CORE_FIELDS)
            writer.writeheader()
            for idx, row in enumerate(rows):
                writer.writerow({"idx": idx, **_current_core_from_full_row(row)})

        keys = load_schema(schema_json)
        with open(out_full_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["idx"] + keys)
            writer.writeheader()
            for idx, row in enumerate(rows):
                writer.writerow({"idx": idx, **{k: row.get(k, math.nan) for k in keys}})
        return

    text = open(raw_txt, "r", errors="ignore").read()
    blocks = split_samples(text)
    blocks = blocks[:samples_target] + [""] * max(0, samples_target - len(blocks))
    keys = load_schema(schema_json)

    with open(out_core_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["idx"] + TIER2_LEGACY_CORE_FIELDS)
        writer.writeheader()
        for idx, block in enumerate(blocks):
            kv = extract_kv(block)
            writer.writerow({"idx": idx, **extract_legacy_core(kv)})

    with open(out_full_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["idx"] + keys)
        writer.writeheader()
        for idx, block in enumerate(blocks):
            kv = extract_kv(block)
            writer.writerow({"idx": idx, **{k: kv.get(k, math.nan) for k in keys}})
