import os, time, threading, random, zlib, sys, subprocess
from pathlib import Path
import numpy as np
import urllib.request
from .cfg import SEED, parse_workload_crash_stressor

def _seed_all():
    random.seed(SEED)
    np.random.seed(SEED)

def workload_browser(stop_evt: threading.Event):
    _seed_all()
    urls = ["https://example.com","https://www.iana.org/domains/reserved","https://www.wikipedia.org"]
    i = 0
    while not stop_evt.is_set():
        try:
            urllib.request.urlopen(urls[i % len(urls)], timeout=5).read(200_000)
        except Exception:
            pass
        i += 1
        time.sleep(0.05)

def workload_video_sw(stop_evt: threading.Event):
    _seed_all()
    H, W = 720, 1280
    frame = (np.random.rand(H, W, 3) * 255).astype(np.uint8)
    while not stop_evt.is_set():
        gray = (0.299 * frame[:,:,0] + 0.587 * frame[:,:,1] + 0.114 * frame[:,:,2]).astype(np.uint8)
        small = gray[::2, ::2]
        comp = zlib.compress(small.tobytes(), level=1)
        _ = zlib.decompress(comp)
        frame = (frame + 1) % 255
        time.sleep(0.005)

def workload_ai_numpy_torch(stop_evt: threading.Event, phase_s: float = 5.0):
    _seed_all()
    import torch
    torch.manual_seed(SEED)
    mps_ok = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    device = torch.device("mps" if mps_ok else "cpu")

    N_NUMPY = 1024
    N_TORCH = 2048
    a_np = np.random.randn(N_NUMPY, N_NUMPY).astype(np.float32)
    b_np = np.random.randn(N_NUMPY, N_NUMPY).astype(np.float32)
    a_t = torch.randn((N_TORCH, N_TORCH), device=device, dtype=torch.float32)
    b_t = torch.randn((N_TORCH, N_TORCH), device=device, dtype=torch.float32)

    def torch_phase(end_t):
        while time.time() < end_t and (not stop_evt.is_set()):
            c = a_t @ b_t
            s = c.sum()
            if device.type == "cpu":
                _ = float(s.item())

    def numpy_phase(end_t):
        while time.time() < end_t and (not stop_evt.is_set()):
            _ = a_np @ b_np

    while not stop_evt.is_set():
        t0 = time.time()
        torch_phase(t0 + phase_s)
        if stop_evt.is_set(): break
        t1 = time.time()
        numpy_phase(t1 + phase_s)

def workload_stats_streaming(stop_evt: threading.Event):
    _seed_all()
    x = np.random.rand(100_000_000).astype(np.float32)
    while not stop_evt.is_set():
        _ = float(x.sum()); _ = float(x.mean())
        x[::16] += 1.0


def workload_crash_app(stop_evt: threading.Event):
    _seed_all()
    while not stop_evt.is_set():
        time.sleep(0.2)


def _crash_harness_path() -> Path:
    return Path(__file__).resolve().with_name("crash_harness.py")


def _workload_crash_wrapper_path() -> Path:
    return Path(__file__).resolve().with_name("workload_crash_wrapper.py")


def _run_crash_harness_subprocess(scenario: str, stop_evt: threading.Event):
    script = _crash_harness_path()
    cmd = [sys.executable, str(script), "--scenario", str(scenario)]
    proc = subprocess.Popen(cmd)
    try:
        while not stop_evt.is_set():
            rc = proc.poll()
            if rc is not None:
                # Abort scenarios are expected to exit via SIGABRT (-6 on macOS).
                return
            time.sleep(0.25)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3.0)


def _wrapped_crash_mode_for_workload(workload: str) -> tuple[str, str] | None:
    wrap_workload = str(os.environ.get("DICE_MATCHED_WORKLOAD_CRASH_WORKLOAD", "")).strip().upper()
    wrap_stressor = str(os.environ.get("DICE_MATCHED_WORKLOAD_CRASH_STRESSOR", "")).strip().upper()
    wrap_mode = str(os.environ.get("DICE_MATCHED_WORKLOAD_CRASH_MODE", "")).strip().upper()
    if wrap_workload != str(workload).strip().upper():
        return None
    if not wrap_stressor or wrap_mode not in {"CONTROL", "ABORT"}:
        return None
    parsed = parse_workload_crash_stressor(f"{wrap_stressor}_{wrap_mode}")
    if parsed is None:
        return None
    return parsed


