"""Reads the recorded answer shapes in `tests/fixtures`."""

import json
from pathlib import Path
from typing import Any

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def answer(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
