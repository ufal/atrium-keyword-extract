"""
tests/conftest.py
=================
Shared pytest fixtures and sys.path wiring for atrium-keyword-extract unit tests.

sys.path is patched here (once, at collection time) so that every test module
can import from the repo root (``keywords.py``, ``atrium_paradata.py``).
"""

import sys
from pathlib import Path

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow integration smoke tests")


# ── path wiring ───────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── CoNLL-U fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def sample_conllu(tmp_path):
    """
    Three-sentence CoNLL-U file written to a temp path.

    Sentences:
        1. "Archeologický výzkum byl proveden."   (ADJ NOUN AUX VERB PUNCT)
        2. "Nalezená keramika a nádoby."           (ADJ NOUN CCONJ NOUN PUNCT)
        3. "Starý výzkum trval."                   (ADJ NOUN VERB PUNCT)

    Lemma counts: výzkum=2, archeologický=1, nalezený=1,
                  keramika=1, nádoba=1, starý=1

    SpaceAfter=No is set on every VERB/ADJ token immediately before a period,
    so "proveden." / "nádoby." / "trval." have no space between word and stop.
    """
    content = (FIXTURES_DIR / "sample.conllu").read_text(encoding="utf-8")
    dest = tmp_path / "sample.conllu"
    dest.write_text(content, encoding="utf-8")
    return str(dest)


@pytest.fixture
def empty_conllu(tmp_path):
    """CoNLL-U file with only a comment header — no token lines."""
    dest = tmp_path / "empty.conllu"
    dest.write_text("# newdoc\n", encoding="utf-8")
    return str(dest)
