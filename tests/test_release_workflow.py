"""The release workflow stays wired to CI and to the manifest version."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github/workflows"
MANIFEST = "custom_components/midea_water_softener/manifest.json"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_release_waits_for_the_ci_workflow_on_main():
    release = _load("release.yml")
    # PyYAML reads the bare key `on` as True.
    trigger = release[True]["workflow_run"]
    assert trigger["workflows"] == [_load("ci.yml")["name"]]
    assert trigger["types"] == ["completed"]
    assert trigger["branches"] == ["main"]


def test_release_runs_only_after_a_passing_push():
    job = _load("release.yml")["jobs"]["release"]
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert "github.event.workflow_run.event == 'push'" in job["if"]


def test_release_reads_the_version_from_the_manifest():
    assert (ROOT / MANIFEST).is_file()
    assert MANIFEST in (WORKFLOWS / "release.yml").read_text()
