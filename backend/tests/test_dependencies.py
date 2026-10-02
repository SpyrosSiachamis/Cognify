"""The backend's dependencies are pinned (backend/constraints.txt), so a rebuild cannot change behaviour."""

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
HOW_TO_UPDATE = "see the header of backend/constraints.txt for how to regenerate it"


def _name(requirement: str) -> str:
    """'uvicorn[standard]' -> 'uvicorn', 'psycopg[binary]>=3' -> 'psycopg' (normalised like pip does)."""
    match = re.match(r"[A-Za-z0-9_.\-]+", requirement.strip())
    assert match, f"cannot read a package name from {requirement!r}"
    return re.sub(r"[-_.]+", "-", match.group(0)).lower()


def _lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.strip().startswith("#")]


def test_every_pin_is_an_exact_version():
    pins = _lines(BACKEND / "constraints.txt")
    assert pins, "constraints.txt has no packages"
    bad = [line for line in pins if not re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9_.+!\-]*", line)]
    assert not bad, f"not name==version: {bad}"
    names = [_name(line) for line in pins]
    assert len(names) == len(set(names)), "a package is pinned twice"


def test_every_direct_dependency_is_pinned():
    pinned = {_name(line) for line in _lines(BACKEND / "constraints.txt")}
    missing = [r for r in _lines(BACKEND / "requirements.txt") if _name(r) not in pinned]
    assert not missing, f"in requirements.txt but not pinned in constraints.txt: {missing}; {HOW_TO_UPDATE}"


def test_the_dockerfile_installs_with_the_pins():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert "pip install -r requirements.txt -c constraints.txt" in dockerfile
    assert "constraints.txt" in dockerfile.split("pip install")[0]  # copied into the image before pip runs
