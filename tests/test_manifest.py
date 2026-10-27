"""The manifest pins midea-local, which the local transport needs."""
from __future__ import annotations

import json
from pathlib import Path

MANIFEST = Path(__file__).parents[1] / "custom_components/midea_water_softener/manifest.json"


def test_manifest_requires_midea_local_14_0_0():
    requirements = json.loads(MANIFEST.read_text())["requirements"]
    assert "midea-local==14.0.0" in requirements
