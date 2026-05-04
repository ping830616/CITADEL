#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = REPO_ROOT / "data" / "external_sources.json"
MANIFEST_ROOT = REPO_ROOT / "data" / "external_manifests"


@dataclass(frozen=True)
class SourceFile:
    repo: str
    ref: str
    source_id: str
    source_path: str
    rel_path: str
    name: str
    size: int
    git_sha: str
    raw_url: str
    target_path: Path


def _load_registry(path: Path = SOURCE_REGISTRY) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        proc = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    token = proc.stdout.strip()
    return token or None


def _api_json(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CITADEL-data-prep",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _quote_path(path: str) -> str:
    return urllib.parse.quote(path, safe="/")


def _raw_url(repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{_quote_path(path)}"


def _repo_tree(repo: str, ref: str, token: str | None) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/git/trees/{_quote_path(ref)}?recursive=1"
    payload = _api_json(url, token)
    if payload.get("truncated"):
        raise RuntimeError(
            f"GitHub returned a truncated tree for {repo}@{ref}; use a narrower source path."
        )
    return payload.get("tree", [])


def _source_files(source_id: str, spec: dict[str, Any], token: str | None) -> list[SourceFile]:
    repo = spec["repo"]
    ref = spec.get("ref", "main")
    root = spec["path"].strip("/")
    target_root = REPO_ROOT / spec["target"]
    preserve_tree = bool(spec.get("preserve_tree", True))
    include_prefixes = spec.get("include_prefixes")

    files: list[SourceFile] = []
    for entry in _repo_tree(repo, ref, token):
        if entry.get("type") != "blob":
            continue
        path = str(entry.get("path", ""))
        if not path.startswith(root + "/"):
            continue
        rel = path[len(root) + 1 :]
        if include_prefixes and not any(rel.startswith(prefix) for prefix in include_prefixes):
            continue
        local_rel = rel if preserve_tree else Path(rel).name
        files.append(
            SourceFile(
                repo=repo,
                ref=ref,
                source_id=source_id,
                source_path=path,
                rel_path=rel,
                name=Path(rel).name,
                size=int(entry.get("size", 0)),
                git_sha=str(entry.get("sha", "")),
                raw_url=_raw_url(repo, ref, path),
                target_path=target_root / local_rel,
            )
        )
    return sorted(files, key=lambda f: f.rel_path)


def _split_csv_arg(value: str | None) -> set[str] | None:
    if not value:
        return None
    items = {x.strip().upper() for x in value.split(",") if x.strip()}
    return items or None


def _filter_x_octane(
    files: Iterable[SourceFile],
    setups: set[str] | None,
    scenarios: set[str] | None,
    workloads: set[str] | None,
) -> list[SourceFile]:
    selected = []
    for item in files:
        parts = Path(item.name).stem.split("_")
        if len(parts) < 3:
            continue
        setup, scenario, workload = parts[0].upper(), parts[1].upper(), parts[2].upper()
        if setups and setup not in setups:
            continue
        if scenarios and scenario not in scenarios:
            continue
        if workloads and workload not in workloads:
            continue
        selected.append(item)
    return selected


def _filter_dice_tiers(files: Iterable[SourceFile], tiers: set[str] | None) -> list[SourceFile]:
    if not tiers:
        return list(files)
    selected = []
    for item in files:
        top = item.rel_path.split("/", 1)[0].upper()
        if top in tiers:
            selected.append(item)
    return selected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_one(item: SourceFile, token: str | None, force: bool = False) -> dict[str, Any]:
    item.target_path.parent.mkdir(parents=True, exist_ok=True)
    if item.target_path.exists() and not force:
        return {
            "status": "exists",
            "sha256": _sha256(item.target_path),
            "local_size": item.target_path.stat().st_size,
        }

    headers = {"User-Agent": "CITADEL-data-prep"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(item.raw_url, headers=headers)
    tmp_path = item.target_path.with_suffix(item.target_path.suffix + ".tmp")
    with urllib.request.urlopen(req, timeout=240) as resp, tmp_path.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp_path.replace(item.target_path)
    return {
        "status": "downloaded",
        "sha256": _sha256(item.target_path),
        "local_size": item.target_path.stat().st_size,
    }


def _manifest_entry(item: SourceFile, downloaded: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "source_id": item.source_id,
        "repo": item.repo,
        "ref": item.ref,
        "source_path": item.source_path,
        "relative_path": item.rel_path,
        "name": item.name,
        "size": item.size,
        "git_sha": item.git_sha,
        "raw_url": item.raw_url,
        "target_path": str(item.target_path.relative_to(REPO_ROOT)),
    }
    if downloaded:
        entry.update(downloaded)
    return entry


def _write_manifest(source_id: str, spec: dict[str, Any], files: list[SourceFile], entries: list[dict[str, Any]]) -> Path:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    path = MANIFEST_ROOT / f"{source_id}.json"
    payload = {
        "source_id": source_id,
        "repo": spec["repo"],
        "ref": spec.get("ref", "main"),
        "source_path": spec["path"],
        "target": spec["target"],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_count": len(files),
        "total_bytes": sum(f.size for f in files),
        "files": entries,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _select_sources(registry: dict[str, dict[str, Any]], requested: str) -> list[str]:
    if requested == "all":
        return list(registry.keys())
    if requested not in registry:
        raise KeyError(f"Unknown source {requested!r}. Available: {', '.join(registry)}")
    return [requested]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch or manifest external CITADEL telemetry sources from GitHub."
    )
    parser.add_argument("--source", default="all", help="Source id from data/external_sources.json, or 'all'.")
    parser.add_argument("--download", action="store_true", help="Download selected files. Without this flag, only a manifest is written.")
    parser.add_argument("--force", action="store_true", help="Re-download files that already exist.")
    parser.add_argument("--setups", default=None, help="X-OCTANE filter, e.g. DDR4,DDR5.")
    parser.add_argument("--scenarios", default=None, help="X-OCTANE filter, e.g. benign,DROOP,RH,SPECTRE.")
    parser.add_argument("--workloads", default=None, help="X-OCTANE filter, e.g. dft,mm,tr.")
    parser.add_argument("--apple-tiers", default=None, help="Apple filter, e.g. tier0,tier1_alt,tier2.")
    parser.add_argument("--max-files", type=int, default=None, help="Optional cap for smoke downloads.")
    args = parser.parse_args()

    registry = _load_registry()
    token = _github_token()
    requested = _select_sources(registry, args.source)

    setups = _split_csv_arg(args.setups)
    scenarios = _split_csv_arg(args.scenarios)
    workloads = _split_csv_arg(args.workloads)
    apple_tiers = _split_csv_arg(args.apple_tiers)

    for source_id in requested:
        spec = registry[source_id]
        files = _source_files(source_id, spec, token)
        if source_id == "x_octane_ddr":
            files = _filter_x_octane(files, setups=setups, scenarios=scenarios, workloads=workloads)
        if source_id == "dice_m2pro_tiers":
            files = _filter_dice_tiers(files, tiers=apple_tiers)
        if args.max_files is not None:
            files = files[: args.max_files]

        entries = []
        for idx, item in enumerate(files, start=1):
            downloaded = None
            if args.download:
                downloaded = _download_one(item, token=token, force=args.force)
                print(
                    f"[{source_id} {idx:03d}/{len(files):03d}] "
                    f"{downloaded['status']}: {item.target_path.relative_to(REPO_ROOT)}",
                    flush=True,
                )
            entries.append(_manifest_entry(item, downloaded=downloaded))

        manifest = _write_manifest(source_id, spec, files, entries)
        print(
            f"{source_id}: {len(files)} files, {sum(f.size for f in files)} bytes, "
            f"manifest={manifest.relative_to(REPO_ROOT)}",
            flush=True,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise
