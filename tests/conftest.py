import json

import pytest

from aae import config
from aae.dataset import build


@pytest.fixture(scope="session")
def unit_split() -> str:
    """A small split built once per machine (16 packages, a few seconds); reused when its manifest exists."""
    if not (config.DATA / "unit" / "manifest.json").exists():
        build("unit")
    return "unit"


@pytest.fixture(scope="session")
def unit_truths(unit_split: str) -> dict[str, dict]:
    folder = config.DATA / unit_split / "truth"
    return {p.stem: json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))}
