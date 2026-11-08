"""Shared test helpers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "editions"


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


@pytest.fixture
def normal() -> dict[str, Any]:
    return copy.deepcopy(load_fixture("normal"))


@pytest.fixture
def quiet() -> dict[str, Any]:
    return copy.deepcopy(load_fixture("quiet_day"))