def _run_workload_crash_wrapper_subprocess(workload: str, stressor: str, mode: str, stop_evt: threading.Event):
    script = _workload_crash_wrapper_path()
    cmd = [
        sys.executable,
        str(script),
        "--workload",
        str(workload),
        "--stressor",
        str(stressor),
        "--mode",
        str(mode).lower(),
    ]
    if str(os.environ.get("DICE_MATCHED_WORKLOAD_CRASH_GUI", "")).strip().lower() in {"1", "true", "yes", "on"}:
        cmd.append("--gui")
    if str(os.environ.get("DICE_MATCHED_WORKLOAD_CRASH_DRY_RUN", "")).strip().lower() in {"1", "true", "yes", "on"}:
        cmd.append("--dry_run")
    proc = subprocess.Popen(cmd)
    try:
        while not stop_evt.is_set():
            rc = proc.poll()
            if rc is not None:
                stop_evt.set()
                return
            time.sleep(0.25)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3.0)


def run_base_workload(workload: str, stop_evt: threading.Event):
    if workload == "BROWSER": return workload_browser(stop_evt)
    if workload == "VIDEO_SW": return workload_video_sw(stop_evt)
    if workload == "PY_AI": return workload_ai_numpy_torch(stop_evt, phase_s=5.0)
    if workload == "PY_STATS": return workload_stats_streaming(stop_evt)
    if workload == "CRASH_APP": return workload_crash_app(stop_evt)
    raise ValueError(f"Unknown workload: {workload}")


def run_workload(workload: str, stop_evt: threading.Event):
    wrapped = _wrapped_crash_mode_for_workload(workload)
    if wrapped is not None:
        base_stressor, mode = wrapped
        return _run_workload_crash_wrapper_subprocess(workload, base_stressor, mode, stop_evt)
    return run_base_workload(workload, stop_evt)


def run_base_stressor(stressor: str, stop_evt: threading.Event):
    _seed_all()
    if stressor == "NOMINAL":
        while not stop_evt.is_set(): time.sleep(0.2)
        return

    if stressor in {"MEM_RAMP_CONTROL", "MEM_RAMP_ABORT", "CPU_RAMP_CONTROL", "CPU_RAMP_ABORT"}:
        return _run_crash_harness_subprocess(stressor, stop_evt)

    if stressor == "MEMBW":
        arr = np.zeros((200_000_000,), dtype=np.uint8)
        i = 0
        while not stop_evt.is_set():
            arr[i:i+10_000_000] = (arr[i:i+10_000_000] + 1) % 255
            i = (i + 10_000_000) % (len(arr) - 10_000_000)

    elif stressor == "CACHE":
        arr = np.random.randn(20_000_000).astype(np.float32)
        while not stop_evt.is_set():
            _ = float(arr[::64].sum())

    elif stressor == "TLB":
        arr = np.zeros((200_000_000,), dtype=np.uint8)
        pages = [i for i in range(0, len(arr), 4096)]
        while not stop_evt.is_set():
            for _ in range(20000):
                idx = random.choice(pages)
                arr[idx] = (arr[idx] + 1) % 255

    elif stressor == "BRANCH":
        x = 0
        while not stop_evt.is_set():
            r = random.getrandbits(32)
            if r & 1: x += 3
            elif r & 2: x -= 2
            elif r & 4: x ^= r
            else: x += 1

    elif stressor == "ATOMIC":
        lock = threading.Lock()
        counter = 0
        def worker():
            nonlocal counter
            while not stop_evt.is_set():
                with lock:
                    counter += 1
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(2, os.cpu_count() // 2))]
        for th in threads: th.start()
        while not stop_evt.is_set(): time.sleep(0.05)

    else:
        raise ValueError(f"Unknown stressor: {stressor}")


def run_stressor(stressor: str, stop_evt: threading.Event):
    parsed = parse_workload_crash_stressor(stressor)
    if parsed is not None:
        while not stop_evt.is_set():
            time.sleep(0.2)
        return
    return run_base_stressor(stressor, stop_evt)
