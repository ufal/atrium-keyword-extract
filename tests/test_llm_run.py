"""
tests/test_llm_run.py — the torch-free logic units of the llm_run.py entry point.

Schema construction, system-prompt assembly with its token-budget truncation, the id/qualifier
passthrough (issue #6, B2/B3/C4), and the abort-marker sidecar. The runtime loop
(process_document*) needs a real model and is exercised only in the slow GPU lane.

Same GPU-lane convention as test_llm_utils.py: llm_run imports torch, transformers and
pysqlite3 at module scope, so this file skips entirely on a machine without them (the
fast CI lane) rather than failing. The schema/truncation/abort-marker cases came with
llm-enrich's copy of the engine (atrium-digital-convert 31534d5, atrium-keyword-extract#1).
"""

import json

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("pysqlite3")

import llm_run  # noqa: E402

VOCAB_DATA = {
    "Artefact": {
        "priority": 6,
        "in_prompt": True,
        "zámek": {
            "cs": "zámek",
            "en": "lock",
            "sub": "",
            "source": "amcr",
            "source_id": "HES-000817",
            "discarded_ids": [
                {"source": "teater", "id": "2358", "scheme": "1788", "cs": "zámek", "en": "lock"}
            ],
        },
    },
    "Activity Area": {
        "priority": 8,
        "in_prompt": True,
        "zámek (sídlo elity)": {
            "cs": "zámek (sídlo elity)",
            "en": "châteaux",
            "sub": "sídlo elity",
            "source": "teater",
            "source_id": "1439",
            "discarded_ids": [],
            "bare_cs": "zámek",
        },
    },
    "Other": {"priority": -1, "in_prompt": False, "keywords": {}},
}

#: The legacy flat shape (`{"keywords": {"cs": [...], "en": [...]}}`), still read.
_VOCAB = {
    "Structures": {"keywords": {"cs": ["kostel", "hrad"], "en": ["church", "castle"]}},
    "Periods": {"keywords": {"cs": ["středověk"], "en": ["Middle Ages"]}},
}


class _FakeTokenizer:
    """count_tokens() takes the ``tokenizer.encode(text)`` branch for anything without
    a ``tokenize`` method (that branch is reserved for llama.cpp-style tokenizers)."""

    def encode(self, text: str) -> list:
        return text.split()


def _tokenizer():
    return _FakeTokenizer()


# ── build_schema ─────────────────────────────────────────────────────────────


def test_build_schema_empty_raises():
    with pytest.raises(ValueError, match="term_names is empty"):
        llm_run.build_schema([])


def test_build_schema_accepts_valid_category():
    Model = llm_run.build_schema(["kostel", "hrad"])
    inst = Model(
        extracted_keywords_cs=["věž"],
        extracted_keywords_en=["tower"],
        teater_category="hrad",
        confidence_score=0.8,
    )
    assert inst.category_name() == "hrad"


def test_build_schema_rejects_unknown_category():
    from pydantic import ValidationError

    Model = llm_run.build_schema(["kostel", "hrad"])
    with pytest.raises(ValidationError):
        Model(
            extracted_keywords_cs=[],
            extracted_keywords_en=[],
            teater_category="not-a-term",
            confidence_score=0.5,
        )


def test_build_schema_accepts_a_qualified_label_as_an_enum_value():
    surviving = ["Nerelevantní (meta-text)", "zámek", "zámek (sídlo elity)"]
    Model = llm_run.build_schema(surviving)
    instance = Model.model_validate(
        {
            "extracted_keywords_cs": ["zámek"],
            "extracted_keywords_en": ["chateau"],
            "teater_category": "zámek (sídlo elity)",
            "confidence_score": 0.9,
        }
    )
    assert instance.category_name() == "zámek (sídlo elity)"


# ── build_system_prompt ──────────────────────────────────────────────────────


def test_build_system_prompt_full_fit():
    prompt, terms, _, _ = llm_run.build_system_prompt(_VOCAB, _tokenizer(), max_tokens=100_000)
    # The mandatory meta-text fallback term is always injected first.
    assert terms[0] == "Nerelevantní (meta-text)"
    for cs in ("kostel", "hrad", "středověk"):
        assert cs in terms
        assert cs in prompt
    assert "THEMATIC VOCABULARY" in prompt


def test_build_system_prompt_truncates_under_tiny_budget():
    full, full_terms, _, _ = llm_run.build_system_prompt(_VOCAB, _tokenizer(), max_tokens=100_000)
    budget = llm_run.count_tokens(full, _tokenizer()) - 1
    trunc, trunc_terms, _, _ = llm_run.build_system_prompt(_VOCAB, _tokenizer(), max_tokens=budget)
    assert len(trunc_terms) < len(full_terms)
    assert len(trunc) < len(full)


