"""
tests/test_document_record.py
==============================
Tests for the paired per-document record (`atrium_document.py`) as wired into the
service's controlled kind and both batch clients through
`llm_client_shared.write_document_record()` (came with llm-enrich's engine,
atrium-digital-convert 31534d5; atrium-keyword-extract#1).

The record is built by **accretion**: each ATRIUM tool takes the previous version of
the JSON, if it is given one, and returns it with only its own block updated. These
tests pin the two properties that make that safe for this stage specifically:

  * keyword-extract — llm-enrich's successor as the owner of `enrichment` — writes
    `enrichment` (and its own `derived_from`/`regenerable` keys) and **nothing else**:
    an upstream tool's blocks survive verbatim;
  * with no baseline the client still produces a valid standalone record.

Plus the projection from this repo's `*_enriched.json` shapes onto `enrichment.items[]`,
which is the part most likely to drift if the enrichment schema changes.
"""

import json
import sys

import pytest

import llm_client_shared
from llm_client_shared import enrichment_block, write_document_record

atrium_document = pytest.importorskip("atrium_document")
DocumentRecord = atrium_document.DocumentRecord
FILE_SUFFIX = atrium_document.FILE_SUFFIX
load_document = atrium_document.load_document

DOC = "CTX000000001"

# The two record shapes this repo writes to <doc_id>_enriched.json.
DOC_LEVEL = [
    {
        "file_id": DOC,
        "locator": "gotického kostela",
        "page": "1",
        "enrichment": {
            "extracted_keywords_cs": ["gotický kostel"],
            "extracted_keywords_en": ["gothic church"],
            "teater_category": "kostel",
            "confidence_score": 0.95,
        },
    }
]
LINE_LEVEL = [
    {
        "file_id": DOC,
        "page": 1,
        "line": 14,
        "categ": "Text",
        "quality_score": 0.98,
        "original_text": "Výzkum odhalil základy.",
        "enrichment": {
            "extracted_keywords_cs": ["základy"],
            "extracted_keywords_en": ["foundations"],
            "teater_category": "kostel",
            "confidence_score": 0.9,
        },
    }
]


# ──────────────────────────────────────────────────────────────────────────────
# enrichment_block() — projection of both record shapes
# ──────────────────────────────────────────────────────────────────────────────


def test_enrichment_block_flattens_document_level_records():
    item = enrichment_block(DOC, DOC_LEVEL)["items"][0]
    assert item["locator"] == "gotického kostela"
    assert item["page"] == "1"
    # the nested enrichment dict is flattened up into the item
    assert item["teater_category"] == "kostel"
    assert item["extracted_keywords_en"] == ["gothic church"]
    assert item["confidence_score"] == 0.95


def test_enrichment_block_keeps_line_numbers_for_line_level_records():
    item = enrichment_block(DOC, LINE_LEVEL)["items"][0]
    assert item["line"] == 14
    # `page` is a STRING in atrium_document.schema.json, so the projection stringifies the
    # int run_line_level() coerces page_num into (atrium-project#10, D4). This assertion
    # expected the raw int, which is what the record used to carry — and what made every
    # line-level record schema-invalid until the Layer D gate started checking.
    assert item["page"] == "1"
    assert "locator" not in item  # line-level records have none


def test_enrichment_block_adds_page_citation():
    assert enrichment_block(DOC, DOC_LEVEL)["items"][0]["citation"] == f"[Source: {DOC}, Page 1]"


def test_enrichment_block_omits_citation_when_page_unknown():
    records = [{"locator": "x", "page": None, "enrichment": {}}]
    assert "citation" not in enrichment_block(DOC, records)["items"][0]


def test_enrichment_block_tolerates_missing_enrichment_key():
    assert enrichment_block(DOC, [{"locator": "x"}])["items"] == [{"locator": "x"}]


# ──────────────────────────────────────────────────────────────────────────────
# write_document_record() — standalone and accretion behaviour
# ──────────────────────────────────────────────────────────────────────────────


def test_writes_standalone_record_without_baseline(tmp_path):
    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")

    assert path == tmp_path / f"{DOC}{FILE_SUFFIX}"
    record = load_document(str(path))
    assert record["doc_id"] == DOC
    assert record["enrichment"]["items"][0]["teater_category"] == "kostel"
    # rule 3: no baseline → this tool's own part only
    assert record["assembled"]["had_baseline"] is False
    assert "entities" not in record and "pages" not in record


