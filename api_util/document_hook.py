import logging
import os
import sys
from typing import Any, Dict, List, Optional

from atrium_document import DocumentRecord, load_document, validate_baseline

# Aliased on import, deliberately (atrium-project#10, D4). This repo has a SECOND,
# unrelated `validate_document()` in api_util/validate_teitok_xml.py — TEITOK XML
# against the XSD (issue #28) — and the two are different contracts that happen to
# share a name: one returns a list of diagnostics, the other raises. Importing the
# hub one under an explicit name means neither a reader nor a future edit can mistake
# which gate is being invoked here.
from atrium_document import validate_document as validate_document_record

from .ner_types import coarse_type, tagset
from .teitok_alto import group_ner_spans, has_coords, parse_and_align_conllu

logger = logging.getLogger(__name__)

#: (atrium-project#10, D4) One-shot latch for the "validation is unavailable" warning.
#: The gate below runs once per document and api_4_stats.sh walks a whole corpus, so
#: repeating the same line per record would bury every other diagnostic of the run.
#: Loud once is the point; loud once per document is noise that gets filtered.
_VALIDATION_UNAVAILABLE_WARNED = False


def _warn(message: str) -> None:
    """stderr in atrium_document's own ``[document]`` voice.

    print(), not ``logger.warning()``: these lines interleave with the module's own
    unconditional stderr diagnostics ("baseline … not found", "contributed no block",
    "Record written →"), and the accretion trace of a run is only readable if all of
    it lands in one stream with one prefix. The ``logger`` above stays for this
    module's own advisory messages.
    """
    print(f"[document] WARNING – {message}", file=sys.stderr)


def _warn_validation_unavailable(reason: str) -> None:
    """(D4) The gate could not run at all. Announced ONCE, loudly, never silently:
    ``validate_document()`` deliberately raises rather than passing when ``jsonschema``
    is absent, because a gate that quietly becomes a no-op is indistinguishable from a
    passing one. Degrading loudly keeps that property while honouring rule 3 — a
    missing optional dependency must not stop a standalone run producing its output.
    """
    global _VALIDATION_UNAVAILABLE_WARNED
    if _VALIDATION_UNAVAILABLE_WARNED:
        return
    _VALIDATION_UNAVAILABLE_WARNED = True
    _warn(
        f"schema validation is DISABLED for this run — {reason}. This is a DEGRADED "
        f"gate, not a pass: records are being written unchecked. Install the missing "
        f"dependency (requirements.txt declares jsonschema for exactly this call)."
    )


def _baseline_is_invalid(path: Optional[str]) -> bool:
    """Validate the INHERITED baseline before nlp-enrich accretes onto it (D4).

    Warns and returns True on a schema failure rather than refusing to run: the defect
    belongs to whichever upstream tool wrote it, and turning one bad record into a
    stalled pipeline is worse than passing it through (rule 6 already commits to
    carrying unknown content forward). The flag downgrades the own-output gate below
    from raise to warn, so this stage is not blamed for a defect it inherited.

    A baseline that cannot be READ at all is not this function's problem —
    ``DocumentRecord.open()`` reports on it a few lines later, with the right message.

    An AMČR seed (``doc_id`` and ``source`` only, atrium-project#71) is checked against the
    seed profile (``validate_baseline``), not the full schema it could never pass: it used to
    be reported here as an invalid baseline, which also demoted this stage's own output gate.
    """
    if not path or not os.path.exists(path):
        return False
    try:
        record = load_document(path)
    except Exception:
        return False
    try:
        validate_baseline(record)
    except (RuntimeError, FileNotFoundError) as exc:
        # RuntimeError = jsonschema missing; FileNotFoundError = the schema itself was
        # not vendored next to the module. Neither means "the record is bad".
        _warn_validation_unavailable(str(exc))
        return False
    except Exception as exc:
        _warn(
            f"inherited baseline {path} does not validate against "
            f"atrium_document.schema.json — {exc}. Accreting onto it anyway; this "
            f"stage's own output gate is downgraded to a warning as a result."
        )
        return True
    return False


