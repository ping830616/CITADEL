from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _split_requirement(requirement: str) -> tuple[str, str]:
    name, version = requirement.split("==", 1)
    return name.strip(), version.strip()


def _pyproject_pinned_dependencies() -> dict[str, str]:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    deps = dict(_split_requirement(req) for req in project["dependencies"])
    for group in ("dev", "notebook"):
        deps.update(_split_requirement(req) for req in project["optional-dependencies"][group])
    return deps


def _requirements_pinned_dependencies() -> dict[str, str]:
    deps: dict[str, str] = {}
    for line in (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = _split_requirement(line)
        deps[name] = version
    return deps


def _environment_pinned_dependencies() -> dict[str, str]:
    deps: dict[str, str] = {}
    in_dependencies = False
    for line in (REPO_ROOT / "environment.yml").read_text(encoding="utf-8").splitlines():
        if line.strip() == "dependencies:":
            in_dependencies = True
            continue
        if not in_dependencies:
            continue
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        package = stripped[2:].strip()
        if "=" not in package:
            continue
        name, version = package.split("=", 1)
        deps[name.strip()] = version.strip()
    deps.pop("python", None)
    return deps


def test_environment_files_pin_same_direct_dependencies() -> None:
    pyproject_deps = _pyproject_pinned_dependencies()
    requirements_deps = _requirements_pinned_dependencies()
    environment_deps = _environment_pinned_dependencies()

    assert requirements_deps == pyproject_deps
    assert environment_deps == pyproject_deps