def test_stamps_its_own_block_with_program_and_run_id(tmp_path):
    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1", paradata_ref="p.json")

    stamp = load_document(str(path))["assembled"]["blocks"]["enrichment"]
    assert stamp["program"] == "keyword-extract"
    assert stamp["run_id"] == "R1"
    assert stamp["paradata_ref"] == "p.json"


def test_preserves_upstream_blocks_verbatim(tmp_path):
    """The core accretion guarantee: this stage must not disturb anyone else's block."""
    baseline = tmp_path / f"{DOC}{FILE_SUFFIX}"
    with DocumentRecord(DOC, "nlp-enrich", run_id="R0", out_dir=str(tmp_path)) as up:
        up.set_source(sha256="a" * 64, filename=f"{DOC}.alto.xml", origin="ABBYY-ALTO")
        up.set_block("entities", [{"surface": "gotického kostela", "type_onto": "FAC"}])
        up.merge_block("lines", [{"page": "1", "line": 14, "lemma": "výzkum"}])
    before = json.loads(baseline.read_text(encoding="utf-8"))

    write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")
    after = load_document(str(baseline))

    for block in ("source", "entities", "lines"):
        assert after[block] == before[block], f"{block} was modified by keyword-extract"
    assert after["assembled"]["blocks"]["entities"]["program"] == "nlp-enrich"
    assert after["assembled"]["blocks"]["enrichment"]["program"] == "keyword-extract"
    assert after["enrichment"]["items"][0]["locator"] == "gotického kostela"
    assert after["assembled"]["had_baseline"] is True


def test_records_derived_from_and_no_stored_markdown_path(tmp_path):
    path = write_document_record(
        DOC,
        DOC_LEVEL,
        tmp_path,
        run_id="R1",
        enriched_path=tmp_path / f"{DOC}_enriched.json",
    )
    record = load_document(str(path))

    assert record["derived_from"]["enriched"].endswith(f"{DOC}_enriched.json")
    # a recipe at most, never a stored path to the disposable Markdown itself
    assert not json.dumps(record).count(f"{DOC}.md")


def test_no_markdown_recipe_when_no_markdown_was_fed(tmp_path):
    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")
    assert "regenerable" not in load_document(str(path))


def _seed_lines(tmp_path, doc_id=DOC):
    """A baseline with text in it, as alto-postprocess leaves one: what json_to_md renders."""
    with DocumentRecord(doc_id, "alto-postprocess", run_id="R0", out_dir=str(tmp_path)) as up:
        up.set_source(sha256="a" * 64, filename=f"{doc_id}.alto.xml", origin="ABBYY-ALTO")
        up.set_block("lines", [{"page": "1", "line": 1, "text": "Výzkum odhalil základy."}])


def test_used_markdown_input_writes_self_referential_json_to_md_recipe(tmp_path):
    """A document-level run (real Markdown fed to the LLM, whether from a pre-converted
    PDF/DOCX or an upstream xml_to_md.py TEITOK pass) gets a recipe pointing at THIS
    SAME document JSON via json_to_md — self-sufficient, no external file required."""
    _seed_lines(tmp_path)
    path = write_document_record(
        DOC, DOC_LEVEL, tmp_path, run_id="R1", used_markdown_input=True, detail="minimal"
    )
    recipe = load_document(str(path))["regenerable"]["markdown"]

    assert recipe["from"] == f"{DOC}{FILE_SUFFIX}"
    assert recipe["converter"] == llm_client_shared.JSON_TO_MD_CONVERTER == "json_to_md@1.1"
    assert recipe["detail"] == "minimal"


def test_no_json_to_md_recipe_for_a_record_it_cannot_render(tmp_path):
    """A plain-text upload with no baseline leaves a record with no lines and no text:
    json_to_md refuses that record, so no recipe may promise it (the service wrote one for
    every .txt/.md upload until 2026-09-30)."""
    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1", used_markdown_input=True)
    assert "regenerable" not in load_document(str(path))