def _validate_own_output(doc: DocumentRecord, baseline_was_invalid: bool) -> None:
    """The Layer D gate on nlp-enrich's own output, called before ``finalize()`` (D4).

    Raises on a schema failure so the record is never emitted — ``DocumentRecord``'s
    context manager only finalises when the body leaves without an exception, so
    raising here is what makes "no doc.json is emitted if validation fails" true. The
    one exception is an already-invalid baseline: the failure is then almost certainly
    the inherited one, and refusing to write would discard this stage's work along with
    the upstream stage's.
    """
    try:
        validate_document_record(doc.to_dict())
    except (RuntimeError, FileNotFoundError) as exc:
        _warn_validation_unavailable(str(exc))
    except Exception as exc:
        if baseline_was_invalid:
            _warn(
                f"nlp-enrich output for {doc.doc_id} does not validate — {exc}. "
                f"Emitting it anyway: the inherited baseline was already invalid, so "
                f"this is very likely not our defect to refuse."
            )
            return
        raise


def _augment_tokens_with_position(tokens: List[dict]) -> None:
    """
    Attach ``_page`` (str), ``_line`` (int, 1-based, sequential per page) and
    ``_char_start``/``_char_end`` (offset within that line's reconstructed text) to
    each token IN PLACE, walking ``tokens`` in document order.

    ALTO's own ``line_id`` (carried on ``tok["_bbox"]["line_id"]`` by
    ``parse_and_align_conllu``/``_align_tokens_to_alto``) is an arbitrary XML ID, not
    a sequential number — it is only used here to detect "still the same line as the
    previous token" while assigning a stable per-page sequential line number as new
    line_ids are first encountered in token order. This is internally consistent
    across re-runs of nlp-enrich against the same CoNLL-U/ALTO pair (which is what
    the entities[] merge key needs — it does not need to match alto-postprocess's own
    line numbering, since nlp-enrich is entities[]'s sole owner).

    Tokens with no matched ALTO bbox (alignment miss, or no layout at all) are grouped onto
    one synthetic line of their page (``_page_idx``, resolved by ``parse_and_align_conllu``)
    rather than dropped, so entities from an unaligned document still get a valid (page,
    line) pair instead of crashing later.

    Offsets count the *surface* text, the text the page shows: the syntactic words of a
    multi-word token (``tok["_surface"]``, e.g. "abych" = aby + bych) all get the span of
    that one surface token, and the cursor advances once for it.
    """
    page_line_seq: Dict[str, Dict[Any, int]] = {}
    page_next_line: Dict[str, int] = {}
    last_key = None
    last_unit = None
    prev: Dict[str, Any] = {}
    cursor = 0

    for tok in tokens:
        unit = tok.get("_surface")
        if unit is not None and unit is last_unit and unit.get("mwt"):
            for key in ("_page", "_line", "_char_start", "_char_end"):
                tok[key] = prev[key]
            continue
        last_unit = unit
        bbox = tok.get("_bbox") or {}
        # _page_idx: the page parse_and_align_conllu resolved (layout, else rows) -- the
        # page the writer puts the token on; the box's page is the same whenever there is one
        page_idx = tok.get("_page_idx") or bbox.get("page_idx")
        line_id = bbox.get("line_id")
        page = str(page_idx) if page_idx is not None else "1"
        line_marker = line_id if line_id is not None else f"__noalign_{page}"

        page_line_seq.setdefault(page, {})
        page_next_line.setdefault(page, 1)
        if line_marker not in page_line_seq[page]:
            page_line_seq[page][line_marker] = page_next_line[page]
            page_next_line[page] += 1
        line_num = page_line_seq[page][line_marker]

        key = (page, line_marker)
        if key != last_key:
            cursor = 0

        surface = unit if unit is not None and unit.get("mwt") else tok
        form = surface.get("form", "")
        tok["_page"] = page
        tok["_line"] = line_num
        tok["_char_start"] = cursor
        tok["_char_end"] = cursor + len(form)

        cursor = tok["_char_end"] + (1 if surface.get("space_after", True) else 0)
        last_key = key
        prev = tok


def _surface_text(span_tokens: List[dict]) -> str:
    """The entity's text as the document shows it: real spacing (``SpaceAfter=No`` kept,
    e.g. "č.") and multi-word tokens as their one surface form."""
    parts = []
    last_unit = None
    for tok in span_tokens:
        unit = tok.get("_surface")
        if unit is not None and unit.get("mwt"):
            if unit is last_unit:
                continue
            last_unit = unit
            parts.append((unit.get("form", ""), unit.get("space_after", True)))
        else:
            last_unit = None
            parts.append((tok.get("form", ""), tok.get("space_after", True)))
    text = ""
    for i, (form, space_after) in enumerate(parts):
        text += form
        if space_after and i < len(parts) - 1:
            text += " "
    return text


