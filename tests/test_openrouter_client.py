"""
tests/test_openrouter_client.py
================================
Tests for openrouter_client.py, focused on the 2026-07-03 review-pass fix
for finding #1: --attach-as-file was dead code. _build_attachment_content()
existed and was documented but run_document_level() had no way to receive
it, so the document body was always inlined as plain text and the
file-attachment path did nothing regardless of the flag. These tests
exercise _build_attachment_content() directly, then reproduce the exact
per-document closure _make_doc_builder() builds inside main() to confirm
its output is what actually reaches the chat_fn once wired through
llm_client_shared.run_document_level()'s user_content_builder parameter.
"""

import base64
import json

import pytest

import openrouter_client
from llm_client_shared import run_document_level
from openrouter_client import _build_attachment_content, build_arg_parser

# ── _build_attachment_content ───────────────────────────────────────────────


def test_build_attachment_content_inlines_by_default():
    content = _build_attachment_content("Vyzkum odhalil zaklady.", "sample.md", as_file=False)
    assert content == "DOCUMENT:\nVyzkum odhalil zaklady."


def test_build_attachment_content_as_file_encodes_base64_file_part():
    content = _build_attachment_content("Vyzkum odhalil zaklady.", "sample.md", as_file=True)
    assert isinstance(content, list)
    text_part, file_part = content
    assert text_part == {"type": "text", "text": "DOCUMENT (attached below):"}
    assert file_part["type"] == "file"
    assert file_part["file"]["filename"] == "sample.md"

    data_url = file_part["file"]["file_data"]
    assert data_url.startswith("data:text/markdown;base64,")
    b64_payload = data_url.split(",", 1)[1]
    assert base64.b64decode(b64_payload).decode("utf-8") == "Vyzkum odhalil zaklady."


# ── run_document_level(user_content_builder=...) — finding #1 regression ───


def _fake_empty_items_chat_fn(captured):
    def chat_fn(messages):
        captured.append(messages)
        return json.dumps({"items": []})

    return chat_fn


class _DummyDocModel:
    """Minimal stand-in for build_document_schema()'s DocumentEnrichment —
    only .items is ever read by run_document_level()."""

    items = []

    @classmethod
    def model_validate_json(cls, data):
        return cls()


def test_attach_as_file_reaches_run_document_level_when_wired(tmp_path):
    doc_path = tmp_path / "sample.md"
    doc_path.write_text("Vyzkum odhalil zaklady.", encoding="utf-8")

    captured = []

    def doc_builder(doc_text):
        # exactly the closure _make_doc_builder() returns inside main()
        return _build_attachment_content(doc_text, doc_path.name, True)

    run_document_level(
        doc_path,
        _fake_empty_items_chat_fn(captured),
        "system prompt",
        _DummyDocModel,
        user_content_builder=doc_builder,
    )

    sent_content = captured[0][1]["content"]
    assert isinstance(sent_content, list)  # the file-attachment content part, not inlined text
    assert sent_content[1]["file"]["filename"] == "sample.md"


def test_attach_as_file_flag_defaults_to_false():
    args = build_arg_parser().parse_args([])
    assert args.attach_as_file is False

    args = build_arg_parser().parse_args(["--attach-as-file"])
    assert args.attach_as_file is True


# ── main() end-to-end over a .teitok.xml input — D1 regression ───────────────
#
# atrium-project#10, D1 (P0). `doc_id = f.stem` strips only the LAST extension, so a
# `CTX000000001.teitok.xml` input — one this client's own input filter accepts and its
# docstring advertises — produced the doc_id `CTX000000001.teitok`.
# write_document_record() then looked for a baseline called
# `CTX000000001.teitok.document.json`, which no upstream tool ever writes, so
# DocumentRecord.open() fell back to rule 3 and DISCARDED every upstream block — pages,
# lines, entities, translations — emitting an orphan record under an id nothing else in the
# pipeline uses. Nothing caught it: this file referenced neither document_json, nor doc_id,
# nor .teitok.xml, and the E2E smoke feeds a single-dot `.csv` whose `.stem` happens to be
# right. The test below runs the real main() against a pre-seeded baseline, which is the
# only shape that reproduces it.


