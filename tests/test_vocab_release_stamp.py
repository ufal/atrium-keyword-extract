"""
tests/test_vocab_release_stamp.py — the vocabulary sidecars carry the release's version.

The release packages the vocabulary as a CC0 asset and refuses a sidecar stamped with another
version ("Package the vocabulary (CC0)" in release.yml). v1.5.0-beta was tagged with sidecars still
stamped v1.4.0-beta: the images were published, the GitHub release was not (atrium-project#72,
#81). This test runs the same comparison on every push, so a version bump without
`python vocab_build.py --from-flat --skos` fails here, before a tag is cut.
"""

from __future__ import annotations

import configparser
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VOCAB = ROOT / "data_samples" / "vocab"


def _version() -> str:
    config = configparser.ConfigParser()
    config.read(ROOT / "para_config.txt", encoding="utf-8")
    return config.get("tool", "version")


def test_sidecars_are_stamped_with_the_release_version():
    version = _version()
    sidecars = [VOCAB / f"{name}_nested.meta.json" for name in ("union", "amcr", "teater")]
    stamps = {
        path.name: json.loads(path.read_text(encoding="utf-8")).get("tool_version")
        for path in sidecars
    }
    stale = {name: stamp for name, stamp in stamps.items() if stamp != version}
    assert not stale, (
        f"the vocabulary sidecars are stamped {stale}, not {version}: run "
        "`python vocab_build.py --from-flat --skos` and commit the result before tagging"
    )