def test_json_to_md_recipe_names_the_record_file_when_the_seed_id_differs(tmp_path):
    """#68: the record keeps the seed's doc_id and is written under it, so the recipe's
    `from` must name that file, not one derived from the upload's name."""
    _seed_lines(tmp_path, doc_id="C-202400123A")
    seed = tmp_path / f"C-202400123A{FILE_SUFFIX}"
    seed.rename(tmp_path / f"{DOC}{FILE_SUFFIX}")
    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1", used_markdown_input=True)
    record = load_document(str(path))
    assert record["doc_id"] == "C-202400123A"
    assert record["regenerable"]["markdown"]["from"] == f"C-202400123A{FILE_SUFFIX}"


def test_no_markdown_recipe_for_line_level_run(tmp_path):
    """A line-level run (a record's lines, CSV, TEITOK) never fed Markdown to the LLM, so no
    recipe may claim one can be regenerated — not even over a record json_to_md could render.
    (llm-enrich also wrote a `doc_to_visual_md` recipe for a PDF/DOCX it converted itself; the
    conversion stayed in atrium-digital-convert, and so did that recipe.)"""
    _seed_lines(tmp_path)
    path = write_document_record(DOC, LINE_LEVEL, tmp_path, run_id="R1", used_markdown_input=False)
    assert "regenerable" not in load_document(str(path))


def test_rerun_replaces_only_its_own_block(tmp_path):
    """Granularity: a second run rewrites `enrichment`, not the neighbours."""
    write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")
    path = tmp_path / f"{DOC}{FILE_SUFFIX}"
    with DocumentRecord.open(DOC, "translator", baseline=str(path), out_dir=str(tmp_path)) as tr:
        tr.set_block("translations", {"source_lang": "cs", "target_lang": "en"})

    write_document_record(DOC, LINE_LEVEL, tmp_path, run_id="R2")
    record = load_document(str(path))

    assert record["translations"]["target_lang"] == "en"  # survived
    assert record["enrichment"]["items"][0]["line"] == 14  # replaced
    assert record["assembled"]["blocks"]["enrichment"]["run_id"] == "R2"


def test_license_detail_accretes_into_provenance(tmp_path):
    path = write_document_record(
        DOC,
        DOC_LEVEL,
        tmp_path,
        run_id="R1",
        license_detail={"components": [{"name": "nametag3", "license": "CC BY-NC-SA 4.0"}]},
    )
    provenance = load_document(str(path))["provenance"]

    assert provenance["license"] == "CC BY-NC-SA 4.0"
    assert provenance["contributors"][0]["program"] == "keyword-extract"


# ──────────────────────────────────────────────────────────────────────────────
# Layer D — the schema gate on the write path (atrium-project#10, D4)
# ──────────────────────────────────────────────────────────────────────────────
#
# `validate_document()` existed, was documented as normative in docs/document_schema.md,
# and was called from no production path in any of the five repos. These tests pin the
# ecosystem-wide policy now that write_document_record() applies it:
#
#   * our own invalid output      -> raise, emit nothing;
#   * an invalid inherited baseline -> warn, continue, and demote the check above;
#   * no `jsonschema` installed   -> one loud warning, and still write.
#
# The middle rule is the one that needs a test rather than a comment: refusing to run
# because an upstream tool wrote something invalid would turn one bad record into a
# stalled pipeline, and rule 6 already commits to passing unknown content through.

#: A result whose projection violates the schema: `confidence_score` is capped at 1.
INVALID_RESULTS = [
    {
        "file_id": DOC,
        "locator": "gotického kostela",
        "page": "1",
        "enrichment": {"teater_category": "kostel", "confidence_score": 42},
    }
]

#: A baseline no tool in this repo could have produced — `pages` must be an array.
INVALID_BASELINE = {
    "schema_version": "1.0",
    "record_type": "atrium-document",
    "doc_id": DOC,
    "pages": "not-an-array",
}


def _write_invalid_baseline(tmp_path):
    path = tmp_path / f"{DOC}{FILE_SUFFIX}"
    path.write_text(json.dumps(INVALID_BASELINE), encoding="utf-8")
    return path