def _run_main(env, extra=()):
    openrouter_client.main(
        [
            "--config",
            str(env.config),
            "--input",
            str(env.teitok),
            "--output-dir",
            str(env.output_dir),
            "--model",
            "test/model",
            "--api-key",
            "test-key",
            *extra,
        ]
    )


def test_teitok_run_preserves_every_upstream_block(remote_client_env, seeded_baseline, stub_llm):
    """The whole point of the accretion contract: this stage adds `enrichment` and touches
    nothing else. Before the fix this assertion failed on all three blocks at once."""
    from atrium_document import load_document

    env = remote_client_env
    stub_llm(openrouter_client)

    _run_main(env, ["--document-json-dir", str(env.record_dir)])

    assert env.baseline.exists(), (
        f"no record at the canonical doc_id; dir holds "
        f"{sorted(p.name for p in env.record_dir.iterdir())}"
    )
    assert not env.forked_record.exists(), "record written under the forked `.teitok` doc_id"

    record = load_document(str(env.baseline))
    assert record["doc_id"] == env.doc_id
    assert record["assembled"]["had_baseline"] is True
    for block in ("pages", "lines", "entities"):
        assert block in record, f"upstream {block!r} block was discarded"
    assert record["lines"][0]["text"].startswith("Výzkum odhalil")
    assert record["entities"][0]["surface"] == "gotického kostela"
    assert record["source"]["origin"] == "ABBYY-ALTO"
    # …and this stage's own contribution really is there, so the test is not passing by
    # having skipped the write altogether.
    assert record["enrichment"]["items"][0]["extracted_keywords_en"] == ["church"]
    assert record["assembled"]["blocks"]["enrichment"]["program"] == "keyword-extract"


def test_teitok_run_names_its_enriched_output_by_the_canonical_doc_id(
    remote_client_env, seeded_baseline, stub_llm
):
    """The same derivation names `<doc_id>_enriched.json`, so the fix is visible in the
    CLI's own output too — `CTX000000001.teitok_enriched.json` was the old name."""
    env = remote_client_env
    stub_llm(openrouter_client)

    _run_main(env, ["--document-json-dir", str(env.record_dir)])

    assert (env.output_dir / f"{env.doc_id}_enriched.json").exists()


def test_document_json_single_file_pair_round_trips_the_baseline(
    remote_client_env, seeded_baseline, stub_llm
):
    """The --document-json/--document-json-out convenience pair (issue #13) copies the
    baseline into a scratch dir under the derived doc_id, so it forks on exactly the same
    name and had to be fixed with the loop."""
    from atrium_document import load_document

    env = remote_client_env
    stub_llm(openrouter_client)
    out_path = env.root / "5_llm.json"

    _run_main(
        env,
        ["--document-json", str(seeded_baseline), "--document-json-out", str(out_path)],
    )

    assert out_path.exists()
    record = load_document(str(out_path))
    assert record["doc_id"] == env.doc_id
    for block in ("pages", "lines", "entities"):
        assert block in record, f"upstream {block!r} block was discarded"


def test_document_json_single_file_pair_enriches_a_seed_keyed_unlike_the_input(
    remote_client_env, seeded_baseline, stub_llm
):
    """(atrium-project#68) The same pair with a seed keyed by an AMČR file id, not by the
    input's name. The record was written under the seed's id while `--document-json-out`
    received the file named after the input: the untouched seed, without `enrichment`."""
    from atrium_document import load_document

    env = remote_client_env
    stub_llm(openrouter_client)
    seed_id = "C-202000543A-DT-27"
    seed = json.loads(seeded_baseline.read_text(encoding="utf-8"))
    seed["doc_id"] = seed_id
    seed_path = env.root / "amcr-seed.document.json"
    seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    out_path = env.root / "5_llm.json"

    _run_main(env, ["--document-json", str(seed_path), "--document-json-out", str(out_path)])

    record = load_document(str(out_path))
    assert record["doc_id"] == seed_id
    for block in ("pages", "lines", "entities"):
        assert block in record, f"upstream {block!r} block was discarded"
    assert record["enrichment"]["items"][0]["extracted_keywords_en"] == ["church"]