def test_build_system_prompt_skip_truncation_keeps_full():
    # Even with a tiny budget, skip_truncation must return the full vocabulary
    # (used when vLLM prefix caching makes truncation pointless).
    _, terms, _, _ = llm_run.build_system_prompt(
        _VOCAB, _tokenizer(), max_tokens=1, skip_truncation=True
    )
    for cs in ("kostel", "hrad", "středověk"):
        assert cs in terms


def test_build_system_prompt_returns_id_lookup_and_strip_map():
    prompt, surviving, id_lookup, strip_map = llm_run.build_system_prompt(
        VOCAB_DATA, _tokenizer(), max_tokens=10**9
    )
    assert "zámek (sídlo elity)" in surviving
    assert "zámek" in surviving

    assert id_lookup["zámek"] == [
        {"source": "amcr", "id": "HES-000817"},
        {"source": "teater", "id": "2358"},
    ]
    assert id_lookup["zámek (sídlo elity)"] == [{"source": "teater", "id": "1439"}]
    assert strip_map == {"zámek (sídlo elity)": "zámek"}
    # the synthetic meta-text term carries no ids and must not appear in either map
    assert "Nerelevantní (meta-text)" not in id_lookup
    assert "Nerelevantní (meta-text)" not in strip_map


def test_build_system_prompt_id_lookup_survives_truncation():
    """A term dropped by the binary-search truncation must not leave a stale id_lookup
    entry — the model was never shown that label, so nothing should claim to back it."""
    tok = _tokenizer()
    # The injected "Nerelevantní (meta-text)" term is always first, so a budget sized
    # to exactly the meta-text-only prompt admits that one term and nothing else.
    meta_only_prompt, _, _, _ = llm_run.build_system_prompt({}, tok, max_tokens=10**9)
    budget = llm_run.count_tokens(meta_only_prompt, tok)

    prompt, surviving, id_lookup, strip_map = llm_run.build_system_prompt(
        VOCAB_DATA, tok, max_tokens=budget
    )
    assert surviving == ["Nerelevantní (meta-text)"]
    assert id_lookup == {}
    assert strip_map == {}


# ── _attach_category_ids (B2/B3/C4 post-inference passthrough) ─────────────────

ID_LOOKUP = {
    "zámek": [{"source": "amcr", "id": "HES-000817"}, {"source": "teater", "id": "2358"}],
    "zámek (sídlo elity)": [{"source": "teater", "id": "1439"}],
}
STRIP_MAP = {"zámek (sídlo elity)": "zámek"}


def test_attach_category_ids_strips_qualifier_and_attaches_full_id_set():
    results = [{"enrichment": {"teater_category": "zámek (sídlo elity)"}}]
    llm_run._attach_category_ids(results, ID_LOOKUP, STRIP_MAP, emit_ids=True)
    enrichment = results[0]["enrichment"]
    assert enrichment["teater_category"] == "zámek"  # bracket stripped
    assert enrichment["teater_category_ids"] == [{"source": "teater", "id": "1439"}]


def test_attach_category_ids_leaves_a_native_bracket_untouched():
    """A term that legitimately contains parentheses in its own source label (319 of
    them exist, e.g. 'GPS (navigační systém)') must never be stripped — only labels
    vocab_sources.to_term_pairs itself qualified (present in strip_map) are."""
    results = [{"enrichment": {"teater_category": "GPS (navigační systém)"}}]
    llm_run._attach_category_ids(results, {}, {}, emit_ids=True)
    assert results[0]["enrichment"]["teater_category"] == "GPS (navigační systém)"
    assert results[0]["enrichment"]["teater_category_ids"] == []


def test_attach_category_ids_can_be_disabled():
    results = [{"enrichment": {"teater_category": "zámek"}}]
    llm_run._attach_category_ids(results, ID_LOOKUP, STRIP_MAP, emit_ids=False)
    assert "teater_category_ids" not in results[0]["enrichment"]


# ── _write_abort_marker ──────────────────────────────────────────────────────


def test_write_abort_marker(tmp_path):
    out_file = tmp_path / "CTX1_enriched.json"
    llm_run._write_abort_marker(out_file, {"processed": 7, "skipped_error": 10}, reason="boom")
    marker = tmp_path / "CTX1_enriched.abort.json"
    assert marker.exists()
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["aborted"] is True
    assert data["abort_reason"] == "boom"
    assert data["processed_before_abort"] == 7
    assert data["errors_before_abort"] == 10
