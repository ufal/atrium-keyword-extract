"""tests/test_api_service.py
=========================
Hermetic tests for the keyword-extract API service (atrium-keyword-extract#1).

YAKE and the legacy method run for real (CPU, no model); KeyBERT is replaced by a stub at
``keywords._keybert_from_texts`` so no embedding model is loaded.
"""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("fastapi.testclient")
pytest.importorskip("yake")

from fastapi.testclient import TestClient  # noqa: E402

import atrium_rocrate  # noqa: E402
import keywords  # noqa: E402
from service import api  # noqa: E402

client = TestClient(api.app)

TEXT = (
    "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou a kamennými nástroji. "
    "Keramika pochází z doby bronzové a objekt byl zahlouben do spraše."
)


def _record():
    return {
        "doc_id": "AMCR-F-1",
        "lines": [
            {
                "page": "1",
                "line": 1,
                "text": "Keramika z doby bronzové",
                "lemma": "keramika",
                "upos": "NOUN",
            },
            {
                "page": "1",
                "line": 2,
                "text": "kamenné nástroje",
                "lemma": "nástroj",
                "upos": "NOUN",
            },
            {
                "page": "2",
                "line": 1,
                "text": "Zahloubený objekt se sídlištní keramikou",
                "lemma": "objekt",
                "upos": "NOUN",
            },
            {"page": "2", "line": 2, "text": "garbage ~~ ##", "categ": "Trash"},
            {"page": "2", "line": 3, "text": "", "categ": "Empty"},
            # digital-convert's decode verdict on a born-digital text layer that does not decode
            {"page": "2", "line": 4, "text": "garbage sondì høeby", "categ": "Garbage"},
            {"page": "2", "line": 5, "text": "garbage ǝʇɐɹǝdo", "categ": "Inverted"},
        ],
    }


def _post_record(record, **data):
    files = {"document_json": ("r.document.json", json.dumps(record), "application/json")}
    return client.post("/extract_keywords", files=files, data=data)


@pytest.fixture
def fake_keybert(monkeypatch):
    calls = []

    def fake(texts, num_keywords, **kwargs):
        calls.append(list(texts))
        return [[(f"kb-{i}", 0.9 - i / 10) for i in range(min(num_keywords, 2))] for _ in texts]

    monkeypatch.setattr(keywords, "_keybert_from_texts", fake)
    return calls