# ── the three zero-record outcomes are three different artifacts ─────────────
#
# atrium-project#49. `--document-json` seeds a scratch dir with the CALLER'S baseline and
# the run's tail used to `glob` that dir and copy whatever it found to
# `--document-json-out`. A glob cannot tell a record the stage WROTE from the baseline it
# was HANDED, so all three of these shipped the untouched baseline, printed
# "[document] Record written", and exited 0:
#
#   * the model was asked and located nothing   -> a correct, empty enrichment
#   * every inference call failed               -> no verdict at all
#   * nothing ever reached the model            -> no verdict at all
#
# The born-digital nightly (atrium-project run 34090340995) hit the first one against a
# fixture with no archaeology in it and reported it as "'enrichment' block missing from
# llm-enrich stage" — the consumer guessing, because the artifact carried no way to know.


def _stub_line_level(monkeypatch, results, **stat_overrides):
    """Replace the line-level driver with one that returns a chosen outcome."""
    stats = {"processed": len(results), "skipped_filter": 0, "skipped_error": 0, "aborted": 0}
    stats.update(stat_overrides)
    stats.setdefault("attempted", len(results))

    def fake_run_line_level(*_args, **_kwargs):
        return list(results), dict(stats)

    monkeypatch.setattr(openrouter_client, "run_line_level", fake_run_line_level)


def test_asked_and_found_nothing_still_stamps_an_empty_enrichment_block(
    remote_client_env, seeded_baseline, stub_llm, monkeypatch
):
    """The atrium-project#49 case, and the reason the fix is not "assert less".

    "the stage ran and found nothing" and "the stage never ran" are different facts and
    the record has to be able to hold both. `assembled.blocks` is the record's account of
    which tool contributed what, so the only honest encoding of the first is an
    `enrichment` block with an empty `items` list, stamped by this stage — which is exactly
    what atrium-project's e2e_assert.py checks for.
    """
    from atrium_document import load_document

    env = remote_client_env
    stub_llm(openrouter_client)
    _stub_line_level(monkeypatch, [], attempted=3)
    out_path = env.root / "5_llm.json"

    openrouter_client.main(
        [
            "--config",
            str(env.config),
            "--input",
            str(env.teitok),
            "--output-dir",
            str(env.output_dir),
            "--model",
            "test/model",
            "--api-key",
            "test-key",
            "--document-json",
            str(seeded_baseline),
            "--document-json-out",
            str(out_path),
        ]
    )

    assert out_path.exists(), "a completed pass must emit its record even with no items"
    record = load_document(str(out_path))
    assert record["enrichment"] == {"items": []}
    assert record["assembled"]["blocks"]["enrichment"]["program"] == "keyword-extract"
    # Accretion still holds: contributing an empty block must not cost the upstream ones.
    for block in ("pages", "lines", "entities"):
        assert block in record, f"upstream {block!r} block was discarded"
    # No records means no `*_enriched.json`, so nothing may claim one.
    assert not (env.output_dir / f"{env.doc_id}_enriched.json").exists()
    assert "enriched" not in str(record.get("derived_from") or "")


