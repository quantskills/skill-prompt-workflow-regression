"""Exercise the real environment gate with controlled installed metadata."""
from importlib import metadata
from pathlib import Path
import runpy
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL = dict(line.split("==") for line in (ROOT / "requirements.txt").read_text().splitlines()
             if "==" in line and not line.startswith("#"))
EVO = {"numpy": "1.26.4", "pandas": "2.3.3", "scipy": "1.17.1",
       "pytest": "9.1.1", "PyYAML": "6.0.3"}

@pytest.mark.parametrize("profile", [LOCAL, EVO])
def test_supported_complete_profile(monkeypatch, profile):
    monkeypatch.setattr(metadata, "version", lambda name: profile[name])
    assert runpy.run_path(str(ROOT / "scripts/guide.py"))["check"]() == 0

@pytest.mark.parametrize("change", ["missing", "unknown", "mixed", "old_python"])
def test_unsupported_environment_stays_blocked(monkeypatch, change):
    versions = dict(LOCAL)
    if change == "unknown":
        versions["numpy"] = "99.0.0"
    elif change == "mixed":
        versions["numpy"] = EVO["numpy"]
    elif change == "old_python":
        monkeypatch.setattr(sys, "version_info", (3, 10, 0))
    def installed(name):
        if change == "missing" and name == "numpy":
            raise metadata.PackageNotFoundError(name)
        return versions[name]
    monkeypatch.setattr(metadata, "version", installed)
    assert runpy.run_path(str(ROOT / "scripts/guide.py"))["check"]() == 1