def test_text_endpoint_returns_keywords_with_method_score_and_rank():
    r = client.post(
        "/extract_keywords_text", json={"text": TEXT, "method": "yake", "num_keywords": 4}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method_used"] == "yake" and body["words"] == len(TEXT.split())
    assert 1 <= len(body["keywords"]) <= 4
    for rank, kwd in enumerate(body["keywords"], start=1):
        assert kwd["method"] == "yake" and isinstance(kwd["score"], float) and kwd["rank"] == rank
    assert body["pages"] == []


def test_the_response_carries_the_runs_create_action():
    body = client.post("/extract_keywords_text", json={"text": TEXT, "method": "yake"}).json()
    action = body["paradata"]
    assert atrium_rocrate.action_problems(action) == []
    assert action["instrument"]["name"] == "atrium-keyword-extract"
    assert action["actionStatus"].endswith("CompletedActionStatus")
    assert any(
        c["name"] == "yake" for c in action["paradataRecord"]["license_detail"]["components"]
    )


def test_record_endpoint_gives_document_and_page_keywords(fake_keybert):
    r = _post_record(_record(), kind="statistical", method="keybert", num_keywords="2")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_id"] == "AMCR-F-1" and body["kind"] == "statistical"
    assert [p["page"] for p in body["pages"]] == ["1", "2"]
    assert all(k["method"] == "keybert" for p in body["pages"] for k in p["keywords"])
    # one batch: the document, then each page; Trash, Garbage, Inverted and Empty lines are not read
    assert len(fake_keybert) == 1 and len(fake_keybert[0]) == 3
    assert "garbage" not in " ".join(fake_keybert[0])


def test_the_skipped_categories_are_the_hub_registrys():
    """`atrium_vocab.UNTRUSTWORTHY_LINE_CATEGORIES` is the one declaration downstream filters key off."""
    from atrium_vocab import UNTRUSTWORTHY_LINE_CATEGORIES
    from service import api

    assert api._SKIPPED_CATEGORIES == frozenset(UNTRUSTWORTHY_LINE_CATEGORIES) | {"Empty"}


def test_per_page_can_be_switched_off(fake_keybert):
    body = _post_record(_record(), method="keybert", per_page="false").json()
    assert body["pages"] == [] and len(fake_keybert[0]) == 1


def test_legacy_counts_the_lemmas_of_the_record():
    body = _post_record(_record(), method="legacy", num_keywords="5").json()
    assert {k["keyword"] for k in body["keywords"]} == {"keramika", "nástroj", "objekt"}
    assert all(k["method"] == "legacy" for k in body["keywords"])


def test_legacy_without_lemmas_is_refused():
    r = client.post("/extract_keywords_text", json={"text": TEXT, "method": "legacy"})
    assert r.status_code == 422 and "lemma" in r.json()["detail"]


def test_both_kinds_runs_the_statistical_one_and_says_the_other_was_skipped():
    body = client.post(
        "/extract_keywords_text", json={"text": TEXT, "method": "yake", "kind": "both"}
    ).json()
    assert [(k["kind"], k["status"]) for k in body["kinds"]] == [
        ("statistical", "ok"),
        ("controlled", "skipped"),
    ]


def test_the_controlled_kind_alone_is_not_in_this_release():
    r = client.post("/extract_keywords_text", json={"text": TEXT, "kind": "controlled"})
    assert r.status_code == 501 and r.json()["status"] == 501


def test_an_unopenable_record_is_invalid_record():
    files = {"document_json": ("r.json", "[1, 2]", "application/json")}
    r = client.post("/extract_keywords", files=files)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_record"


def test_a_record_without_text_is_refused():
    r = _post_record({"doc_id": "X", "lines": []})
    assert r.status_code == 422 and "no text" in r.json()["detail"]


def test_over_the_keyword_limit_is_limit_exceeded(monkeypatch):
    monkeypatch.setenv("MAX_KEYWORDS", "3")
    r = client.post(
        "/extract_keywords_text", json={"text": TEXT, "method": "yake", "num_keywords": 4}
    )
    assert r.status_code == 422 and r.json()["reason"] == "limit_exceeded"
    assert r.json()["limit"]["key"] == "max_keywords"


def test_over_the_document_word_limit_is_413(monkeypatch):
    monkeypatch.setenv("MAX_DOCUMENT_WORDS", "5")
    r = client.post("/extract_keywords_text", json={"text": TEXT, "method": "yake"})
    assert r.status_code == 413 and r.json()["limit"]["key"] == "max_document_words"


def test_every_slot_taken_is_busy(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "1")
    api._semaphore.running = 1
    try:
        r = client.post("/extract_keywords_text", json={"text": TEXT, "method": "yake"})
    finally:
        api._semaphore.running = 0
    assert (
        r.status_code == 429 and r.json()["reason"] == "busy" and r.headers["Retry-After"] == "15"
    )


def test_the_slot_is_released_after_a_request():
    client.post("/extract_keywords_text", json={"text": TEXT, "method": "yake"})
    assert api._semaphore.running == 0


def test_keybert_limits_that_shaped_the_result_are_reported(monkeypatch):
    def fake(texts, num_keywords, limit_counts=None, **kwargs):
        limit_counts["split"] = 1
        return [[("kb", 0.5)] for _ in texts]

    monkeypatch.setattr(keywords, "_keybert_from_texts", fake)
    body = client.post("/extract_keywords_text", json={"text": TEXT, "method": "keybert"}).json()
    assert [(n["limit"], n["effect"]) for n in body["limits_applied"]] == [
        ("keybert_chunk_words", "split")
    ]


def test_info_names_the_methods_and_kinds():
    info = client.get("/info").json()
    assert info["methods"]["default"] == api.DEFAULT_KW_METHOD
    assert set(info["methods"]["available"]) == {"keybert", "yake", "legacy"}
    assert info["kinds"] == {"available": ["statistical"], "planned": ["controlled"]}
