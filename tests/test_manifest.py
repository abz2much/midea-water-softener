"""midea-local: a minimum version in the manifest, an exact pin for the tests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "custom_components/midea_water_softener/manifest.json"


def test_manifest_asks_for_midea_local_12_2_0_or_newer():
    # hassfest rejects an exact pin of a package Home Assistant depends on;
    # a minimum lets it follow HA's own Midea integration.
    requirements = json.loads(MANIFEST.read_text())["requirements"]
    assert "midea-local>=12.2.0" in requirements


def test_the_tests_pin_midea_local_12_2_0():
    lines = (ROOT / "requirements_test.txt").read_text().split()
    assert "midea-local==12.2.0" in lines
