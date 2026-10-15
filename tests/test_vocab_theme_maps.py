"""
tests/test_vocab_theme_maps.py — the registry's theme maps follow this repository's taxonomy.

``atrium_vocab.py`` is hub-canonical and vendored here, but its two theme maps
(``HESLAR_TO_THEME``, ``TEATER_BRANCH_TO_THEME``) are copies of decisions made in this
repository's ``data_samples/taxonomy_config.json`` (``_settings.heslar_map``,
``_settings.teater_branch_map``). They drifted once: the facet layout of 2026-10-08
(``heslar:jazyk`` excluded, TEATER branch ``1`` under Methods; david-spacil on #2) reached the
registry only on 2026-10-13 (atrium-project#51). This test fails on the next taxonomy edit until
the hub's registry follows it and is re-vendored.

Local to this repository (not in the hub's MANIFEST): the taxonomy lives here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import atrium_vocab as av

CONFIG = Path(__file__).resolve().parent.parent / "data_samples" / "taxonomy_config.json"
EXCLUDE = "__exclude__"


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _mapped(mapping: dict) -> dict:
    # `__exclude__` is a build-time gate, not a meaning; the registry leaves those entries out.
    return {key: theme for key, theme in mapping.items() if theme != EXCLUDE}


def test_heslar_map_equals_the_registry(taxonomy):
    expected = _mapped(taxonomy["_settings"]["heslar_map"])
    assert av.HESLAR_TO_THEME == expected, (
        "taxonomy_config.json heslar_map and atrium_vocab.HESLAR_TO_THEME differ: change the hub's "
        "docs/templates/shared/atrium_vocab.py and re-vendor (scripts/revendor_shared.sh)"
    )


def test_teater_branch_map_equals_the_registry(taxonomy):
    expected = _mapped(taxonomy["_settings"]["teater_branch_map"])
    assert av.TEATER_BRANCH_TO_THEME == expected, (
        "taxonomy_config.json teater_branch_map and atrium_vocab.TEATER_BRANCH_TO_THEME differ: change "
        "the hub's docs/templates/shared/atrium_vocab.py and re-vendor (scripts/revendor_shared.sh)"
    )


def test_every_facet_is_a_registry_theme(taxonomy):
    facets = {name for name in taxonomy if not name.startswith("_")}
    assert facets == set(av.THEMES)


def test_mapped_themes_are_registry_themes(taxonomy):
    settings = taxonomy["_settings"]
    for mapping in (settings["heslar_map"], settings["teater_branch_map"]):
        assert set(_mapped(mapping).values()) <= set(av.THEMES)


def test_the_2026_10_08_layout_is_in_the_registry():
    """The two decisions that drifted: the language list is metadata, not content, and TEATER's
    "Theory and approaches" branch is archaeology's own terms."""
    assert "jazyk" not in av.HESLAR_TO_THEME
    assert av.TEATER_BRANCH_TO_THEME["1"] == "Methods"