def test_failed_inference_never_ships_the_baseline_as_this_stage_output(
    remote_client_env, seeded_baseline, stub_llm, monkeypatch, capsys
):
    """No verdict -> no record, and a non-zero exit. Previously: baseline out, exit 0."""
    env = remote_client_env
    stub_llm(openrouter_client)
    _stub_line_level(monkeypatch, [], attempted=3, skipped_error=3, aborted=1)
    out_path = env.root / "5_llm.json"

    with pytest.raises(SystemExit) as excinfo:
        openrouter_client.main(
            [
                "--config",
                str(env.config),
                "--input",
                str(env.teitok),
                "--output-dir",
                str(env.output_dir),
                "--model",
                "test/model",
                "--api-key",
                "test-key",
                "--document-json",
                str(seeded_baseline),
                "--document-json-out",
                str(out_path),
            ]
        )

    assert excinfo.value.code == 1
    assert not out_path.exists(), "the caller's own baseline was re-emitted as our output"
    assert "contributed no enrichment verdict" in capsys.readouterr().err


def test_input_that_never_reached_the_model_writes_no_record(
    remote_client_env, seeded_baseline, stub_llm, monkeypatch
):
    """Every row dropped by the quality filter is not an empty enrichment.

    The model was never consulted, so there is no verdict to record and an empty block
    would claim one. This is the split `attempted` exists for — `processed` is 0 here and
    0 in the asked-and-found-nothing case above.
    """
    env = remote_client_env
    stub_llm(openrouter_client)
    _stub_line_level(monkeypatch, [], attempted=0, skipped_filter=3)
    out_path = env.root / "5_llm.json"

    with pytest.raises(SystemExit) as excinfo:
        openrouter_client.main(
            [
                "--config",
                str(env.config),
                "--input",
                str(env.teitok),
                "--output-dir",
                str(env.output_dir),
                "--model",
                "test/model",
                "--api-key",
                "test-key",
                "--document-json",
                str(seeded_baseline),
                "--document-json-out",
                str(out_path),
            ]
        )

    assert excinfo.value.code == 1
    assert not out_path.exists()


# ── the prompt, the ids and the record input (atrium-keyword-extract#1, #2) ───────────────
#
# llm-enrich's copy of these clients sent a prompt of its own: the strict geographic
# guardrail after the vocabulary had reinstated the geographic terms, no PROMPT_* flag, no
# teater_category_ids, and a bracketed homonym's qualifier left on the label. They now send
# the GPU path's prompt (prompts/system_prompt.txt) and attach what llm_run.py attaches.


def _enriched(env):
    return json.loads((env.output_dir / f"{env.doc_id}_enriched.json").read_text(encoding="utf-8"))


def test_the_model_is_sent_the_templates_prompt_with_the_configured_guardrail(
    remote_client_env, stub_llm
):
    env = remote_client_env
    sent = stub_llm(openrouter_client)

    _run_main(env)

    system = sent[0][0]["content"]
    assert "Select a geographic, ethnic or dynastic term only when" in system  # preference
    assert "NEVER select a country name" not in system  # the strict wording llm-enrich sent
    assert "--- Site Types / sídlo elity ---" in system  # PROMPT_VOCAB_GROUPING=facet_sub
    assert "- kostel (church)" in system and system.rstrip().endswith("}")  # the examples close it


def test_the_results_carry_the_ids_behind_the_label(remote_client_env, stub_llm):
    env = remote_client_env
    stub_llm(openrouter_client)

    _run_main(env)

    enrichment = _enriched(env)[0]["enrichment"]
    assert enrichment["teater_category"] == "kostel"
    assert enrichment["teater_category_ids"] == [
        {"source": "amcr", "id": "HES-000021"},
        {"source": "teater", "id": "1333"},
    ]


def test_a_qualified_homonym_comes_back_bare_with_its_own_ids(remote_client_env, stub_llm):
    env = remote_client_env
    stub_llm(openrouter_client, category="zámek (sídlo elity)")

    _run_main(env)

    enrichment = _enriched(env)[0]["enrichment"]
    assert enrichment["teater_category"] == "zámek"
    assert enrichment["teater_category_ids"] == [{"source": "teater", "id": "1439"}]