def test_refuses_to_emit_its_own_invalid_record(tmp_path):
    """Layer D's actual promise: "no doc.json is emitted if validation fails"."""
    with pytest.raises(RuntimeError, match="refusing to emit"):
        write_document_record(DOC, INVALID_RESULTS, tmp_path, run_id="R1")

    assert not (tmp_path / f"{DOC}{FILE_SUFFIX}").exists()
    # finalize() writes `<path>.tmp` then renames, so a gate that fired too late would
    # leave the temp file behind for the next load_document() to trip over.
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_inherited_baseline_warns_and_still_writes(tmp_path, capsys):
    """An upstream tool's bad record must not stall this stage (rule 6)."""
    _write_invalid_baseline(tmp_path)

    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")

    assert "inherited baseline" in capsys.readouterr().err
    record = load_document(str(path))
    assert record["enrichment"]["items"][0]["teater_category"] == "kostel"  # our part landed
    assert record["pages"] == "not-an-array"  # …and theirs passed through untouched


def test_an_amcr_seed_is_a_valid_baseline_and_keeps_its_identity(tmp_path, capsys):
    """atrium-project#71: a seed (a foreign doc_id and the archive's view of the original) is
    checked against the seed profile, so it is no "invalid baseline", and the gate on this
    tool's own output keeps raising. Its identity survives, and the run's run_uuid is stamped."""
    run_uuid = "urn:uuid:5d1c7f0e-3b9a-4c2e-8f61-0a7d2b4e9c13"
    seed = {
        "doc_id": "AMCR-F-0001",
        "source": {"sha512": "c" * 128, "filename": "zprava.pdf", "media_type": "application/pdf"},
    }
    (tmp_path / f"{DOC}{FILE_SUFFIX}").write_text(json.dumps(seed), encoding="utf-8")

    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1", run_uuid=run_uuid)

    assert "inherited baseline" not in capsys.readouterr().err
    record = load_document(str(path))
    assert record["doc_id"] == seed["doc_id"] and record["source"] == seed["source"]
    assert record["assembled"]["blocks"]["enrichment"]["run_uuid"] == run_uuid
    assert record["provenance"]["contributors"][-1]["run_uuid"] == run_uuid
    atrium_document.validate_document(record)
    # The own-output gate was not demoted: a bad contribution onto a seed is still refused.
    again = tmp_path / "again"
    again.mkdir()
    (again / f"{DOC}{FILE_SUFFIX}").write_text(json.dumps(seed), encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to emit"):
        write_document_record(DOC, INVALID_RESULTS, again, run_id="R2")


def test_inherited_invalidity_demotes_our_own_check_to_a_warning(tmp_path, capsys):
    """With the baseline already broken, refusing to emit would punish this tool for
    somebody else's output — and lose our block as well as theirs."""
    _write_invalid_baseline(tmp_path)

    path = write_document_record(DOC, INVALID_RESULTS, tmp_path, run_id="R1")

    assert "emitting it anyway" in capsys.readouterr().err
    assert path.exists()


def test_missing_jsonschema_degrades_loudly_and_once(tmp_path, capsys, monkeypatch):
    """A gate that quietly becomes a no-op is worse than no gate: you cannot tell the two
    apart from the output. So it announces itself — once per process, not once per
    document — and never turns a missing dependency into a missing record."""
    monkeypatch.setitem(sys.modules, "jsonschema", None)  # `import jsonschema` -> ImportError
    monkeypatch.setattr(llm_client_shared, "_schema_gate_disabled_warned", False)

    first = write_document_record(DOC, INVALID_RESULTS, tmp_path, run_id="R1")
    err = capsys.readouterr().err
    assert "DISABLED" in err and "jsonschema" in err
    assert first.exists()

    write_document_record(DOC, INVALID_RESULTS, tmp_path, run_id="R2")
    assert "DISABLED" not in capsys.readouterr().err


def test_record_validates_against_the_shared_schema(tmp_path):
    """A real gate, not an importorskip.

    `jsonschema` was in no requirements file, so this guarded on
    `pytest.importorskip("jsonschema")` and therefore SKIPPED on a clean venv — the only
    schema check in the repo, silently not running. It is now declared in
    requirements-test.txt and requirements_digital.txt, and the locator lives in
    atrium_document.validate_document() so the hub and tool-repo layouts both resolve.
    """
    from atrium_document import validate_document

    path = write_document_record(DOC, DOC_LEVEL, tmp_path, run_id="R1")
    validate_document(load_document(str(path)))
