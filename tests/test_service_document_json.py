"""
tests/test_service_document_json.py
====================================
The controlled kind of ``service/api.py``: the record after nlp-enrich in, the record with
keyword-extract's ``enrichment`` block (and ``entities[].pid``) out (atrium-keyword-extract#1, #2).

Ported from llm-enrich's test of the same name (atrium-digital-convert 31534d5), which tested
the ``document_json`` part of llm-enrich's ``/extract_keywords``: what is pinned is still the
accretion guarantee (the record's other blocks come back untouched) and Layer D on the way out
(atrium-project#10, D4). The engine is the real one — the shipped vocabulary, the prompt
``llm_config.txt`` configures, the 4712-term schema — with the LLM call stubbed
(``tests/conftest.py``: ``controlled``), so no network is needed.
"""

import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from service import api  # noqa: E402

client = TestClient(api.app)

DOC = "CTX000000001"

#: The record the AMČR pipeline sends: an OCR'd page with a quality-filtered line, a heading,
#: nlp-enrich's entities, and a page this stage must not touch.
RECORD = {
    "schema_version": "1.0",
    "record_type": "atrium-document",
    "doc_id": DOC,
    "pages": [{"page": "1", "page_index": 1}, {"page": "iv", "page_index": 2}],
    "lines": [
        {
            "page": "1",
            "line": 1,
            "text": "Výzkum odhalil základy gotického kostela.",
            "categ": "Clear",
            "quality_score": 0.91,
        },
        {"page": "1", "line": 2, "text": "garbage ~~ ##", "categ": "Trash", "quality_score": 0.1},
        {
            "page": "iv",
            "line": 1,
            "text": "Zámek nad řekou, v příkopu nalezena keramika.",
            "categ": "Clear",
            "quality_score": 0.88,
        },
        {
            "page": "iv",
            "line": 2,
            "text": "Praha, dne 6. října 1956, Dr. Solle",
            "categ": "Clear",
            "quality_score": 0.9,
        },
    ],
    "entities": [
        {
            "page": "1",
            "line": 1,
            "char_span": [27, 44],
            "surface": "gotického kostela",
            "lemma": "kostel",
            "type_onto": "FAC",
        },
        {
            "page": "iv",
            "line": 2,
            "char_span": [0, 5],
            "surface": "Praha",
            "lemma": "Praha",
            "type_onto": "GPE",
        },
    ],
}


def _post(record=RECORD, **data):
    files = {
        "document_json": (
            "r.document.json",
            json.dumps(record, ensure_ascii=False),
            "application/json",
        )
    }
    return client.post("/extract_keywords", files=files, data=data)


def test_the_record_comes_back_with_its_enrichment_block_and_every_other_block_untouched(
    controlled,
):
    response = _post(kind="controlled")
    assert response.status_code == 200, response.text
    body = response.json()
    record = body["document_json"]
    assert record["doc_id"] == DOC
    assert record["assembled"]["had_baseline"] is True
    assert record["pages"] == RECORD["pages"]
    assert [line["text"] for line in record["lines"]] == [line["text"] for line in RECORD["lines"]]
    assert record["assembled"]["blocks"]["enrichment"]["program"] == "keyword-extract"
    assert record["enrichment"] == body["enrichment"]
    assert "document_json_schema_error" not in body
    # The statistical kind did not run: no keywords, and the record has no `keywords` block.
    assert body["keywords"] == [] and body["method_used"] is None and "keywords" not in record


def test_one_item_per_line_the_model_was_asked_about_with_the_records_page_labels(controlled):
    body = _post(kind="controlled").json()
    items = body["enrichment"]["items"]
    # The Trash line was not sent; the three others were, in record order.
    assert [(i["page"], i["line"]) for i in items] == [("1", 1), ("iv", 1), ("iv", 2)]
    assert len(controlled.chat.calls) == 3
    assert body["controlled"]["outcome"] == "contributed"
    assert body["controlled"]["stats"]["skipped_filter"] == 1
    assert items[1]["citation"] == f"[Source: {DOC}, Page iv]"


