"""
tests/test_controlled_live.py
=============================
The controlled kind of ``service/api.py`` against a real LLM backend (atrium-keyword-extract#1,
#2).

Every other test of the controlled kind stubs the model's chat function (``tests/conftest.py``:
``controlled``), so none of them sees what only a real backend shows: that the provider still
takes the request (the vocabulary's schema as ``response_format``, a prompt of some 50k tokens),
that the model's replies validate against that schema, and that a record and a CreateAction
built from real replies pass the same gates as the stubbed ones.

Opt-in, like the translator's live-backend lane: the module runs only with
``ATRIUM_LIVE_BACKEND=1``, and then the backend must be configured (``OPENROUTER_API_KEY`` and
``OPENROUTER_MODEL``, or ``LLM_BACKEND=ollama`` with ``OLLAMA_MODEL``). An opted-in run whose
backend does not start fails instead of skipping. One run sends two lines, two calls.
``.github/workflows/controlled-live.yml`` runs it with the repository's ``OPENROUTER_KEY``
secret; locally::

    ATRIUM_LIVE_BACKEND=1 OPENROUTER_API_KEY=sk-... OPENROUTER_MODEL=openai/gpt-4o-mini \\
        pytest -rs tests/test_controlled_live.py

The assertions hold for any model that answers within the schema. Which category a model
chooses is printed, not asserted: that is the evaluation's question (#2), not this lane's.
"""

import json
import os
from pathlib import Path

import pytest

if os.getenv("ATRIUM_LIVE_BACKEND") != "1":
    pytest.skip(
        "calls a real LLM backend: set ATRIUM_LIVE_BACKEND=1 and configure one",
        allow_module_level=True,
    )

from fastapi.testclient import TestClient  # noqa: E402

import atrium_document  # noqa: E402
import atrium_openapi  # noqa: E402
import atrium_rocrate  # noqa: E402
from service import api  # noqa: E402

_SPEC = atrium_openapi.load(Path(__file__).resolve().parent.parent / "service" / "openapi.json")

DOC = "CTX000000001"
META = "Nerelevantní (meta-text)"

#: The record after nlp-enrich, schema-valid, so the service's own output check is enforced
#: rather than demoted (rule 6): two lines any archaeological vocabulary has a term for, and an
#: entity the vocabulary knows, so `entities[].pid` is written whatever the model answers.
RECORD = {
    "schema_version": "1.0",
    "record_type": "atrium-document",
    "doc_id": DOC,
    "provenance": {
        "contributors": [
            {"program": "ocr-postprocess", "blocks": "pages,lines"},
            {"program": "nlp-enrich", "blocks": "entities"},
        ]
    },
    "assembled": {
        "had_baseline": True,
        "blocks": {
            "pages": {"program": "ocr-postprocess"},
            "lines": {"program": "ocr-postprocess"},
            "entities": {"program": "nlp-enrich"},
        },
    },
    "pages": [{"page": "1", "page_index": 1}],
    "lines": [
        {
            "page": "1",
            "line": 1,
            "text": "Výzkum odhalil základy gotického kostela.",
            "categ": "Clear",
            "quality_score": 0.91,
        },
        {
            "page": "1",
            "line": 2,
            "text": "V příkopu pod hradem byla nalezena středověká keramika.",
            "categ": "Clear",
            "quality_score": 0.9,
        },
    ],
    "entities": [
        {
            "page": "1",
            "line": 1,
            "char_span": [23, 40],
            "surface": "gotického kostela",
            "lemma": "kostel",
            "type_onto": "FAC",
        }
    ],
}


@pytest.fixture(scope="module")
def live():
    """The service's own warm-up against the configured backend, then a client."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api, "DEFAULT_KW_METHOD", "yake")  # no KeyBERT model to load
        mp.setattr(api, "_controlled", {})
        api._warmup()
        if not api._controlled_ready():
            pytest.fail(f"the controlled kind did not start: {api._controlled_unavailable()}")
        yield TestClient(api.app)


@pytest.fixture(scope="module")
def answer(live):
    """One `/extract_keywords` call with the record, the controlled kind alone."""
    files = {
        "document_json": (
            "r.document.json",
            json.dumps(RECORD, ensure_ascii=False),
            "application/json",
        )
    }
    response = live.post("/extract_keywords", files=files, data={"kind": "controlled"})
    assert response.status_code == 200, response.text
    body = response.json()
    for item in body.get("enrichment", {}).get("items", []):
        print(
            f"P{item['page']} L{item['line']}: {item['teater_category']!r} "
            f"cs={item.get('extracted_keywords_cs')} en={item.get('extracted_keywords_en')}"
        )
    return body


def test_the_baseline_is_a_valid_record():
    """An invalid one would demote the service's own output check to a warning (rule 6), and the
    Layer D assertion below would prove less."""
    atrium_document.validate_document(RECORD)


def test_info_reports_the_backend_ready(live):
    info = live.get("/info").json()["controlled"]
    assert info["ready"] is True and info["detail"] is None, info
    assert info["backend"] == os.getenv("LLM_BACKEND", "openrouter").strip().lower()
    assert info["vocabulary"]["prompt_terms"] > 0, info["vocabulary"]


def test_the_response_conforms_to_the_published_schema(answer):
    atrium_openapi.validate_response(_SPEC, "/extract_keywords", "post", 200, answer)


def test_every_line_was_answered_within_the_vocabulary(answer):
    controlled = answer["controlled"]
    assert controlled["outcome"] == "contributed", controlled
    stats = controlled["stats"]
    assert stats["attempted"] == 2 and stats["skipped_error"] == 0, stats
    items = answer["enrichment"]["items"]
    assert [(i["page"], i["line"]) for i in items] == [("1", 1), ("1", 2)]
    # The schema allows only vocabulary terms and the meta-text label; two lines about a church
    # and pottery both answered as meta-text would mean the model is not reading the vocabulary.
    assert any(i["teater_category"] != META for i in items), items


def test_the_record_comes_back_with_its_blocks_and_passes_layer_d(answer):
    record = answer["document_json"]
    assert "document_json_schema_error" not in answer, answer["document_json_schema_error"]
    assert record["doc_id"] == DOC
    assert record["enrichment"] == answer["enrichment"]
    assert record["assembled"]["blocks"]["enrichment"]["program"] == "keyword-extract"
    assert [line["text"] for line in record["lines"]] == [line["text"] for line in RECORD["lines"]]
    (church,) = record["entities"]
    assert church["pid"]["amcr"].startswith("https://api.aiscr.cz/id/"), church


def test_the_create_action_names_the_model_and_the_vocabularies(answer):
    action = answer["paradata"]
    assert atrium_rocrate.action_problems(action) == []
    assert action["paradataRecord"]["config"]["model"] == answer["controlled"]["model"]
    components = {c["name"] for c in action["paradataRecord"]["license_detail"]["components"]}
    assert {"amcr_vocab", "teater_data"} <= components, components
