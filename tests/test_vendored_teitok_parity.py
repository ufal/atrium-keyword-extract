"""tests/test_vendored_teitok_parity.py -- the TEITOK files vendored from atrium-nlp-enrich.

atrium-nlp-enrich writes TEITOK XML and owns the code that reads and converts it; this repo
only reads it, for the batch CLI's `.teitok.xml` input (`keywords.py`) and for the research LLM
code. The files below are verbatim copies of the nlp-enrich files at the same paths, and their
tests stay there.

Each copy is pinned by the SHA-256 of the nlp-enrich file it was taken from (line endings
normalised to ``\\n``). A mismatch means a local edit to a vendored file -- make the change
in atrium-nlp-enrich instead -- or a re-vendor without updating the pins.

To re-vendor:

1. Copy the files from atrium-nlp-enrich (same relative paths).
2. Run ``python3 tests/test_vendored_teitok_parity.py`` and paste its output over
   ``VENDORED`` below; set ``ADOPTED["commit"]`` to the nlp-enrich commit the files came from
   (``git -C ../atrium-nlp-enrich rev-parse HEAD``) and ``ADOPTED["release"]`` to its first release.
3. Commit the copies and the new pins together (atrium-project docs/shared_components.md).

When an atrium-nlp-enrich checkout sits next to this repo (``../atrium-nlp-enrich``),
the copies are also compared with it byte for byte. That check is skipped when the
checkout is absent (CI): the hub's para-drift ``vendored-parity`` job runs it there.
"""

import hashlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NLP_ENRICH = REPO_ROOT.parent / "atrium-nlp-enrich"

#: The owner revision the copies were taken from (atrium-project#82): the
#: atrium-nlp-enrich commit of 2026-10-15 (issue #42); its files have the digests below, first released
#: in v1.1.0-beta.
ADOPTED = {
    "owner": "atrium-nlp-enrich",
    "commit": "6726124b5faac0baa0e6ef70bc6d7a2318940d56",
    "release": "v1.1.0-beta",
}

VENDORED = {
    "api_util/teitok_read.py": "861be1187ee130a2251b475325eab1785e6a50d1fb363ebe161407e2f498c280",
    "api_util/bbox_scale.py": "a3198dfdb8ab9dad0688139678514f4cdea86d066bc6a12c814f7e24937011f4",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


@pytest.mark.parametrize("rel", sorted(VENDORED))
def test_vendored_copy_matches_its_pin(rel):
    assert _digest(REPO_ROOT / rel) == VENDORED[rel], (
        f"{rel} differs from the atrium-nlp-enrich copy it was vendored from -- change it in "
        "atrium-nlp-enrich and re-vendor (see this module's docstring)"
    )


@pytest.mark.parametrize("rel", sorted(VENDORED))
def test_vendored_copy_matches_a_sibling_nlp_enrich_checkout(rel):
    upstream = NLP_ENRICH / rel
    if not upstream.is_file():
        pytest.skip("no ../atrium-nlp-enrich checkout next to this repo")
    assert _digest(REPO_ROOT / rel) == _digest(upstream), f"{rel} drifted from atrium-nlp-enrich"


def test_adopted_names_an_immutable_owner_revision():
    assert ADOPTED["owner"] == NLP_ENRICH.name
    assert re.fullmatch(r"[0-9a-f]{40}", ADOPTED["commit"]), (
        "a full commit SHA, not a branch or a short SHA"
    )
    assert re.fullmatch(r"v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", ADOPTED["release"])


def test_the_writer_is_not_vendored():
    """Only nlp-enrich writes TEITOK."""
    assert not (REPO_ROOT / "api_util" / "teitok_alto.py").exists()


if __name__ == "__main__":
    for rel in sorted(VENDORED):
        print(f'    "{rel}": "{_digest(REPO_ROOT / rel)}",')