def test_ids_are_attached_and_a_qualified_homonym_comes_back_bare(controlled):
    items = _post(kind="controlled").json()["enrichment"]["items"]
    church, chateau, meta = items
    assert church["teater_category"] == "kostel"
    assert church["teater_category_ids"] == [
        {"source": "amcr", "id": "HES-000021"},
        {"source": "amcr", "id": "HES-000465"},
        {"source": "teater", "id": "1333"},
    ]
    # The model chose "zámek (sídlo elity)"; the record carries the bare label, the ids the sense.
    assert chateau["teater_category"] == "zámek"
    assert chateau["teater_category_ids"] == [{"source": "teater", "id": "1439"}]
    assert meta["teater_category"] == "Nerelevantní (meta-text)"
    assert meta["teater_category_ids"] == []
    assert meta["extracted_keywords_cs"] == [] and meta["extracted_keywords_en"] == []


def test_ids_stay_out_when_emit_category_ids_is_off(controlled):
    controlled.engine["emit_ids"] = False
    items = _post(kind="controlled").json()["enrichment"]["items"]
    assert all("teater_category_ids" not in item for item in items)
    assert items[1]["teater_category"] == "zámek"  # the qualifier is stripped regardless


def test_the_entities_the_vocabulary_knows_get_a_pid_and_no_other_field_changes(controlled):
    record = _post(kind="controlled").json()["document_json"]
    church, place = record["entities"]
    assert church["pid"]["amcr"] == "https://api.aiscr.cz/id/HES-000021"
    assert church["pid"]["aat"] == "http://vocab.getty.edu/aat/300007466"
    assert {k: v for k, v in church.items() if k != "pid"} == RECORD["entities"][0]
    assert "pid" not in place  # Praha is not an archaeological term: no row of nulls
    assert record["assembled"]["blocks"]["entities"]["program"] == "keyword-extract"


def test_the_model_is_sent_the_configured_prompt_and_one_marked_line_in_its_context(controlled):
    _post(kind="controlled")
    system, user = controlled.chat.calls[0]
    assert system["content"] == controlled.engine["prompt"]
    # llm_config.txt's PROMPT_GEO_GUARDRAIL=preference: the relaxed wording, not the strict one.
    assert "Select a geographic, ethnic or dynastic term only when" in system["content"]
    assert "NEVER select a country name" not in system["content"]
    assert "THEMATIC VOCABULARY" in system["content"]
    assert (
        "<target_line> >>> [P1 L1] Výzkum odhalil základy gotického kostela. </target_line>"
        in user["content"]
    )
    assert "garbage" not in user["content"]  # a Trash neighbour is not context either


def test_kind_both_returns_both_kinds_apart(controlled, monkeypatch):
    import keywords

    def yake(text, num_keywords, lang="cs", max_words=3, source="text"):
        return [("keramika", 0.9), ("zámek", 0.5)][:num_keywords]

    monkeypatch.setattr(keywords, "_yake_from_text", yake)
    body = _post(kind="both", method="yake", num_keywords="2").json()
    assert [k["kind"] for k in body["kinds"]] == ["statistical", "controlled"]
    assert all(k["status"] == "ok" for k in body["kinds"])
    assert {k["method"] for k in body["keywords"]} == {"yake"}
    assert body["enrichment"]["items"] and "keywords" not in body["document_json"]


def test_every_call_failing_is_a_502_for_the_controlled_kind_alone(controlled, monkeypatch):
    monkeypatch.setenv("LLM_MAX_CONSECUTIVE_ERRORS", "2")

    def failing(_messages):
        raise RuntimeError("OpenRouter request failed after 3 attempts: HTTP 503")

    controlled.chat.reply = failing
    response = _post(kind="controlled")
    assert response.status_code == 502
    assert "after 3 attempts" in response.json()["detail"]
    assert len(controlled.chat.calls) == 2  # given up after LLM_MAX_CONSECUTIVE_ERRORS


def test_with_kind_both_a_failed_controlled_kind_does_not_cost_the_statistical_keywords(
    controlled, monkeypatch
):
    import keywords

    def yake(text, num_keywords, lang="cs", max_words=3, source="text"):
        return [("keramika", 0.9)]

    monkeypatch.setattr(keywords, "_yake_from_text", yake)

    def refused(_messages):
        raise RuntimeError("OpenRouter refused the request: HTTP 401")

    controlled.chat.reply = refused
    body = _post(kind="both", method="yake").json()
    statistical, controlled_kind = body["kinds"]
    assert statistical["status"] == "ok" and body["keywords"]
    assert controlled_kind["status"] == "failed" and "HTTP 401" in controlled_kind["detail"]
    assert "enrichment" not in body and "document_json" not in body