def run_document_hook(
    doc_id: str,
    teitok_path: str,
    conllu_path: str,
    baseline_json: Optional[str],
    out_json: str,
    run_id: str,
    paradata_ref: str,
    license_detail: Dict[str, Any],
    alto_path: Optional[str] = None,
    include_lines: bool = False,
    rows: Optional[list] = None,
    run_uuid: Optional[str] = None,
):
    """
    Integrates nlp-enrich outputs (entities, TEITOK refs) into the AtriumDocument pair.

    ``run_id``, ``run_uuid`` and ``paradata_ref`` name the stage's run (its paradata state):
    ``run_uuid`` (atrium-project#71) is stamped with every block and the contributor entry,
    and it is the ``@id`` of the run's CreateAction.

    ``alto_path`` (ALTO or a converted TEITOK layout) gives each token its page, line and
    bbox; ``rows`` (stage 1's rows file, ``api_util/page_rows.py``) gives page and line where
    there is no layout -- the same pages the TEITOK writer uses (issue #38, A). With
    neither, every token is on page "1", on one synthetic line per page.
    """
    # 1. Parse tokens & bboxes (reusing the unified teitok_alto refactor). This
    # returns {"sentences": [...], ...} — NOT a flat token list — so it must be
    # flattened the same way parse_and_align_conllu itself does internally before
    # bbox alignment.
    parsed = parse_and_align_conllu(conllu_path, alto_path=alto_path, doc_id=doc_id, rows=rows)
    tokens: List[dict] = (
        [tok for sent in parsed["sentences"] for tok in sent["tokens"]] if parsed else []
    )
    _augment_tokens_with_position(tokens)

    entities = []
    name_counter = 1

    spans = group_ner_spans(tokens)

    for span in spans:
        if span.get("kind") != "name":
            continue  # non-entity tokens are grouped too; only "name" spans are entities

        span_tokens = span["tokens"]
        surface = _surface_text(span_tokens)
        lemma = " ".join(t["lemma"] for t in span_tokens)

        # a converted layout source can place a token without boxing it (has_coords)
        boxed = [t["_bbox"] for t in span_tokens if has_coords(t.get("_bbox"))]
        x_mins = [float(b["left"]) for b in boxed]
        y_mins = [float(b["top"]) for b in boxed]
        x_maxs = [float(b["right"]) for b in boxed]
        y_maxs = [float(b["bottom"]) for b in boxed]

        bbox = None
        if x_mins and y_mins and x_maxs and y_maxs:
            bbox = [min(x_mins), min(y_mins), max(x_maxs), max(y_maxs)]

        first, last = span_tokens[0], span_tokens[-1]
        page = first.get("_page", "1")
        line = first.get("_line", 0)
        char_span = [first.get("_char_start", 0), last.get("_char_end", 0)]

        # span["code"] is the BIO-stripped NE code (_bio_to_code). ner_types is the one
        # label map the TEITOK writer uses too, so `type_teitok` here and `<name type>`
        # in the XML always agree. Every CNEC 2.0 code (p, pf, gc, ty, n_, ...) is
        # recognised as CNEC; any other label (OntoNotes PERSON/GPE/..., the
        # archaeological model's LOCATION/ARTEFACT/...) goes to `type_onto`, the schema's
        # field for non-CNEC labels.
        raw_type = span.get("code", "")
        is_cnec = tagset(raw_type) == "cnec"
        type_onto = raw_type if not is_cnec else None
        type_cnec = raw_type if is_cnec else None

        entity_record = {
            "surface": surface,
            "lemma": lemma,
            "type_teitok": coarse_type(raw_type),
            "page": str(page),
            "line": int(line),
            "char_span": char_span,
            # The <name id> the writer gives this span (assigned once, in
            # parse_and_align_conllu); a TEITOK-local id, like teitok_surface below.
            "teitok_ref": first.get("_name_id") or f"n-{name_counter}",
        }
        # Only the tagset that actually applies is written — never the other one as an
        # explicit null (atrium-project#10, caught by D4's gate the moment it was wired).
        # `entities[].type_onto` and `.type_cnec` are typed `{"type": "string"}` in
        # atrium_document.schema.json with no null member, so a record carrying
        # `"type_cnec": null` FAILS validation. Every real NameTag run produces exactly
        # one tagset, so before this the hook emitted a schema-invalid record for every
        # document that had a single entity — invisible only because nothing validated.
        # Absent is also the truthful encoding: the field does not apply, rather than
        # applying with an empty value.
        if type_onto is not None:
            entity_record["type_onto"] = type_onto
        if type_cnec is not None:
            entity_record["type_cnec"] = type_cnec
        if bbox:
            entity_record["bbox"] = bbox
        # `pid` is deliberately NOT set here (atrium-project#10, D10): it is
        # llm-enrich's field in BLOCK_FIELD_OWNERS["entities"], and merge_block()
        # filtered the placeholder out on every single call — so it never persisted a
        # wrong value, but it did invite a future edit to assume ownership. With the
        # assert_fields_survived() call below in place it would now raise, which is the
        # mechanism working exactly as intended.

        entities.append(entity_record)
        name_counter += 1

    # 2. Document Integration via Accretion
    #
    # This function is the repo's single document-write chokepoint — api_4_stats.sh →
    # summarize_nt_udp.process_single_document() is the only caller — so it is also
    # where the Layer D guarantees are enforced once for every stage that reaches the
    # record (atrium-project#10, D4/D8):
    #
    #   * the inherited baseline is validated and a failure only WARNED about;
    #   * every merge_block() is followed by assert_fields_survived(), which RAISES
    #     when a field handed in was filtered away;
    #   * nlp-enrich's own output is validated before finalize(), and a failure RAISES
    #     so nothing is emitted.
    baseline_was_invalid = _baseline_is_invalid(baseline_json)

    with DocumentRecord.open(
        doc_id,
        "nlp-enrich",
        baseline=baseline_json,
        run_id=run_id,
        run_uuid=run_uuid,
        paradata_ref=paradata_ref,
    ) as doc:
        if license_detail:
            doc.add_license_detail(license_detail)

        if teitok_path:
            doc.add_derived_from("teitok", teitok_path)

        # entities[] is field-split (llm-enrich writes pid; the translator's
        # translation_en is granted but reserved and unwritten, atrium-project#70) —
        # merge_block(), never set_block(), or a re-run of nlp-enrich alone erases
        # every downstream contribution on the same rows.
        doc.merge_block("entities", entities)
        # (#10 D8) merge_block()'s field filtering is silent by design, and that
        # silence is how a wrong grant produced rows stripped down to their key that
        # still validated (entities[] requires nothing at all). Deliberately the
        # raising form rather than the blunt global warn_dropped_fields=True: it fires
        # only when THIS repo hands over a field its own declared grant in
        # BLOCK_FIELD_OWNERS does not cover, which is a code bug here, not data
        # variance — so a red test is the correct outcome, at dev time.
        doc.assert_fields_survived("entities", entities)

        pages_present = sorted({t.get("_page", "1") for t in tokens})
        # The <surface id> the writer gives each page (TEITOK-local, "facs-P"). The writer
        # only has surfaces for ALTO pages -- a text-only document (no ALTO, e.g. /enrich)
        # has no <facsimile>, and a teitok_surface there would point at nothing.
        surfaces = {str(pg["idx"]) for pg in (parsed or {}).get("alto_pages", [])}
        page_updates = [
            {"page": p, "teitok_surface": f"facs-{p}"} for p in pages_present if p in surfaces
        ]
        doc.merge_block("pages", page_updates)
        # nlp-enrich owns exactly one field in pages[] — teitok_surface — so this is
        # the assertion most likely to catch a well-meaning future edit that adds a
        # page-level field here instead of to the originator that owns it.
        doc.assert_fields_survived("pages", page_updates)

        if include_lines:
            logger.warning(
                "DANGER: `lines` block merged from nlp-enrich. This may cause silent duplicate rows due to layout reordering mismatches with alto-postprocess."
            )
            # Line extraction logic omitted by default to protect the integrity of the OCR pipeline layout
            # NOTE: whoever enables this must add the matching
            # doc.assert_fields_survived("lines", line_updates) after the merge, as the
            # two blocks above do — nlp-enrich's lines[] grant is
            # ["lemma", "upos", "feats", "teitok_ref", "bbox"] and `text` is
            # alto-postprocess's, which merge_block() would drop in silence (#10 D8).
            pass

        # Layer D on the way out (#10 D4). Before finalize(), inside the `with` body:
        # DocumentRecord.__exit__ only finalises when the body left without an
        # exception, so raising HERE is what makes "no doc.json is emitted if
        # validation fails" true, rather than emitting and then complaining.
        _validate_own_output(doc, baseline_was_invalid)

        # Rule: the caller decides where the record lands (in-place accretion or a
        # fresh path) — write there explicitly rather than falling through to
        # __exit__'s implicit out_dir="." default, which silently drops the record
        # in the process CWD instead of the shared document_json_dir.
        doc.finalize(out_json)
