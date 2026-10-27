"""The manifest pins midea-local to the version Home Assistant's own Midea integration uses."""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).parents[1] / "custom_components/midea_water_softener/manifest.json"


def test_manifest_requires_midea_local_12_2_0():
    requirements = json.loads(MANIFEST.read_text())["requirements"]
    assert "midea-local==12.2.0" in requirements