def test_no_record_is_written_when_no_line_reached_the_model(controlled):
    record = {
        **RECORD,
        "lines": [
            {"page": "1", "line": 1, "text": "garbage", "categ": "Trash"},
            {"page": "1", "line": 2, "text": "ab", "categ": "Clear"},
        ],
    }
    body = _post(record, kind="controlled").json()
    assert controlled.chat.calls == []
    assert body["controlled"]["outcome"] == "not-asked"
    assert body["kinds"][0] == {
        "kind": "controlled",
        "status": "ok",
        "detail": "no line passed the quality filter; the model was not asked",
    }
    # Never asked is not "found nothing": no block is written, so no record comes back.
    assert "enrichment" not in body and "document_json" not in body


def test_returned_record_is_schema_checked_and_the_response_says_when_it_is_not(controlled):
    """Layer D on the way out (D4): a record let through because the CALLER's record did not
    validate comes back, with the schema error in a field a client can test (rule 6)."""
    body = _post({**RECORD, "pages": "not-an-array"}, kind="controlled").json()
    assert "pages" in body["document_json_schema_error"]
    assert body["document_json"]["enrichment"]["items"]
    assert body["document_json"]["pages"] == "not-an-array"


def test_layer_d_refusal_is_a_500_not_a_502(controlled, monkeypatch):
    """A record this service built wrong is a defect on THIS side: never blamed on the backend."""
    import llm_client_shared

    monkeypatch.setattr(
        llm_client_shared,
        "schema_gate",
        lambda record, what, baseline=False: None if baseline else "deliberate failure",
    )
    response = _post(kind="controlled")
    assert response.status_code == 500
    assert "schema" in response.json()["detail"]


def test_a_record_keyed_unlike_a_file_name_keeps_its_id(controlled):
    seed_id = "C-202000543A/DT-27"
    body = _post({**RECORD, "doc_id": seed_id}, kind="controlled").json()
    assert body["doc_id"] == seed_id
    assert body["document_json"]["doc_id"] == seed_id
    assert (
        body["document_json"]["enrichment"]["items"][0]["citation"]
        == f"[Source: {seed_id}, Page 1]"
    )


@pytest.mark.parametrize("doc_id", ["../escape", "a/b", "a\\b", "nul\x00", "..", "", "x" * 201, 7])
def test_a_record_id_that_is_not_a_plain_file_name_is_never_a_path(doc_id):
    assert api._record_stem({"doc_id": doc_id}) == "record"
    assert api._record_stem(None) == "record"
    assert api._record_stem({"doc_id": DOC}) == DOC


def test_the_text_endpoint_reads_the_texts_lines_as_one_page(controlled):
    body = client.post(
        "/extract_keywords_text",
        json={"text": "Základy kostela.\n\nZámek na kopci.", "kind": "controlled", "doc_id": "T1"},
    ).json()
    items = body["enrichment"]["items"]
    assert [(i["page"], i["line"], i["teater_category"]) for i in items] == [
        ("1", 1, "kostel"),
        ("1", 2, "zámek"),
    ]
    assert items[0]["citation"] == "[Source: T1, Page 1]"
    assert "document_json" not in body


def test_the_paradata_names_the_blocks_written_and_the_vocabularies_used(controlled):
    body = _post(kind="controlled").json()
    action = body["paradata"]
    names = [entity.get("name") for entity in action["result"]]
    assert f"{DOC}.enrichment.json" in names and "enrichment" in names
    components = {c["name"] for c in action["paradataRecord"]["license_detail"]["components"]}
    assert {"amcr_vocab", "teater_data"} <= components
    assert action["paradataRecord"]["config"]["model"] == "test/model"


def test_info_reports_the_controlled_kind(controlled):
    info = client.get("/info").json()
    assert info["kinds"]["available"] == ["statistical", "controlled"]
    controlled_info = info["controlled"]
    assert controlled_info["ready"] is True and controlled_info["detail"] is None
    assert controlled_info["backend"] == "openrouter" and controlled_info["model"] == "test/model"
    assert controlled_info["vocabulary"]["terms"] == controlled_info["vocabulary"]["prompt_terms"]
    assert controlled_info["prompt"] == {
        "geo_guardrail": "preference",
        "vocabulary_grouping": "facet_sub",
    }
