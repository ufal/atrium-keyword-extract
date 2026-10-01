"""
tests/test_cli_orchestration.py — every CLI entry point at least parses its arguments.

Lived in ``api_util/`` until 2026-09, outside ``pytest.ini``'s ``testpaths``, so none of
these ever ran. ``llm_run.py`` imports torch/transformers/pysqlite3 at module scope and is
skipped on the fast lane without them, the same GPU-lane convention as test_llm_run.py.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).parent.parent


def _missing(*modules):
    return [m for m in modules if importlib.util.find_spec(m) is None]


@pytest.mark.skipif(
    bool(_missing("torch", "transformers", "pysqlite3")),
    reason="llm_run.py needs the GPU-lane requirements (torch, transformers, pysqlite3)",
)
def test_llm_run_cli_help():
    """Ensure the LLM orchestration script compiles and parses arguments."""
    res = subprocess.run(
        [sys.executable, str(ROOT_DIR / "llm_run.py"), "--help"], capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "usage" in res.stdout.lower() or "help" in res.stdout.lower()


def test_keywords_cli_help():
    """Ensure the keyword extraction script compiles and parses arguments."""
    res = subprocess.run(
        [sys.executable, str(ROOT_DIR / "keywords.py"), "--help"], capture_output=True, text=True
    )
    assert res.returncode == 0
    assert "usage" in res.stdout.lower() or "help" in res.stdout.lower()