def test_emit_category_ids_false_leaves_the_ids_out(remote_client_env, stub_llm):
    env = remote_client_env
    env.config.write_text(
        env.config.read_text(encoding="utf-8") + "EMIT_CATEGORY_IDS=false\n", encoding="utf-8"
    )
    stub_llm(openrouter_client)

    _run_main(env)

    assert "teater_category_ids" not in _enriched(env)[0]["enrichment"]


def test_a_prompt_that_contradicts_the_vocabulary_refuses_to_start(
    remote_client_env, stub_llm, capsys
):
    """No PROMPT_GEO_GUARDRAIL in the config renders the strict wording, which forbids what
    the reinstated vocabulary offers (taxonomy_config.json: geo_guardrail inactive)."""
    env = remote_client_env
    env.config.write_text(
        env.config.read_text(encoding="utf-8").replace("PROMPT_GEO_GUARDRAIL=preference\n", ""),
        encoding="utf-8",
    )
    sent = stub_llm(openrouter_client)

    with pytest.raises(SystemExit) as excinfo:
        _run_main(env)

    assert excinfo.value.code == 1
    assert "contradicts the vocabulary" in capsys.readouterr().err
    assert sent == []


def test_a_record_is_read_through_its_lines_and_is_its_own_baseline(
    remote_client_env, seeded_baseline, stub_llm
):
    """The record after nlp-enrich is this stage's input: its lines are the rows, and with
    `--document-json-out` alone the record it came from is the one that gets the block."""
    from atrium_document import load_document

    env = remote_client_env
    sent = stub_llm(openrouter_client)
    record_input = env.root / f"{env.doc_id}.document.json"
    record_input.write_text(seeded_baseline.read_text(encoding="utf-8"), encoding="utf-8")
    out_path = env.root / "5_kw.json"

    openrouter_client.main(
        [
            "--config",
            str(env.config),
            "--input",
            str(record_input),
            "--output-dir",
            str(env.output_dir),
            "--model",
            "test/model",
            "--api-key",
            "test-key",
            "--document-json-out",
            str(out_path),
        ]
    )

    assert (
        "<target_line> >>> [P1 L1] Výzkum odhalil základy gotického kostela."
        in (sent[0][1]["content"])
    )
    record = load_document(str(out_path))
    assert record["doc_id"] == env.doc_id
    for block in ("pages", "lines", "entities"):
        assert block in record, f"upstream {block!r} block was discarded"
    item = record["enrichment"]["items"][0]
    assert (item["page"], item["line"], item["teater_category"]) == ("1", 1, "kostel")
    assert item["teater_category_ids"][0] == {"source": "amcr", "id": "HES-000021"}


def test_a_pdf_is_not_read_here_and_the_error_says_where_to_convert_it(
    remote_client_env, stub_llm, capsys
):
    env = remote_client_env
    stub_llm(openrouter_client)
    pdf = env.root / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    with pytest.raises(SystemExit) as excinfo:
        openrouter_client.main(
            ["--config", str(env.config), "--input", str(pdf), "--model", "m", "--api-key", "k"]
        )

    assert excinfo.value.code == 1
    assert "atrium-digital-convert" in capsys.readouterr().err


def test_a_key_in_the_config_file_never_reaches_the_paradata(remote_client_env, stub_llm):
    """The client reads OPENROUTER_API_KEY from llm_config.txt when it is not passed, and
    the paradata logged the whole file, key included; paradata is published with the record."""
    env = remote_client_env
    env.config.write_text(
        env.config.read_text(encoding="utf-8") + "OPENROUTER_API_KEY=sk-from-the-config\n",
        encoding="utf-8",
    )
    stub_llm(openrouter_client)

    openrouter_client.main(
        [
            "--config",
            str(env.config),
            "--input",
            str(env.teitok),
            "--output-dir",
            str(env.output_dir),
            "--model",
            "test/model",
        ]
    )

    written = list((env.root / "paradata").glob("*.json"))
    assert written, "the run wrote no paradata"
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "sk-from-the-config" not in text
        assert json.loads(text)["config"]["model"] == "test/model"
