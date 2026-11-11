"""Every language file has the same keys, and the panel only uses keys that exist."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "lunch_planner"
LANGUAGES = sorted(p.stem for p in (ROOT / "translations").glob("*.json"))


def load(lang: str) -> dict:
    return json.loads((ROOT / "translations" / f"{lang}.json").read_text(encoding="utf-8"))


def keys(tree: dict, prefix: str = "") -> set[str]:
    result = set()
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        result |= keys(value, path) if isinstance(value, dict) else {path}
    return result


def test_strings_json_is_the_english_file():
    assert json.loads((ROOT / "strings.json").read_text(encoding="utf-8")) == load("en")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_same_keys_as_english(lang):
    assert keys(load(lang)) == keys(load("en"))


@pytest.mark.parametrize("lang", LANGUAGES)
def test_panel_keys_exist(lang):
    script = (ROOT / "frontend" / "panel.js").read_text(encoding="utf-8")
    block = script[script.index("const TEXT_KEYS = {") : script.index("};", script.index("const TEXT_KEYS"))]
    used = set(re.findall(r':\s*"([a-z_]+)"', block))
    categories = re.search(r"const CATEGORIES = \[([^\]]*)\]", script)[1]
    used |= {f"category_{c}" for c in re.findall(r'"([a-z]+)"', categories)}
    available = set(load(lang)["selector"]["panel"]["options"])
    assert used <= available, used - available


@pytest.mark.parametrize("lang", LANGUAGES)
def test_notification_texts_exist(lang):
    options = load(lang)["selector"]["notification"]["options"]
    expected = {"default_name", "event", "soup_format", "soup_word"} | {
        f"weekday_{d}" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    assert set(options) == expected
    assert "{meal}" in options["event"]
    assert "{name}" in options["soup_format"]
