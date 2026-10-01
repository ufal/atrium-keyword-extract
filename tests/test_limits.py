"""tests/test_limits.py — every limit is a setting, and none cuts an input quietly.

atrium-project#53 (factor III), for this repo: the limits are declared in tool_limits.py, an
input over one is refused with the harmonised error, a full service answers 429 ``busy``, and
every limit that shapes a result without refusing it is recorded (``limits_applied``). The
endpoint-level cases (413, 422, 429) are in tests/test_api_service.py and test_api_contract.py;
tests/test_limits_contract.py (canonical) checks the declaration against .env.example and
service/README.md.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import keywords as kw
import tool_limits
from atrium_limits import LimitExceeded

# ── the declaration ─────────────────────────────────────────────────────────────────────


def test_every_limit_is_an_environment_setting_with_a_default():
    env = {spec.env for spec in tool_limits.LIMITS}
    assert {
        "MAX_UPLOAD_MB",
        "MAX_DOCUMENT_WORDS",
        "MAX_KEYWORDS",
        "MAX_CONCURRENT_REQUESTS",
        "KEYBERT_CHUNK_WORDS",
        "KEYBERT_CHUNK_OVERLAP",
    } == env
    assert tool_limits.MAX_UPLOAD.get() == 10


def test_a_malformed_setting_stops_the_process_naming_the_variable(monkeypatch):
    from atrium_limits import LimitConfigError

    monkeypatch.setenv("MAX_KEYWORDS", "many")
    with pytest.raises(LimitConfigError, match="MAX_KEYWORDS"):
        tool_limits.MAX_KEYWORDS.get()


def test_over_max_keywords_is_limit_exceeded_with_status_422(monkeypatch):
    monkeypatch.setenv("MAX_KEYWORDS", "5")
    with pytest.raises(LimitExceeded) as caught:
        tool_limits.MAX_KEYWORDS.check(6)
    assert caught.value.http_status == 422 and caught.value.key == "max_keywords"


def test_over_max_document_words_is_limit_exceeded_with_status_413(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENT_WORDS", "10")
    with pytest.raises(LimitExceeded) as caught:
        tool_limits.MAX_DOCUMENT_WORDS.check(11)
    assert caught.value.http_status == 413


# ── notes: KeyBERT chunking ─────────────────────────────────────────────────────────────


class _Encoder:
    max_seq_length = 8

    @staticmethod
    def tokenizer(text):
        return {"input_ids": ["[CLS]", *text.split(), "[SEP]"]}


class _KeyBERT:
    model = SimpleNamespace(embedding_model=_Encoder())

    def extract_keywords(self, chunks, **_kw):
        return [[(chunk.split()[0], 0.5)] for chunk in chunks]


def test_keybert_chunking_is_a_setting_and_is_counted(monkeypatch):
    monkeypatch.setenv("KEYBERT_CHUNK_WORDS", "10")
    monkeypatch.setenv("KEYBERT_CHUNK_OVERLAP", "2")
    monkeypatch.setattr(kw, "_get_keybert_model", lambda _name: _KeyBERT())
    monkeypatch.setattr(
        kw,
        "_extract_surface_text",
        lambda p: " ".join(f"w{i}" for i in range(25)) if p == "long" else "a b",
    )
    counts: dict = {}
    result = kw._extract_keybert(["long", "short"], 5, limit_counts=counts)
    assert len(result) == 2 and result[1] == [("a", 0.5)]
    # 25 words, chunks of 10 starting every 8 words: w0-w9, w8-w17, w16-w24 (over the 8-token
    # window) and w24 (not over it) -- the chunking the literal 400/50 always did.
    assert counts == {"split": 1, "trimmed": 3, "window": 8}
    assert [c.split()[0] for c in kw._chunk_words([f"w{i}" for i in range(25)], 10, 2)] == [
        "w0",
        "w8",
        "w16",
        "w24",
    ]


def test_the_text_entry_point_chunks_the_same_way(monkeypatch):
    monkeypatch.setenv("KEYBERT_CHUNK_WORDS", "10")
    monkeypatch.setenv("KEYBERT_CHUNK_OVERLAP", "2")
    monkeypatch.setattr(kw, "_get_keybert_model", lambda _name: _KeyBERT())
    counts: dict = {}
    result = kw.extract_from_texts(
        [" ".join(f"w{i}" for i in range(25)), "a b", ""], "keybert", 5, limit_counts=counts
    )
    assert [len(r) for r in result] == [4, 1, 0]
    assert counts["split"] == 1


def test_keybert_notes_reach_the_paradata(tmp_path):
    from atrium_paradata import ParadataLogger

    logger = ParadataLogger(program="keyword-extract", config={}, paradata_dir=str(tmp_path))
    kw._note_keybert_limits(logger, {"split": 2, "trimmed": 5, "window": 128})
    notes = {n["limit"]: n for n in logger.limits_applied}
    assert (notes["keybert_chunk_words"]["effect"], notes["keybert_chunk_words"]["count"]) == (
        "split",
        2,
    )
    assert (notes["keybert_max_seq_tokens"]["value"], notes["keybert_max_seq_tokens"]["count"]) == (
        128,
        5,
    )
