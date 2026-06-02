import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def _log_line(log_path: Optional[Path], message: str) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        fh.write(message.rstrip() + "\n")


def _backup_existing_output(path: Path) -> None:
    if not path.exists():
        return
    backup = path.with_name(path.name + ".bak")
    if backup.exists():
        if backup.is_dir():
            shutil.rmtree(backup)
        else:
            backup.unlink()
    path.rename(backup)


def collect_powermetrics_text(
    out_txt: Path,
    samples_target: int,
    sample_rate_ms: int = 200,
    log_path: Optional[Path] = None,
    samplers: str = "default,thermal",
) -> subprocess.CompletedProcess:
    out_txt = Path(out_txt)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    _backup_existing_output(out_txt)

    cmd = [
        "sudo",
        "-n",
        "powermetrics",
        "-i",
        str(sample_rate_ms),
        "-n",
        str(samples_target),
        "-o",
        str(out_txt),
        "-b",
        "1",
        "-a",
        "0",
        "-s",
        samplers,
        "--handle-invalid-values",
    ]
    _log_line(log_path, "[powermetrics] " + " ".join(cmd))
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def record_xctrace_time_profile(
    trace_out: Path,
    duration_s: int,
    template: str,
    log_path: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    trace_out = Path(trace_out)
    trace_out.parent.mkdir(parents=True, exist_ok=True)
    _backup_existing_output(trace_out)

    cmd = [
        "xcrun",
        "xctrace",
        "record",
        "--template",
        template,
        "--all-processes",
        "--time-limit",
        f"{duration_s}s",
        "--output",
        str(trace_out),
        "--no-prompt",
    ]
    _log_line(log_path, "[xctrace record] " + " ".join(cmd))
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def _time_profile_xpath_from_toc(toc_path: Path) -> str:
    root = ET.parse(toc_path).getroot()
    run = root.find("./run")
    if run is None:
        raise RuntimeError(f"Malformed xctrace TOC: missing run node in {toc_path}")
    data = run.find("./data")
    if data is None:
        raise RuntimeError(f"Malformed xctrace TOC: missing data node in {toc_path}")

    for idx, table in enumerate(data.findall("./table"), start=1):
        schema = (table.get("schema") or "").strip().lower()
        if schema == "time-profile":
            return f"//trace-toc[1]/run[1]/data[1]/table[{idx}]"

    for idx, table in enumerate(data.findall("./table"), start=1):
        schema = (table.get("schema") or "").strip().lower()
        if schema == "time-sample":
            return f"//trace-toc[1]/run[1]/data[1]/table[{idx}]"

    raise RuntimeError(
        "Unable to locate a time-profile table in the xctrace table of contents. "
        "Check that the selected template exports time-profile data."
    )


def export_xctrace_time_profile(
    trace_out: Path,
    raw_export: Path,
    log_path: Optional[Path] = None,
) -> None:
    trace_out = Path(trace_out)
    raw_export = Path(raw_export)
    raw_export.parent.mkdir(parents=True, exist_ok=True)
    _backup_existing_output(raw_export)

    toc_path = raw_export.with_name(raw_export.stem + "_toc.xml")
    if toc_path.exists():
        toc_path.unlink()

    toc_cmd = [
        "xcrun",
        "xctrace",
        "export",
        "--input",
        str(trace_out),
        "--toc",
        "--output",
        str(toc_path),
    ]
    _log_line(log_path, "[xctrace toc] " + " ".join(toc_cmd))
    toc_result = subprocess.run(
        toc_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if toc_result.returncode != 0:
        raise RuntimeError(
            "xctrace TOC export failed. "
            f"Output: {(toc_result.stdout or '').strip()}"
        )

    xpath = _time_profile_xpath_from_toc(toc_path)
    export_cmd = [
        "xcrun",
        "xctrace",
        "export",
        "--input",
        str(trace_out),
        "--xpath",
        xpath,
        "--output",
        str(raw_export),
    ]
    _log_line(log_path, "[xctrace export] " + " ".join(export_cmd))
    export_result = subprocess.run(
        export_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if export_result.returncode != 0:
        raise RuntimeError(
            "xctrace XML export failed. "
            f"Output: {(export_result.stdout or '').strip()}"
        )
