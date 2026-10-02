# TEITOK conformance & flexi* integration — ecosystem plan (umbrella for #9 · #10 · #28 · #38)

> 🔀 **Not this repository's plan:** the TEITOK umbrella stays with ufal/atrium-nlp-enrich; this copy came with the history on 2026-10-01. keyword-extract only reads TEITOK (vendored `api_util/teitok_read.py`, pinned).

> _Written 2026-09-23 from an audit of `atrium-nlp-enrich` (`test` `ed18f40`, v0.20.3), `atrium-llm-enrich`,
> `atrium-alto-postprocess` and `atrium-project`, checked against the TEITOK author's own tooling; round 4
> (2026-09-24) re-audited `test` `3654e73` (v0.21.0) and the same upstream heads; round 5 (2026-09-24, after the
> push) re-checked the pushed heads (nlp `8003051`, llm `08dff48`, alto `2e2794d`, hub `eec0682` = `v1`). Per-issue detail:
> [`digests/10.digest.md`](../digests/10.digest.md) · [`plans/10.plan.md`](10.plan.md) ·
> [`digests/38.digest.md`](../digests/38.digest.md) · [`plans/38.plan.md`](38.plan.md). #9 and #28 are closed
> (2026-09-24); their digest+plan pairs were removed as for #35 — the issues themselves are the record:
> [#9](https://github.com/ufal/atrium-nlp-enrich/issues/9) · [#28](https://github.com/ufal/atrium-nlp-enrich/issues/28).
> Findings marked ▶ were reproduced by running the code (scratch environment, repos untouched)._

> **2026-09-26 — AMČR baseline ([atrium-project#67](https://github.com/ufal/atrium-project/issues/67)).** Decided by
> motyc (AMČR) in #67 and on #10/#38 (and llm-enrich#10), adopted by ÚFAL: #10 and #38 close; **the flexiconv route
> stays off the AMČR production chain** (GPL-3.0, CLI only); the line-table input AMČR sends is `/enrich` with a table
> plus its ALTO, with Trash and Empty lines left out. Two stages are added for the pilot — **Stage 8**, TEITOK layout
> from the record's `lines[].bbox` + `pages[].canvas` for born-digital documents, and **Stage 9**, the nlp-enrich
> `keywords` block (#67 R5; **superseded 2026-09-30**: the block moves to keyword-extractor with #40) — both in §5. Decision 2's xmltokenizer path and the roadmap's flexipipe/xmltokenizer and
> JSON→TEITOK items are marked off the production chain or moved.

## 0. Progress (updated 2026-09-24, round 4)

Stages 1–6 are on `test` and **released in v0.21.0** (tag at `ecdac10`, 2026-09-24; the tag's Docker
build succeeded, so `:latest` is format 2). Rounds: Stages 1–5 pushed 2026-09-23 (nlp `67751ef`/`701b02c`,
llm `f62921c`, hub `4d6ea10`); round 3 (tier-1 fixture, `flexiconv_report.py`, `--with-flexiconv`, Stage 6)
landed as nlp `8a1ded3` + `ecdac10`. `teitok-schema.yml`: red on `8a1ded3` (the annotated CoNLL-U fixtures
came one commit later), green on `ecdac10` (runs 35974285161 `test`, 35974294357 `master`). The hub E2E
last ran on 2026-09-23 (before the tag), so ~~**no E2E has run on format 2 yet**~~ — _it ran on 2026-09-24: run 35990199050 on hub `eec0682`, green, strict `teitok-2` checks, 1/1 references resolved
(CTX000000003)._

Issues: #9 and #28 closed; #10 open for its close-out report; **#38 opened** for the annotated path's
follow-ups. Round 4 (this revision) found that page attribution is wrong in every stage (§3.3, R4-1/R4-2)
and re-scoped #38 around it; the work is Stage 7 (§5), **implemented the same day** in all four repos and
delivered as files, and **pushed the same day**: nlp `8003051` (= `master`), llm `951db5e` (then `08dff48`),
alto `fb72526` (then #31 Phase 4: `267e334`, `3bd10f9`, `2e2794d`), hub `eec0682` (= `main` = `v1`); CI green
everywhere (nlp TEITOK Schema Contract 35989955130). Verified in a scratch venv: nlp-enrich 1123 passed · llm-enrich
947 · alto-postprocess 1584 · hub 169, `mkdocs build --strict` and `workflow_lint.py --offline` clean.

| Stage                              | State                                                                                            | Deviations from §5                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|------------------------------------|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 — dev logs                       | ✅ on `test`                                                                                      | the umbrella plan moved into `plans/`; its links were fixed in Stage 2                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 2 — P0 fixes                       | ✅ on `test`                                                                                      | hub `atrium_vocab.py` **not** touched: the file is byte-identical in five tool repos, so `teitok_alto._CNEC_TO_CONLL` keeps its name as the declared authority (now an alias of `ner_types.CNEC_TO_CONLL`); a drift test pins it equal to `atrium_vocab.CNEC_TO_ENTITY_TYPE`. `summarize_nt_udp.py` keeps its own CNEC→OntoNotes *explanation* map (a different purpose). `ner_types.CNEC_CODES` recognises every CNEC 2.0 code (`ty`, `n_`, `T`, …), not only the coarse-mapped ones                                                             |
| 3 — writer conformance             | ✅ on `test`                                                                                      | `entities[].bbox` stays in ALTO page units (it matches `lines[].bbox`); `pages[].teitok_surface` is only written for pages that have a `<surface>` (ALTO input), so `/enrich` records have none. Also fixed on the way: non-ALTO roots (PAGE XML, hOCR) passed as `alto_path` no longer produce an empty facsimile; unnamed ALTO blocks/lines no longer collapse into one; `summarize_nt_udp.py` per-document mode forwards `--dpi/--alto-dpi`; the dead pre-merge writer call is removed; `MODEL_NAMETAG` reaches the header (`--model-nametag`) |
| 4 — flexiconv path                 | ✅ on `test`, v0.21.0; R3: `run_pipeline.py --with-flexiconv` ✅, `api_util/flexiconv_report.py` ✅ | reference experiment on flexiconv's own examples in the README; the table for real ATRIUM documents is now two commands (user action)                                                                                                                                                                                                                                                                                                                                                                                                             |
| 5 — cross-repo                     | ✅ on `test`                                                                                      | hub: E2E asserts TEITOK and turns `SAVE_TEITOK` on; fixture + `document_schema.md` ids. `docs_site/external-tools.md` / `pipelines.md` W11 and the `atrium_vocab.py` authority string left to their own rounds (#57 policy, 5-repo vendoring)                                                                                                                                                                                                                                                                                                     |
| 6 — annotation of flexiconv output | ✅ on `test`, v0.21.0, opt-in `FLEXICONV_ANNOTATE` → follow-ups in #38                            | in-house stages instead of xmltokenizer/flexipipe, see §5 Stage 6                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| 7 — page provenance & #38 round    | ✅ on `test` `8003051` (2026-09-24), unreleased (suggested v0.22.0); E2E 35990199050 green        | re-scoped from #38's "page breaks for table inputs": chunk markers are the producer, and crossing sentences stay on their first page (§3.3). Deviations from the change sets: [`38.plan.md`](38.plan.md) "As implemented". Stage 3's "`/enrich` records have no `teitok_surface`" and Stage 5's "W11 / external-tools left to their own rounds" are superseded by it                                                                                                                                                                              |

#9's last item, the tier-1 evidence, is ✅ R3: `data_samples/pages/CTX000000001-1.png` plus a test. #9 and #28 closed on
2026-09-24.

**Round 5 (2026-09-24, after the push).** Research and documentation, plus three writer warnings; no output change.
* **Code (nlp):** `teitok_alto._build_page_scale_map` now warns on stderr, once per document, when `INPUT_PAGES_DIR`
  has no `<doc>-<N>.<ext>` for a page, when a page image's pixel size cannot be read, and when ALTO units are not
  pixels and nothing scales them (no image, no `IMAGE_DPI`); tests in `tests/test_teitok_preservation.py`; samples
  unchanged; fast suite 1128 passed.
* **Docs:** nlp README § "TEITOK XML" gains *The format and the standards it builds on*, *How a TEITOK document is
  composed*, *Tools that generate or read TEITOK* and *Pitfalls* (14 items: each leaves a valid file that is wrong for its purpose);
  alto-postprocess `docs/text_inputs.md` gains *Formats and their standards* (every input format: standard,
  producers, what it records, what is kept, origin); llm-enrich README *TEITOK input, in short*; the hub's
  alto-postprocess pages no longer describe it as ALTO-only.
* **Findings (R5-1…R5-4, §3).**

Evidence: flexiconv v0.3.10 round-trip of the regenerated samples keeps every `SpaceAfter=No` (7/7, 16/16, 2/2;
before: 0/7). "abych" is one `<tok>` with two `<dtok>`. OntoNotes `PERSON` → `type="PER" onto="PERSON"`. Sample block
bbox is `220 160 1420 280` on `1654×2339` (page) or `20 10 1220 130` on `1254×2039` (printspace). nlp-enrich
`pytest -m "not slow"` passes 1007 tests with 7 environment-only skips.

## 1. Why this plan exists

`atrium-nlp-enrich` is the only ATRIUM tool that **writes** TEITOK XML (`api_util/teitok_alto.py`, stage 4 /
`/enrich`) and the only one that **converts** third-party formats into it (`api_flexiconv.sh` → flexiconv).
`atrium-llm-enrich` **reads** it (`api_util/teitok_read.py`, `api_util/xml_to_md.py`); the hub **documents** it
(`docs/document_schema.md`, `docs_site/pipelines.md`, `docs_site/external-tools.md`) and its shared
`atrium_vocab.py` names `teitok_alto.py _CNEC_TO_CONLL` as the authority of the 4-concept `entity-type` SKOS scheme.

Since the #9/#10/#28 logs were last refreshed, #28 landed (v0.18.3), #11 switched NER to the multilingual
**OntoNotes** model, the flexiconv pin moved to `v0.3.10`, and upstream made plain `@id` the TEITOK default
(flexipipe 0.3.27, 2026-08-05). The question behind this plan: *do the files we generate — via the CLI and via the
service — still fit current TEITOK conventions, and what in the issue plans is still undone?*

## 2. Reference: current TEITOK conventions

There is **no published TEITOK schema** (no XSD/RNG/DTD in any upstream repository) and teitok.org is not reachable
from the build environment, so the reference is the behaviour of the TEITOK author's own readers and writers:
flexiconv `v0.3.10` = `a982b88` (main `a4f0fd9`), flexipipe `73188c5`, xmltokenizer `4b05623`, flexicorp `61f6543`,
teitok-tools `2968265`.

| Aspect               | Convention                                                                                                                                                                                                                                   | Where upstream does it                                                                                               |
|----------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| Namespace            | namespace-off `<TEI>`; `xmlnsoff="http://www.tei-c.org/ns/1.0"` is the TEITOK idiom                                                                                                                                                          | flexiconv `io/teitok_xml.save_teitok`; flexicorp `flexdecoder_writers.cpp`; teitok-tools `teitok2p5.pl`              |
| Ids                  | plain `@id` (not `xml:id`) on `tok`/`s`; `w-N` / `s-N`, document-global; other elements `facs-N`, `lb-P.L`, `e-N`                                                                                                                            | xmltokenizer `profiles_builtin/teitok.toml`; flexiconv `io/alto.py`, `io/page_xml.py`; `conllu2teitok.pl`            |
| Token attributes     | `lemma upos xpos feats deprel head` (+`ord` sentence index, `ohead`, `deps`, `misc`); `_` values dropped; `head` = the head token's `@id`                                                                                                    | `conllu2teitok.pl`; xmltokenizer `conllu.py`; flexipipe `teitok_name_wrap._tok_ord` (needs `ord` or `w-N`)           |
| **Spacing**          | **text-faithful**: whitespace between `</tok>` and the next `<tok>` is a space; none = `SpaceAfter=No`. `join="right"` is a TEI-P5 export marker, honoured by flexicorp only under `@space="remove"`                                         | flexipipe `_token_from_tok_elem`; flexiconv `load_teitok`; `teitok2conllu.pl`; flexicorp `flexencoder_extractor.cpp` |
| Multi-word tokens    | `<tok>surface<dtok form=… lemma=… …/><dtok …/></tok>`                                                                                                                                                                                        | `conllu2teitok.pl`; flexipipe `_dump_teitok_python`; xmltokenizer                                                    |
| Named entities       | `<name type=…>` wrapping the span, optional `sameAs="#w-1 #w-2"`                                                                                                                                                                             | `nametag.pl`; flexipipe `teitok_name_wrap.py`                                                                        |
| Header               | `titleStmt/title`; `notesStmt/note[@n="orgfile"]`; `revisionDesc/change[@who,@when]`; flexicorp reads workflow phases from `change@type/@subtype/@n` (`converted`, `tokenized`, `tagged`, `parsed`, `ner`) and falls back to the change text | flexiconv `_ensure_tei_header`; flexicorp `backends/teitokxml.py`                                                    |
| Language             | plain `@lang` on `TEI`/`text`/`div`/`s` and/or `profileDesc/langUsage/language`                                                                                                                                                              | flexiconv `io/{folia,tmx,hocr}.py`; `udpipe2teitok.pl`                                                               |
| Layout               | `bbox="x1 y1 x2 y2"` in **absolute page-image pixels, page origin** (raw ALTO HPOS/VPOS); `<pb facs>`; optional `<facsimile><surface><zone>` + `@corresp`                                                                                    | flexiconv `io/alto.py`, `io/hocr.py`; `page2teitok.pl`; `hocr2teitok.pl`                                             |
| Project layout       | a TEITOK project indexes `xmlfiles/<docid>.xml` (doc id = filename minus `.xml`)                                                                                                                                                             | flexicorp `_scan_xmlfiles`; flexiconv `--teitok-project`                                                             |
| Relative coordinates | **not adopted** — ufal/flexiconv#1 (ATRIUM alignment, incl. 0–1 bboxes) open, no reply since 2026-06-15                                                                                                                                      | —                                                                                                                    |

Upstream quirk worth reporting (user action): flexicorp's text fallbacks are written as `r"\\btagg"`, `r"\\bner\\b"`,
… — in a raw string that matches a literal backslash, so only the plain patterns (`tokeniz`, `lemmat`, `dependency`,
`named entit`, `convert`) ever fire ▶. Our header should therefore rely on `change@type`.

**Round-4 re-check (2026-09-24).** The upstream heads are unchanged since 2026-09-23, so the table above still
describes the reference. Read against it tool by tool, format 2 **conforms** on: namespace-off root, plain `@id`,
`w-N`/`s-N`/`w-N.K`, token attributes with `head` as a token id, `ord`, text-faithful spacing (the space inside
`</name>` is what flexiconv and flexipipe's C++ reader need), `<dtok>`, `<name sameAs>`, `<s id text>`, typed
`<change>` phases, `lang` + `langUsage`. No upstream reader rejects the ATRIUM-only attributes (`onto`/`cnec`/`archaeo`,
`div@subtype`, the `teitok-2` stamp on `<application>`). Deviations:

| ID | Deviation                                                                                                  | Upstream                                                                             | Handled in                                |
|----|------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|-------------------------------------------|
| U1 | punctuation split off an ALTO word keeps the word's `bbox`                                                 | flexiconv `io/alto.py:210-221`, `io/hocr.py:153`: split punctuation gets no box      | #38 C                                     |
| U2 | the page size is only on `<surface lrx lry>`                                                               | flexiconv's hOCR/xpdf writers and readers use `pb@bbox="0 0 W H"`                    | #38 C                                     |
| U3 | a `.teitok.xml` file becomes document id `<doc>.teitok` in a TEITOK project; `orgfile` has no `Originals/` | flexiconv `--teitok-project` (`xmlfiles/`, `Originals/`); flexicorp `_scan_xmlfiles` | README, "Importing into a TEITOK project" |
| U4 | `xpos`, where teitok-tools reads `pos` by default                                                          | `teitok2conllu.pl:53` (needs `--pos=xpos`); the project's `settings.xml`             | README, same section                      |

Upstream bugs found on the way (report them; do not work around them): flexipipe takes a token's number from the
digits of its document-global `@id` (`teitok.py:1162-1169`, `io_teitok.cpp:476-484`), so dependency heads go wrong from
the second sentence of any file with `w-N` ids — confirmed by running its loader on the samples; flexiconv
`load_teitok` ignores `<dtok>` (an MWT sentence exported to CoNLL-U gets ids 1–5, 7, 8); the flexicorp regex quirk above
is confirmed (`backends/teitokxml.py:31-37`). So a flexiconv round trip keeps spacing and entities but not multi-word
tokens, and flexipipe is not a safe *reader* of format 2 until its id handling is fixed; the README must say so.

## 3. Findings

### Writer — `api_util/teitok_alto.py::write_teitok_merged` (CLI and `/enrich` share it)
| ID   | Sev | Finding                                                                                                                                                                                                                                                                                                                                                       |
|------|-----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| W1 ▶ | P0  | Every `<tok>` is written on its own line; spacing only via `join="right"`. A flexiconv round-trip of the samples keeps **0 of 7** `SpaceAfter=No` ("č . 1 / 2024"); flexipipe, teitok2conllu and flexicorp read it the same way. ATRIUM's own readers are unaffected (they use `<s @text>` first) → writer-only fix.                                          |
| W2 ▶ | P0  | MWT range lines are skipped: "abych" → `<tok>aby</tok><tok>bych</tok>` — surface text changed, the range line's `SpaceAfter` lost, ALTO character alignment degraded.                                                                                                                                                                                         |
| W3 ▶ | P0  | The coarse NER map is CNEC-only while the default model is OntoNotes (#11): every entity becomes `type="MISC" cnec="PERSON"`. `document_hook.py` maps OntoNotes correctly, so TEITOK and `entities[].type_teitok` disagree; `summarize_nt_udp.py` holds a third map (with archaeo `LOCATION→LOC`) and hub `atrium_vocab.py` a fourth (`CNEC_TO_ENTITY_TYPE`). |
| W4 ▶ | P0  | Every bbox is shifted by the ALTO PrintSpace origin while `<surface lrx/lry>` is the full Page (block `220 160` → `20 10` on `1654×2339`). Upstream uses page origin; tier-1 scaling divides by Page width (so even the "cropped image" rationale is not met); `document_hook.py` writes **unshifted** boxes to `entities[].bbox`; the XSD allows negatives.  |
| W5   | P1  | `lang="cs"` hard-coded; ABBYY `TextBlock@LANG` and the model language are ignored.                                                                                                                                                                                                                                                                            |
| W6   | P1  | `<div type="MarginTextZone-P">` for every block with no ALTO source (the XSD accepts any string; the literal lives in fixtures, samples, READMEs; flagged in llm-enrich #13 and the hub's copy of its logs).                                                                                                                                                  |
| W7   | P1  | Ids `CTX.s1.w3`, no `ord` — flexipipe cannot re-wrap names. Ids are a cross-repo contract (`entities[].teitok_ref`, `lines[].teitok_ref`, `pages[].teitok_surface`).                                                                                                                                                                                          |
| W8   | P2  | Header lacks `orgfile`, a NameTag `<change>` and phase attributes; `<figure id>` uses `hash() % 10000`.                                                                                                                                                                                                                                                       |
| W9 ▶ | P1  | Committed `data_samples/TEITOK/*` are stale (`xmlns=` + `xml:lang`, unshifted) — not today's writer output.                                                                                                                                                                                                                                                   |
| W10  | P1  | `schemas/teitok/teitok.xsd` is derived from the writer (circular); flexiconv output only gets `--wellformed-only`.                                                                                                                                                                                                                                            |

### Tools, adapters, readers
| ID   | Sev | Finding                                                                                                                                                                                                                                                                              |
|------|-----|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| T1 ▶ | P0  | `fix_teitok_bboxes.py` crashes on every file (tuple returns of `fix_name_close_tags` / `detect_source_size` unpacked wrongly); its only test lives outside `testpaths`.                                                                                                              |
| T2 ▶ | P0  | `flexiconv_convert.py` calls `flexiconv.convert()`, which does not exist (API: `flexiconv.api.run_convert` → `ConvertResult`) → always the CLI; no `--no-auto-install` (flexiconv `pip install`s extras mid-run); same-stem inputs collide; re-runs fail on "refusing to overwrite". |
| T3 ▶ | P0  | flexiconv output has **no `<s>`** in any format (plain formats: `<p>` text; PAGE/hOCR/ALTO: `<tok bbox>` in `<div>`/`<lb/>`) → `read_teitok_rows()` returns `[]` → keywords/LLM read nothing (PAGE example: 532 tokens, 0 rows).                                                     |
| T4   | P1  | `FLEXICONV_FORMATS` lacks `xml`/`hocr`; the pin covers the core only (docx/odt/md/pdf/rtf extras come from runtime installs); no flexiconv licence/paradata entry (it declares GPL-3.0-or-later; flexipipe, xmltokenizer: MIT).                                                      |
| T5   | P1  | The two `teitok_read.py` copies diverged both ways (llm: `</n>` repair, roman `pb`; nlp: `@upos` fix); llm-enrich keeps a stale, test-only fork of `teitok_alto.py`; no drift check covers these copies.                                                                             |
| T6   | P2  | Tier-1 image fixture never committed; `tests/test_teitok_integraion.py` (sic) checks a 1×1 PNG exists.                                                                                                                                                                               |
| T7   | P1  | `api_flexiconv.sh` is manual (not a `run_pipeline.py` stage, not in the service) and writes into `$TEITOK_OUTPUT_DIR`, which `api_4_stats.sh` validates with the full writer XSD → a converted document halts the next `stats` run.                                                  |
| T8   | P2  | `api_4_stats.sh` resume skips existing `.teitok.xml` → after any format change, directories would mix old and new files.                                                                                                                                                             |

### Docs & configs
| ID | Finding                                                                                                                                                                                                                                                             |
|----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| D1 | nlp `README.md`: `xmlns=`/`xml:lang` example, `</n>` close, "`<n>` elements", "ready for the flexiconv converter", "raw ALTO pixel values", `INPUT_ALTO_DIR="$OUTPUT_DIR/altos"`, a fictional flexiconv CLI recipe, UDPipe/NameTag said to run on flexiconv output. |
| D2 | `config_api.txt` Image-Options comment, `FLEXICONV_FORMATS`; `para_config.txt` NameTag comment still "Czech CNEC 2.0".                                                                                                                                              |
| D3 | `schemas/teitok/README.md` needs an upstream-conformance section; `service/README.md` `/rescale` wording.                                                                                                                                                           |
| D4 | Hub: `e2e-pipeline-smoke.yml` runs nlp with `SAVE_TEITOK=false`; `external-tools.md` has TEITOK/flexiconv "pending"; `pipelines.md` W11 unwritten; `fixtures/atrium_document.example.json` + `document_schema.md` carry the old id forms.                           |
| D5 | llm-enrich `README.md`/`CONTRIBUTING.md`/`para_config.txt`: flexiconv licence "not yet checked", "verbatim copies" claim.                                                                                                                                           |

### Round 4 (2026-09-24) — findings on `test` `3654e73` (v0.21.0)
| ID     | Sev | Finding                                                                                                                                                                                                                                                                                                                                                                                                                         |
|--------|-----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| R4-1 ▶ | P0  | **UDPipe chunks are written as pages.** `call_udpipe.merge_conllu_chunks` (`:117-118`) writes `# page_break = true` at every chunk start (~900 words); `call_nametag`, `summarize_nt_udp._collect_merged_rows` and the writer (`teitok_alto.py:1171`) read it as a page. CTX000000002 has 4 real pages but one NE file and `page_id` 1 on every `UDP_NE` row; a mid-page chunk start adds a phantom `<pb>` to an ALTO document. |
| R4-2 ▶ | P0  | **A sentence crossing a page stays on its first page** (`<pb>` only between sentences; the XSD forbids it inside `<s>`). In the released sample: CTX000000002 page 4's first line is `lb-3.3` under `<pb n="3">`.                                                                                                                                                                                                               |
| R4-3 ✔ | P1  | Converted-document identity differs between stage 1 (`canonical_doc_id(full name)`) and stage 4 (`canonical_doc_id(stem)`): a table and its converted twin are both annotated; ambiguous siblings are picked silently.                                                                                                                                                                                                          |
| R4-4   | P1  | The stage-4 gate and the service verdict run the XSD only; `lint_core` never runs on writer output; duplicate `pb`/`lb`/`n`/`b` ids and dangling `sameAs`/`corresp` go undetected.                                                                                                                                                                                                                                              |
| R4-5   | P1  | `<pb facs>` is invented (`{doc}-{N}.png`) when a page has no image — every `/enrich` output and txt/md conversions.                                                                                                                                                                                                                                                                                                             |
| R4-6   | P1  | A failed flexiconv conversion is logged as `skip`; `--with-flexiconv` without flexiconv ends green.                                                                                                                                                                                                                                                                                                                             |
| R4-7   | P1  | Service: `/enrich` never has layout (csv/xlsx/txt only, `INPUT_ALTO_DIR=""`); a gate failure is reported as "empty run"; `/rescale` and `fix_teitok_bboxes.py` give every surface the first one's size and do not clamp shifts.                                                                                                                                                                                                 |
| R4-8 ✔ | P1  | Readers: `teitok_read`'s `<s>`-mode line counter never resets at `<pb>` (vendored into llm-enrich); llm-enrich enriches **zero lines** from a `.teitok.xml` (quality forced to 0.0 → Trash; its `tests/conftest.py` patches the filter out); the GPU LLM path calls `_should_process_line` with 6 of 7 arguments in both repos; alto-postprocess `read_tei` renumbers pages and breaks lines at every `</s>`.                   |
| R4-9   | P2  | `teitok_layout` ignores `pb@n`, `<surface><graphic url>` and zones; `BBOX_ORIGIN` is the one TEITOK knob still assigned bare in `config_api.txt`; the README over-states round trips and still calls NE files "per-page … CNEC"; `CONTRIBUTING.md`'s v0.21.0 row has unescaped pipe characters; `teitok-schema.yml` path filters miss the page-path files.                                                                      |
| R4-10  | P2  | Dev logs: hub `13.*` describe llm-enrich #13 while hub #13 is the CAA paper; llm-enrich #13 claims a JSON→TEITOK "re-projection" that exists nowhere; statuses still said "branch … local".                                                                                                                                                                                                                                     |

### Round 5 (2026-09-24) — findings on the pushed heads

* **R5-1** (fixed as warnings) a page without an image in `INPUT_PAGES_DIR`, or with an unreadable one, silently
  keeps layout units and a guessed `<doc>-<N>.png` name; ALTO in `mm10`/`inch1200` without an image or `IMAGE_DPI`
  silently keeps ALTO units. Now one stderr line per document each (README Pitfalls 1–2).
* **R5-2** (alto-postprocess, documented, fix proposed) `page_split.py::split_alto_xml` finds pages only in the ALTO
  v3 namespace: an ALTO v2 or v4 file (or any other `.xml` in the ALTO folder) prints `No <Page> elements found`,
  gets no pages and no document record, and the run goes on. text-lines and the service read every version.
* **R5-3** (cross-repo, documented) page numbers: the writer numbers an ALTO file's pages by their order (`pb-1`,
  `facs-1`, image `<doc>-1`, `pages[].teitok_surface` key `1`), alto-postprocess's ALTO methods by
  `PHYSICAL_IMG_NR`, and `DOC_LINE_CATEG` has no `page_label`. When the `PHYSICAL_IMG_NR`s are not 1, 2, 3 …, `pb@n`
  shows ordinals and the record's `pages[]` gets rows under both keys (checked with a 3-page ALTO numbered 5–7:
  alignment 12/12 either way; `pb@n` 1–3 from an ALTO-method table, 5–7 from a text-lines table). README Pitfalls 14.
* **R5-4** (documented) only ALTO, and flexiconv conversions of ALTO/PAGE XML/hOCR, bring boxes into TEITOK; the
  boxes of ABBYY FineReader XML, DjVuXML, Tesseract TSV and OCR JSON reach no ATRIUM output, because
  alto-postprocess keeps text only.

## 4. Decisions (user, 2026-09-23; round 4: 2026-09-24)

1. **Bbox origin: page origin by default** (upstream). `BBOX_ORIGIN=page|printspace`; under `printspace`,
   `<surface lrx/lry>` = PrintSpace size and tier-1 scales against PrintSpace. Coordinates never negative.
2. **flexiconv output: reader fallback now** (`<lb/>` lines for layout formats, block text otherwise);
   text-faithful annotation via xmltokenizer + UDPipe/NameTag later, opt-in, as a new issue. _(2026-09-26: the flexiconv
   route is off the AMČR production chain; the xmltokenizer follow-up is ⏸️ after the pilot, if at all.)_
3. **Ids: TEITOK-native** — `tok` `w-N` (document-global), `dtok` `w-N.K`, `s` `s-N`, `name` `n-N` (+`sameAs`),
   `surface` `facs-N`, `pb` `pb-N`, `lb` `lb-P.L`, `div` `b-P.K`, `figure` `fig-P.K`, plus `ord`. `teitok_ref` /
   `teitok_surface` carry these local ids (`n-5`, `s-3`, `facs-1`); the `atrium_document` schema types them as plain
   strings, so the schema itself does not change — producers, tests, the hub fixture and docs do. Minor version bump
   with a migration note; readers stay id-agnostic, so old files remain readable.
4. **Stage 1** = refresh of these dev logs (+ status notes in llm-enrich #10/#13). *(Round 4: the 2026-09-23 note meant for
   llm-enrich #13 was posted on hub #13, which is the CAA-paper issue; the hub's `13.*` dev logs had the same mix-up —
   see §4, round 4.)*

**Round 4 (user, 2026-09-24):**
5. **Pages: layout-first.** Pages come from the layout source — ALTO, the converted flexiconv file, or the table's
   `page_num`/`line_num` as a coordinate-free layout. `<pb/>` may sit inside `<s>` and `<name>`; UDPipe chunk starts stop
   being page breaks; NE page files follow the real pages. The stamp stays `teitok-2` (additive XSD change).
6. **Service parity:** `/enrich` also accepts a flexiconv-produced `*.teitok.xml` (and, for tables, an ALTO file) as
   the text and layout source; the service image stays free of GPL flexiconv; conversion stays in the CLI.
7. **Dev logs:** the closed #9/#28 pairs are removed (as for #35), their leftovers carried to #38 and §7; the hub's
   misfiled `13.*` pair is rewritten for the CAA paper and its design content moves to llm-enrich's #13 pair; the
   misposted comment on hub #13 is moved by the user.

## 5. Stages

Stages 2–5 each land as one coherent change set: writer, XSD, fixtures, regenerated samples, readers and docs move
together. Every new attribute needs the XSD in the same commit (its attribute sets are closed).

**Stage 1 — dev logs** (this batch): `digests/`+`plans/` for #9, #10, #28; `DEVLOG.md`; this file;
`atrium-llm-enrich/agent_dev_logs/{digests,plans}/{10,13}.*`; `atrium-project/agent_dev_logs/{digests,plans}/13.*`.

**Stage 2 — P0 fixes, no structural change**
- `fix_teitok_bboxes.py` + `tests/test_fix_teitok_bboxes.py`; move `api_util/test_cli_orchestration.py` → `tests/`.
- `api_util/flexiconv_convert.py` (`run_convert` + `ConvertResult`, CLI `--no-auto-install`, collisions, `FLEXICONV_FORCE`),
  `requirements_flexiconv.txt` extras, `TEITOK_FLEXICONV_DIR` in `config_api.txt`/`api_flexiconv.sh`.
- `api_util/teitok_read.py` canonical copy (fallback modes, tail/`join` spacing, `dtok`, `</n>` repair, roman `pb`,
  `@upos`) + real-output flexiconv fixtures.
- `api_util/ner_types.py::coarse_type()` — one CNEC ∪ OntoNotes ∪ archaeo → PER/ORG/LOC/MISC map used by
  `teitok_alto.py`, `document_hook.py`, `summarize_nt_udp.py`; `@cnec` for CNEC codes, new `@onto` for OntoNotes
  (XSD: `cnec` optional, `onto` added); hub `docs/templates/shared/atrium_vocab.py` updated and re-vendored.

**Stage 3 — writer conformance (the contract change set)**
- `teitok_alto.py`: text-faithful spacing (tails; no whitespace across `</name>`/`<lb/>` at a `SpaceAfter=No`;
  `join="right"` kept); MWT `<tok><dtok/></tok>`; ids per decision 3 assigned **once** in `parse_and_align_conllu()`
  and consumed by writer and hook; `ord`; `sameAs`; bbox origin per decision 1 (hook uses the same boxes);
  `lang` from `TextBlock@LANG` → model → omit, plus `langUsage`; `<div type="TextBlock">` (+`@subtype` from ALTO
  `TAGREFS` when present); header `orgfile`, `change@type` (`converted`, `tagged`+`parsed`, `ner`), writer version
  stamp in `appInfo`; deterministic `fig-P.K`.
- `schemas/teitok/teitok.xsd` + `README.md`, `tests/fixtures/teitok/*`, regenerated `data_samples/TEITOK/*`,
  `api_util/document_hook.py`, tests (`test_document_hook`, `test_api_service`, `test_rescale`, `test_teitok_preservation`,
  `test_validate_teitok`), `REGENERATE_TEITOK` knob in `api_4_stats.sh`.
- New `tests/test_teitok_conformance.py` (stdlib TEITOK-reading round-trip + `flexiconv.load_teitok` at `v0.3.10`)
  and `validate_teitok_xml.py --profile core`; both in `.github/workflows/teitok-schema.yml`.

**Stage 4 — flexiconv path (#10)**: `FLEXICONV_FORMATS += xml hocr`; per-file paradata; `--profile core` gate on
`TEITOK_FLEXICONV_DIR`; `para_config.txt` licence line (nlp + llm); optional `run_pipeline.py --with-flexiconv`;
the real-document experiment table in the README.

**Stage 5 — cross-repo**
- llm-enrich: re-vendor `api_util/{teitok_read,bbox_scale,flexiconv_convert}.py` + tests; delete the stale
  `api_util/teitok_alto.py` fork (its tests stay in nlp); `xml_to_md.py` spacing via `teitok_read`; a SHA-256 drift
  test for the vendored copies; README / CONTRIBUTING / para_config.
- hub: `e2e-pipeline-smoke.yml` `SAVE_TEITOK=true` + validator step + `tools/e2e/e2e_assert.py` TEITOK checks;
  `fixtures/atrium_document.example.json`, `docs/document_schema.md` (ids); `docs_site/external-tools.md` entries for
  TEITOK, flexiconv, flexipipe, xmltokenizer, flexicorp, teitok-tools; `docs_site/pipelines.md` W11.
- alto-postprocess: no code change (pass-through of `teitok_surface`/`teitok_ref`); re-vendor shared files only.

**Stage 6 — annotated flexiconv path** (R3, 2026-09-24; released in v0.21.0; now issue [#38](38.plan.md)). The design changed from
xmltokenizer (`profile="teitok"`) + UDPipe/NameTag to **this repo's own stages**. That needs no new dependency or model
download, gives one writer and one id scheme, lets `document_hook.py` work unchanged, and keeps CI offline. The
converted file is an intermediate:
- **Text**: `api_1_manifest.sh` adds `TEITOK_FLEXICONV_DIR/*.teitok.xml` (`build_manifest_row.py` reads their
  `teitok_read` rows). A table with the same `doc_id` wins, e.g. alto-postprocess's `--method text-lines` (#31, on its
  `test` since 2026-09-24) writing `DOC_LINE_CATEG/<doc>.csv` for the same inputs.
- **UDPipe, NameTag**: unchanged.
- **Layout**: `summarize_nt_udp.layout_source()` picks the document's ALTO, else its converted file (matched by
  `canonical_doc_id`). `api_util/teitok_layout.py` reads it into `_parse_alto()`'s structures:
  - pages from `<pb facs>`;
  - lines from `<lb bbox>`;
  - strings from `<tok bbox>`, or from block words, without coordinates;
  - blocks with the element name as `subtype`.
- **Output**: `teitok_alto.py` writes format 2 under the full XSD. The header names flexiconv and the original document.
  `run_pipeline.py --with-flexiconv` runs `api_flexiconv.sh` first and sets `FLEXICONV_ANNOTATE=true`.

**Stage 7 — page provenance and the #38 round** (round 4, 2026-09-24; detail and done-criteria in
[`38.plan.md`](38.plan.md)). Change sets in order:
- **CS-E** small fixes: flexiconv failures recorded as failures and a missing flexiconv stops the stage (R4-6);
  `BBOX_ORIGIN="${BBOX_ORIGIN:-page}"`; the LLM filter fixes (R4-8) here and in llm-enrich.
- **CS-B** identity: `api_util/doc_identity.py` (file identity for converted documents, `find_converted`, a claim rule
  at stage 1, no silent pick) (R4-3).
- **CS-A1** page plumbing: stage 1 writes `<doc>.rows.tsv` (normalised rows, page ordinal + label), stage 2 freezes it
  as `UDP/<doc>.rows.tsv`; `api_util/page_rows.py` places tokens by UDPipe's `SpacesAfter=\n` line ends plus chunk
  starts; `# chunk_start = K` replaces the old marker, which every reader treats as a chunk start; NE files and CSV
  pages follow real pages; `teitok_read` resets line numbers per page and splits a sentence row at an inner `<pb/>`
  (R4-1).
- **CS-A2** writer: pages resolved per token (layout box, else row, else previous); `<pb/>` inside `<s>`/`<name>`;
  pages only move forward; `facs` only for real images; `teitok_layout` reads `pb@n`, `graphic@url` and sizes; XSD
  additive (R4-2, R4-5, R4-9).
- **CS-C** gate: default profile `contract` = XSD + `lint_core` (unique ids, resolvable refs) + `lint_writer`; exit 5
  (R4-4).
- **CS-D** service: `.teitok.xml` upload and an optional `alto` part; distinct error for exit 5; verdict and
  `layout_source` in the response; page-aware, clamped `/rescale` and `fix_teitok_bboxes.py` (R4-7).
- **Cross-repo:** llm-enrich (zero-lines fix, GPU-path fix, re-vendor `teitok_read.py`/`flexiconv_convert.py`, a
  format-2 fixture, bbox origin in `DOC_META`); alto-postprocess (`read_tei`: `pb@n`, inline `<s>`, `</n>` repair);
  hub (W11, external-tools, `document_schema.md`, `e2e_assert.py` element-type and page checks).
- **Upstream conformance details:** split punctuation without a box (U1), `pb@bbox` (U2), README "Importing into a
  TEITOK project" (U3/U4), per-tool round-trip statements.

**Docs & configs, all stages** — nlp: `README.md` (TEITOK section: real example, ids, spacing, MWT, bbox origin, how to
import into a TEITOK project as `xmlfiles/<id>.xml`; flexiconv section rewrite), `service/README.md`, `config_api.txt`,
`para_config.txt`, `CONTRIBUTING.md`, `schemas/teitok/README.md`, `.github/workflows/teitok-schema.yml`;
llm-enrich: `README.md`, `CONTRIBUTING.md`, `para_config.txt`; hub: Stage 5.

### Stage 8 — TEITOK layout from the record (born-digital documents; AMČR pilot, 2026-09-26)

*Why:* a born-digital document has no ALTO, and flexiconv is off the production chain, so today it gets text-only
TEITOK (no `<surface>`, no boxes; `teitok_alto.py:1300-1323`). Its record, written by llm-enrich's `digital-convert`,
already carries `lines[].bbox` and `pages[].canvas`. Requested by motyc on llm-enrich#10 (§12 W5 there).
- **A third layout source.** `api_util/doc_identity.py` `layout_source()` (`:95-105`) looks for `{doc}.alto.xml`,
  then a flexiconv file; add the record — used when the request (or `--document-json`) carries a record with
  positioned `lines[]` and no ALTO or TEITOK is given. `layout_source` reports `record`.
- **An adapter, not a second writer:** `_parse_record_layout(record)` returns the same page/line/box structure
  `_parse_alto()` (`teitok_alto.py:352`) returns, so alignment (`_align_tokens_to_alto`), page resolution and the
  writer run unchanged. Units: `pages[].canvas.unit` → the writer's coordinate system (`_unit_per_inch`, `:231`);
  `BBOX_ORIGIN=page`; no page images, so no `facs` is invented (decision C of #38).
- **Rows:** the line table's `page_num`/`line_num` match `lines[].page`/`line`; a table without a record keeps the
  coordinate-free layout (decision 5).
- **Tests:** fixture records from llm-enrich's `tests/fixtures/digital/make_fixtures.py` (`two_column.pdf`,
  `rich.docx`) → TEITOK with `<surface>` and token boxes; `validate_teitok_xml.py` default profile passes;
  `entities[].bbox` is the union of the entity's token boxes, as for ALTO.
- *Done when* (David's): **a born-digital PDF gets a TEITOK file with boxes.** A DOCX, which has no geometry, gets
  pages but no boxes — stated in the README.

### Stage 9 — the `keywords` block in the record ([atrium-project#67](https://github.com/ufal/atrium-project/issues/67) R5)

> 🧭 **2026-09-30 — superseded after the meeting.** The block is written by `ufal/atrium-keyword-extractor`
> ([#40](https://github.com/ufal/atrium-nlp-enrich/issues/40)), not by this repository; its shape is
> [atrium-project#73](https://github.com/ufal/atrium-project/issues/73)'s plan §A (`items[]` with the method on every
> keyword, document and per-page keywords). What stays here: the TEITOK projection reads the block, as
> `/project_record` called after keyword-extractor (#40 plan §C.4). The KeyBERT/YAKE default alignment moves with
> `keywords.py`. The text below is kept as the record of the pre-meeting plan.

*Why:* AMČR wants the **statistical** keywords — KeyBERT by default, YAKE selectable — with their method and score, in
the record, *next to* the **controlled** keywords llm-enrich writes (`enrichment.items[].extracted_keywords_*`).
Today they reach only the API response and the CSV (`service/api.py:205-217`, `enrichment.py:711-733`); the hook
writes `entities` and `pages.teitok_surface` only (`api_util/document_hook.py:343,361`); the schema has no such
block and `BLOCK_OWNERS` no owner.
- **Hub (one additive schema round with `source.sha512`, #67 plan §G):** a top-level `keywords` block —
  `{method, method_version, params, items: [{keyword, score}]}` — owned by `nlp-enrich` in `BLOCK_OWNERS`, with a
  `POST_FREEZE_CHANGES` register entry and a changelog section; re-vendored here.
- **Here:** the hook writes it from the run's keyword output; the API default (`api.py:51`, KeyBERT) and the CLI
  default (`run_pipeline.py:623`, YAKE) are aligned on **KeyBERT**; `DEFAULT_KW_METHOD`/`-m yake` keep YAKE
  selectable; the legacy KER method, if run, is recorded as such.
- *Done when (proposed; #67 gives none):* a record from `/enrich` carries `keywords` with method and scores, valid
  under the schema, and the hub E2E asserts it.

## 6. Verification (offline)

1. Stage 1 — `pytest tests/test_docs.py`; no foreign plan left in `plans/10.plan.md`.
2. Stage 2 — `pytest tests/test_fix_teitok_bboxes.py tests/test_flexiconv_convert.py tests/test_teitok_read.py
   tests/test_document_hook.py -q`; the fixer halves a copy of `data_samples/TEITOK`; `sample.txt` + `sample.md`
   convert to two files with ≥1 row each; nothing is pip-installed during conversion.
3. Stage 3 — `pytest -m "not slow"`; `validate_teitok_xml.py data_samples/TEITOK` and `--profile core`; flexiconv
   round-trip keeps 7/7 `SpaceAfter=No`; "abych" survives as one surface token; an OntoNotes `PERSON` becomes
   `type="PER" onto="PERSON"`; default-origin block bbox `220 160 1420 280` on `1654×2339`, `printspace` →
   `20 10 1220 130` on `1254×2039`; `entities[].bbox` = union of the entity's TEITOK token boxes.
4. Stage 4 — `api_flexiconv.sh` then `api_4_stats.sh` both pass; `keywords.py -i "$TEITOK_FLEXICONV_DIR" -m yake`
   produces keywords.
5. Stage 5 — llm-enrich `pytest -m "not slow"`; hub `pytest tests/`; E2E left to CI unless run locally.
6. `ruff check` / `pre-commit run --all-files` in every touched repo.
7. Stage 7 — the done-criteria of [`38.plan.md`](38.plan.md): released CTX000000002 s-5 gets `<pb n="4"/>` inside `<s>`
   before `lb-4.1`; a chunk marker on the one-page CTX000000003 leaves one `<pb>`; the NE files of CTX000000002 are
   `-1…-4`; the default gate rejects duplicate or dangling ids with exit 5; `report.csv` + `report.txt.teitok.xml` give
   one document; `/enrich` accepts a `.teitok.xml` and reports `layout_source`; `--with-flexiconv` without flexiconv fails.

## 7. Roadmap (updated 2026-09-24, round 4)

_2026-09-26 (AMČR, #67): v0.22.0 is tagged (the "user" row's first item); the flexipipe/xmltokenizer alternative is off the production chain; the JSON → TEITOK back-projection moves to llm-enrich's "Deferred record extensions" issue; Stages 8 and 9 above are the pilot's items._

| When                                  | Item                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Owner        |
|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|
| done                                  | R3: tier-1 fixture · `flexiconv_report.py` · Stage 6 + `--with-flexiconv` · v0.21.0 tagged (`ecdac10`) and published · #9 and #28 closed · #38 opened                                                                                                                                                                                                                                                                                                                                 | agent + user |
| R4 (on `test` 2026-09-24, unreleased) | Stage 7 = #38 actions A–F (page provenance, identity, gate, layout fidelity, flexiconv failures, service parity) + the cross-repo reader fixes (llm-enrich zero lines, `teitok_read` per-page lines, alto `read_tei`) + hub docs (W11, external-tools, `document_schema.md`) + upstream-conformance details U1–U4; suggested release v0.22.0                                                                                                                                          | agent        |
| user                                  | ~~first E2E run on format 2~~ (done 2026-09-24, run 35990199050) · tag v0.22.0 and re-run the E2E on its image · `REGENERATE_TEITOK=true` on collections written before v0.21.0 · #10 real-document table · live LINDAT run for #38 and the OntoNotes refresh of `data_samples/{NE,UDP_NE,TEITOK}` · move the misposted hub #13 comment · report the flexipipe id, flexiconv `<dtok>` and flexicorp regex bugs upstream and ping ufal/flexiconv#1                                     | user         |
| later                                 | TEITOK project export (`xmlfiles/`, `Originals/`, page images) once the facsimile folder convention is confirmed · relative coordinates after flexiconv#1 · JSON → TEITOK back-projection of LLM keywords/page categories (asked in flexiconv#1; a design item of atrium-llm-enrich#13) · `lines[].teitok_ref` ↔ `<lb id>` · flexipipe/xmltokenizer as an alternative annotator once the upstream bugs are fixed · `atrium_vocab.py` authority string at the next five-repo vendoring | —            |
