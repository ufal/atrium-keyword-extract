# 📓 atrium-keyword-extract — agent_dev_logs/DEVLOG.md (timeline index)
> _Keyword extraction: statistical keywords (KeyBERT/YAKE) and controlled keywords from the AMČR/TEATER vocabulary through an LLM, with the CC0 vocabulary as a release asset. Split from atrium-nlp-enrich and atrium-llm-enrich on 2026-10-01. 2 open issues: #2 (research, deferred past the pilot, atrium-project#67) and #3 (decision models over the vocabulary, #2's Option 4, opened 2026-11-06; a sub-issue of atrium-project#83); #1 closed 2026-10-12 (its pair removed 2026-10-21). **Starting set of the pilot phase: v1.6.4-beta** (`0d5a2f3`, 2026-11-04; immutable, with `images.json`; atrium-project#77); v1.6.3-beta and the mistyped `v1.6.3.-beta` were tagged, not released. Hub workflows pinned to `4435ffb` (`v1`). Latest entry: 2026-11-12 (this repository's part of atrium-project#84: `plans/84.plan.md`)._
> _Per-issue detail: `digests/{id}.digest.md` · `plans/{id}.plan.md` · `issues/` exports (source of truth). Entries before 2026-10-01 are atrium-nlp-enrich's, where #2 was #6. Cross-repo history lives in `ufal/atrium-project/agent_dev_logs/DEVLOG.md`._

## 2026-04-17
- **#6 Extract keywords via LLM (TEATER topics)** — Opened by K4TEL: a local LLM takes the document + topic thesaurus + JSON template and returns thesaurus terms linked to the text.

## 2026-04-19
- **#6** — Posted an LLM comparison table (Qwen 2.5, Mistral NeMo, …); commit `003c05b` drafts the solution + README "LLM Semantic Enrichment" section.

## 2026-04-22
- **#6** — Commit `c9759a7`: full implementation, switching Ollama → Hugging Face `transformers` with `lmformatenforcer` to guarantee Pydantic-schema JSON.

## 2026-04-23
- **#6** — Commit `7e851e3`: anti-hallucination fixes incl. an injected `"Nerelevantní (meta-text)"` category that survives context truncation; cross-model analysis.

## 2026-04-24
- **#6** — Commit `c109444` results: top performers Qwen 2.5 14b (AWQ) & Qwen 3 14b (phrase-level keywords); priority taxonomy (Documentation, Chronology, …).

## 2026-04-27
- **#6** — Commit `382b27e` adds 3 LLM result folders (MoE still has memory bugs); Gemini ranking (Tier 1 `gemma-4-31b`, `qwen-36-27b`); commit `89f3d82` disables Qwen 3 thinking-mode for constrained decoding + a meta-text keyword guard; commit `fafbb37` restructures the LLM pipeline (`llm_run.py` / `llm_utils.py` / `vocab_manager.py`), released **v0.10.0**.

## 2026-04-29
- **#6** — Commit `49f9b2b` results: Gemma 4 31B top tier (flawless meta-text discipline, phrase-level keywords); TODO MoE models + 100–500B dense/MoE runs on the 144 GB/200 GH node; feed the whole vocabulary when context allows.

## 2026-05-11
- **#7 Train domain-specific NameTag NER** — Opened by K4TEL: NameTag 3 for archaeology entities (à la ArchaeoBERT: PER/LOC/ART/CON/MAT/SPE); define flat vs nested NE types; annotate O-I-B data.

## 2026-05-13
- **#7** — 10 example sentences per NE type for a demo; ~10,000/type for actual BERT training.

## 2026-05-20
- **#6** — Commit `3e24876` (items 7 & 8): a `_write_abort_marker()` writes a `*.abort.json` sidecar instead of a silent abort after consecutive errors.

## 2026-05-25
- **#6** — Commit `733f8e4`: results for 8–70B models with rankings (+ a comparison chart); Qwen 3.6-27B settles in as production default.

## 2026-05-28
- **#7** — PERIOD and LOCATION to be merged with existing NameTag3 types; other ArchaeoBERT NEs transferred as-is.
- **#8 Add API service** — Opened by K4TEL (single-file entry point → NLP-enriched `teitok.xml`, all intermediate steps).
- **#9 TEITOK image-file dependence** — Opened by K4TEL (bbox calibration needs image width/height; prefer relative values; document a user-DPI alternative).
- **#10 Flexiconv-supported input options** — Opened by K4TEL (accept any flexiconv format, incl. CSV/XLSX, as raw text).

## 2026-05-29
- **#7** — motyc: Location should be merged (same thing); Period is probably a custom subcategory.

## 2026-06-12
- **#8** — Commit `3928c67`: a documented merged `run_pipeline` script (input = ordered text lines; output = teitok + keywords + LLM JSON).

## 2026-06-14
- **#8** — Commit `f295b5e` review: `num_keywords` is silently ignored (never reaches `run_pipeline.py`).

## 2026-06-15
- **#8** — Commits `d950e1d`/`48c8b85`: working API draft; flagged the missing `nlp-api` service in `docker-compose.gpu.yaml`; released **v0.12.0** (documented API tested via CLI).
- **#9** — Commit `8935d60`: post-factum TEITOK fixer + metadata-based bbox resolution; `api_util/teitok_alto.py` gets dependency-free PNG/JPEG/TIFF header readers; released **v0.13.0**; requested alignment with the flexiconv GUI.
- **#10** — Opus architecture plan confirmed (tabular CSV/XLSX → api_1–4 unchanged).

## 2026-06-16
- **#7** — Posted the CNEC 2.0 ↔ ATRIUM taxonomic alignment strategy (synthesize ArchaeoBERT domain types with NameTag 3 multitagset).
- **#10** — Commit `efbf8b8` (code not yet tested on real out-of-scope formats).

## 2026-06-17
- **#7** — Opus 4.8 Max validation of the CNEC↔ATRIUM mapping: NameTag 3 mechanics right, but use a **separate tagset** (multitagset output-masking keeps labels separate); entity-code mapping corrected.

## 2026-06-19
- **#7** — `nametag3-multilingual-260521` chosen as the base; Czech-only data + maybe some Dutch/British archaeology pages.

## 2026-06-20
- **#7** — stranak: do we need hierarchical tags? As a first learning step, would training an English-Archaeo NameTag from the ArchaeoBERT data make sense?

## 2026-06-21
- **#7** — Posted the refined NER roadmap ("decisions locked").
- **#8** — Commit `d952301`: added a `/rescale` API option + `</n>`→`</name>` fix in returned teitok.xml.
- **#11 NameTag3 multilingual base** — Opened by K4TEL: replace per-language NameTag3 model selection with the generalized multilingual model (links #7); not yet added to the API.

## 2026-06-22
- **#7** — Requested a LINDAT API model-list update (`ufal/nametag3#4`).
- **#8** — Current-state review: the FastAPI wrapper (`/enrich`, `/jobs` with a semaphore) makes the repo deployable.
- **#9** — TEITOK image-dependence audit; released **v0.15.0** with the handling implemented.
- **#10** — Current-state review.
- **#11** — Requested the API model-list update.

## 2026-06-23
- **#6** — Cluster node drivers updated to try bigger models; commit `4ef89fc`. The 235B/671B MoE run is next.

## 2026-06-24
- **#7** — `ufal/nametag3#4` resolved (to test); the multilingual LINDAT API tested fine (via #11).
- **#11** — Full model list available; commit `667b070` tested on synthetic samples (CNEC → ONTO tagset). Config switched to `nametag3-multilingual-onto-260521`; `CNEC_TO_ONTO_MAP` added to the summarization utility; `TestNameTagExplanationMapping` unit suite verifies native-ONTO + legacy-CNEC resolution. Later released in **v0.16.0** (with the paradata-template update + `agent_dev_logs/`).

## 2026-06-25
- **#7** — Posted Gemini DR 3.1's advanced methodological framework for the NameTag 3 archaeology-NER training routine. Immediate next step remains the Phase-0 pilot on Brandsen Dutch data — no training run yet.

## 2026-06-28
- **#10** — Tests + fixtures landed (`5f34f98`), resolving the coverage gap (stdlib readers, mocked conversion, lib→CLI fallback); per K4TEL the flexiconv path has **not been tested in practice** — the issue stays open until real conversion experiments run on live documents.

## 2026-07-12
- **#8** — Version single-sourcing landed (`8ab13e3`): `_read_tool_version()` reads `para_config.txt [tool] version` — no more hardcoded `0.11.0`; repo + `/info` at **v0.16.1** (licenses test per the hub template, dependency bumps; ruff pre-commit flipped to advisory). Digest reconciled against HEAD: the service now verified as a package (`service/api.py` + `enrichment.py` + `jobs.py` + `rescale.py`) with **all audit bugs fixed on HEAD**. Remaining: the `device` field in `/info`, the `nlp-api` NVIDIA reservation in `docker-compose.gpu.yaml`, and a real containerized deployment run.
- **#9** — Status corrected `Closed` → open/`Tocheck`: implementation shipped in v0.15.0, but the **XSD schema-conformance gate** at the end of `api_4_stats.sh` (Q1–Q2 milestone) and the **TEITOK-team confirmation on relative coordinates** are still pending.
- **#10** — Digest downgraded from "fully verified" per the 06-28 comment: test-covered only; stays open for real conversion experiments.
- Digests/plans refreshed across the repo; gap: **#11 still has no issue-log export** (re-run of the export tool needed).

## 2026-07-26: `atrium_document` Integration for nlp-enrich

**Action:** Implemented the paradata-pair accretion model (`atrium_document.py`) into the `nlp-enrich` pipeline.
**Details:**
- **Refactoring:** Extracted and centralized CoNLL-U parsing and ALTO bbox alignment in `teitok_alto.py` to prevent data drift between the TEITOK XML writer and the new accretion hook.
- **Reference Integrity:** Added stable `id="doc.nameN"` attributes to `<name>` tags in TEITOK XML to ensure the `entities[].teitok_ref` JSON field points to a dereferenceable element.
- **Hook Implementation:** Built `api_util/document_hook.py` to handle ONTO and CNEC tagset detection, mapping entities dynamically to the central FAIR JSON schema and capturing union bounding boxes.
- **Process Orchestration:** Wired `--document-json-dir` through `api_4_stats.sh` and `summarize_nt_udp.py`, reading paradata state via `.state_*.json` to extract `run_id` and `license_detail` across subprocess boundaries.
- **Design Gap Addressed:** `lines[]` contribution is strictly gated behind an `--include-lines` opt-in flag. Because `nlp-enrich` processes raw ALTO coordinates without visibility into `alto-postprocess`'s 1-based layout reordering, a naive `merge_block("lines")` would risk silent duplicate rows and misalignment. 
**Status:** Feature complete. Test suite and orchestration verified.

## 2026-07-27

* **#18** — Added a draft of Label Studio to the repo alongside data samples converted by scripts into import-friendly formats.

## 2026-07-30

* **#18** — Posted a screenshot of a local Label Studio run. Provided a GPT DeepResearch summary comparing tools: 
INCEpTION remains the best fit for collaborative document curation and multi-user workflows, while Label Studio is 
stronger for fast bulk ingestion and general-purpose labeling.

## 2026-08-01

* **#18** — Shared a Gemini Pro 3.1E Deep Research summary evaluating INCEpTION (top for curation), Label Studio 
(top for bulk ingestion), Argilla (developer-centric/API-first), and Doccano (lightweight Docker). Posted screenshots 
of the Doccano and Argilla interfaces.
* **#8** — Closed. The API service (`/enrich`, `/jobs`) has been deployable and documented since June; nothing further blocked it.

## 2026-08-02

* **#28 Implement TEITOK XSD Schema-Conformance Gate** — Opened by K4TEL: `atrium-translator` validates its output
against the AMCR XSD, but `nlp-enrich` has no equivalent gate for generated TEITOK XML; a strict schema check must
land at the end of `api_4_stats.sh` so malformed XML is caught before it reaches downstream visualizers, search
indexes, or the LINDAT release.

## 2026-08-02 – 2026-08-19 (version history reconstructed from `CONTRIBUTING.md`'s changelog table)

* The commits tagged **v0.17.0** through **v0.18.3** are **no longer reachable from `test`/`master`** — the same
dangling-tag pattern seen elsewhere in the ecosystem this window (a session-container loss, not real data loss: the
underlying files — `atrium_document.py`, `api_util/document_hook.py` — are present and correct on current `test`).
The repo's own `CONTRIBUTING.md` changelog is the only surviving record of what shipped, and is trustworthy because
it's prose written at release time, not a commit-graph artifact:
  - **v0.17.0** — OpenAPI-standards draft; `agent-skill` branch service aligned with `test`'s API design.
  - **v0.18.0** — `atrium_document` JSON input/output integration (draft); Dockerfile fix; paradata template refresh.
  - **v0.18.1** — Major GHA workflow update, reusable references pinned to the hub's `@v1` tag; annotator LabelStudio
imports drafted.
  - **v0.18.2** — `atrium_document` refined and tested against the draft schema **on the CLI path only**
(`run_pipeline.py --document-json[-out]`, bridged onto the `stats` stage). The API path was **not** covered — `/enrich`
shelled out to `run_pipeline.py` without either flag (tracked as hub #10 finding **J3**).
  - **v0.18.3** — **#28 lands**: TEITOK XML validated against its XSD (`api_util/validate_teitok_xml.py` + a new
`teitok-schema` workflow). **J3 fixed** — `/enrich` now accepts/returns a `document_json` part, giving the API path
the same coverage as the CLI. `atrium_document.py` re-vendored so `DocumentRecord` inherits `doc_id` from the baseline
instead of overwriting it; `canonical_doc_id()` adopted uniformly across `build_manifest_row.py`, `summarize_nt_udp.py`,
`teitok_alto.py`, `teitok_read.py`, `run_pipeline.py`; `entities[].type_cnec: null` fixed.
  - **v0.19.0** (08-19) — **AMCR + TEATER controlled-vocabulary harvest and build** for #6: new `vocab_sources.py`
(OAI-PMH harvest, network disabled at parse time) and `vocab_build.py` (`--from-flat --check` proves the artifact
reproduces from committed flat files alone), on a new monthly `vocab-refresh.yml` (the pipeline's usual runners can't
reach `api.aiscr.cz`). Fixed the nightly suite silently reporting success on zero collected tests (it ran
`pytest -m slow` against a repo with no slow-marked tests, tolerating exit 5).

## 2026-09-03 – 2026-09-06: Issue #6 — the vocabulary becomes decided, then becomes code

*(Full 13-phase record: `digests/6.digest.md`, 808 lines. This is the condensed version.)*

* **The blocking question, reprised.** @david-spacil's 11-Aug question — "which vocabulary are we actually mapping
to?" — turned out to matter more than a naming issue: `teater_nested_vocab.json` was 100% AMCR, and `Other`'s
exclusion silently dropped 228 terms that had a proper TEATER home. @motyc's 26–27 Aug governance rulings settled the
frame ("apply the vocabularies, don't reorganize them"; exclude only on evidence, not anticipation) and this window
is where every ruling became code.
* **03 Sep** — `a5e3c8a` lands scope exclusions (7 technical AMCR lists dropped, `Documentation` facet dissolved),
dedup-before-exclusion (recovers `olej`/`vodní pramen`/`úřední písemnost`), a new `data_samples/taxonomy_overrides.json`
for per-term overrides, and `teater_category_ids` attached to LLM output. Left a several-hour gap where the config and
the vocabulary artifacts disagreed (nothing failed — the stale artifact just won silently); closed same day by
`d4c46b2`/`aaff278`/`655043e`, which also add `vocab_review.py` (collision/composite/exclusion-impact sheets) and a
new `vocab-drift.yml` CI gate that already caught the gap on its first run.
* **04 Sep** — `0ad8ae2` lands the real evidence corpus (issue #19's 16 documents, 2172 lines) and `corpus_review.py`.
Caught and fixed a real bug the same day: casefolded matching credited the country "Malta" with 7 occurrences that
were actually the mortar material `malta` — exactly the failure mode the geographic guardrail exists to prevent,
inverted onto the evidence meant to justify relaxing it. **v0.20.0** ships: ten `_settings` config keys make every
vocabulary decision an edit instead of a code change; `validate_settings()` refuses silent no-ops; a new
`--specificity` report finds 44% of the whole vocabulary is intra-facet broader/narrower pairs (`třetihory` scores
zero against gold `paleogén` under exact match) — the largest open question for the still-unwritten evaluation rubric.
@motyc and @david-spacil rule the two outstanding exclusion questions same day: reinstate both TEATER branch groups,
relaxing the geographic guardrail **in the same change** for the one group that needs it. Reinstatement: 2,074 →
4,718 terms; the build gate now reads the actual prompt text `llm_run.py` renders (not a grep for a sentence) and
fails on a config/prompt mismatch.
* **05–06 Sep** — The system prompt moves out of Python into `prompts/system_prompt.txt` as flag-selected blocks,
byte-for-byte pinned against the old literals so no refactor can silently change what a model receives. Grouping
(`facet_sub`/`facet`/`flat`) becomes an ablation flag. Two real defects caught by re-auditing the reviewers' own
questions against the tree: the vocabulary-block extraction had shipped "half-landed" (two implementations, tests
only compared one against itself) and the token-budget sheet was under-reporting cost by not billing ~120 group-header
lines. Both fixed same day. **v0.20.1** ships (09-06): vocab updated, prompt fully config-driven.
* **State (09-07):** the vocabulary half of #6 has nothing open in it; the reinstatement is shipped but the
evaluation-corpus evidence sheets predate it and can't be refreshed in this environment (the real corpus isn't
checked out here). The one open ruling left is @david-spacil's on facet placement (A1); the evaluation rubric itself
(D1) is still unwritten and got harder as the vocabulary doubled.

## 2026-09-07

* **State**: 7 open issues (#6, #7, #9, #10, #18, #19, #28); #8 and #11 closed. `test` and `master` both at `8dac20e`
(**v0.20.1**). All seven hub reusable-workflow references confirmed pinned to `@v1` (not `@test`). #7 (NER training —
design locked, no training run yet) and #9/#10/#18/#19 are unchanged since their last digest refresh in early
August; #6 is the active thread, blocked only on the D1 evaluation rubric and a live corpus refresh.

## 2026-09-08 – 2026-09-17 (from the `CONTRIBUTING.md` changelog and commit subjects)

* Ecosystem-standard work landed without new issue threads here: SKOS vocabulary standard, RO-Crate standard,
backing-service URLs (`UDPIPE_URL`/`NAMETAG_URL` attachable), env/logging/port-8000 standards, `flexiconv` pin moved to
the `v0.3.10` tag (`843a7ab`, atrium-project#62).
* **#35** — closed (09-16): the single-replica constraint on `/jobs` is surfaced in every `/jobs` 404 and a boot-time
log line — **v0.20.2**. **v0.20.3** fixes the release gate (distro security patches in the `Dockerfile`).

## 2026-09-23: TEITOK / flexi* conformance audit (#9, #10, #28)

* **Scope.** Checked whether the TEITOK XML generated by the CLI (`api_4_stats.sh`) and the service (`/enrich`,
`/rescale`) still fits current TEITOK conventions, taken from the TEITOK author's own code (flexiconv `v0.3.10`,
flexipipe `73188c5`, xmltokenizer `4b05623`, flexicorp `61f6543`, teitok-tools `2968265` — there is no published TEITOK
schema), and re-audited the #9/#10/#28 plans against `test`. Findings were reproduced in a scratch environment; the
repo was not modified by the audit itself.
* **Writer (`teitok_alto.py`)** — spacing lives only in `join="right"` (upstream readers use inter-token whitespace:
0/7 `SpaceAfter=No` survive a flexiconv round-trip); MWTs are split (`abych` → `aby` + `bych`); the CNEC-only NER map
turns every OntoNotes entity (the default model since #11) into `type="MISC" cnec="PERSON"`; bboxes are shifted by
the PrintSpace origin while `<surface>` declares the full page; `lang="cs"`, `MarginTextZone-P`, non-TEITOK ids, no
`ord`; committed `data_samples/TEITOK/` predate the current writer.
* **Tools** — `fix_teitok_bboxes.py` crashes on every file; `flexiconv_convert.py` calls a non-existent
`flexiconv.convert()` (always CLI), lets flexiconv `pip install` extras at runtime and collides on shared stems;
flexiconv output has no `<s>` in any format, so `teitok_read` yields **zero rows** for keywords/LLM; flexiconv writes
into the directory the stage-4 XSD gate validates.
* **Gate (#28)** — landed in v0.18.3 as designed in practice (lxml, not xmllint); circular by construction (XSD
derived from the writer), so it passes the defects above.
* **Decisions (user):** page-origin bboxes by default + `BBOX_ORIGIN=printspace` opt-in; reader fallback for flexiconv
output now, xmltokenizer annotation later; TEITOK-native ids (`w-N`, `s-N`, `n-N`, `facs-N`, …) with the
`teitok_ref`/`teitok_surface` contract migrated; dev logs first.
* **Dev logs refreshed:** `digests/`+`plans/` for #9, #10 (an unrelated llm-enrich plan appended to `plans/10.plan.md`
removed), #28; new [`plans/teitok_conformance_plan.md`](plans/teitok_conformance_plan.md) (Stages 1–6, file lists, verification).
Status notes added to `atrium-llm-enrich` #10/#13 and `atrium-project` #13 logs.

## 2026-09-23: TEITOK format 2 + flexiconv path implemented (#9, #10, #28; branch `claude/inspiring-cerf-2gdtd1`, local)

* **Stage 1 on `test`**: the maintainer took the refreshed dev logs (`bd62317`, `f82f922`; the umbrella plan moved to
`plans/`). Stages 2–5 were then implemented on the branch. It is local and not pushed; every file is delivered in
full for review.
* **Writer = TEITOK format 2** (`api_util/teitok_alto.py`, stamped `version="teitok-2"`):
  * text-faithful inline spacing (entity trailing space inside `</name>`), with `join="right"` kept;
  * MWT as `<tok>abych<dtok/>…</tok>`, aligned to ALTO on surface forms;
  * ids assigned once in `parse_and_align_conllu()`: `w-N`/`w-N.K`/`s-N`/`n-N`/`facs-P`/`pb-P`/`lb-P.L`/`b-P.K`/`fig-P.K`,
    plus `ord` and `head` → id;
  * `<name type sameAs onto|cnec|archaeo>` via the new `api_util/ner_types.py`;
  * page-origin bboxes by default, with `BBOX_ORIGIN=printspace` giving a self-consistent PrintSpace surface and
    clamping;
  * `lang` from ALTO → UDPipe model → omitted;
  * `<div type="TextBlock" subtype>`, `notesStmt` orgfile, `change@type` phases.
  * The XSD moved with it and still accepts format 1. Samples and fixtures are regenerated, and a test fails when
    they drift from the writer. The new `tests/test_teitok_conformance.py` lane runs, with a flexiconv round-trip, in
    `teitok-schema.yml`.
* **Hook**: `teitok_ref` = `n-N`, `teitok_surface` = `facs-P` (only for ALTO pages); entity surface with real spacing;
  character offsets over surface tokens; types from `ner_types`.
* **Stats stage**:
  * `summarize_nt_udp.py` forwards `--dpi/--alto-dpi` in per-document mode (they were dropped);
  * new `--bbox-origin`/`--model-udpipe`/`--model-nametag` flags, because `MODEL_NAMETAG` never reached the
    header — the config is sourced, not exported;
  * the dead pre-merge writer call is removed;
  * `REGENERATE_TEITOK`, and the XSD gate excludes `TEITOK_FLEXICONV_DIR`.
* **flexiconv path (#10)**:
  * `flexiconv_convert.py` on the real `flexiconv.api.run_convert` API, CLI with `--no-auto-install`, same-stem
    naming, resume/force;
  * extras pinned; `xml hocr` routed; own output directory; paradata; `--profile core` gate;
  * `teitok_read.py` (the canonical copy) reads `<lb/>` lines / text blocks when there is no `<s>`;
  * reference run: every flexiconv example gives rows and YAKE keywords (before: 0 rows).
* **Tools**: `fix_teitok_bboxes.py` works again and has tests; `test_cli_orchestration.py` is now collected.
* **Docs**: README TEITOK / coordinate / flexiconv sections, config block, `service/README.md`, `CONTRIBUTING.md`,
`schemas/teitok/README.md`, dev logs #9/#10/#28 and the umbrella plan's progress table.
* **Suite**: `pytest -m "not slow"` 1007 passed, 7 environment-only skips; ruff clean. No version bump (maintainer's call;
suggested: minor, "TEITOK format 2" + `REGENERATE_TEITOK` note).
* **End-to-end**: `api_4_stats.sh` on a scratch copy of `data_samples/` (UDP + NE + ALTO, one flexiconv file under
`TEITOK/flexiconv/`) exits 0. The XSD gate validates exactly the three writer files. OntoNotes entities come out as
`type="LOC" onto="GPE"` and `type="PER" onto="PERSON"`.
* **Follow-up found (not fixed here)**: the committed samples disagree on the NER model. `data_samples/NE/*.tsv` carry
**OntoNotes** tags (GPE/PERSON/DATE, the #11 default), but `data_samples/UDP_NE/*.conllu` and `*.csv` still carry
**CNEC** tags (gu/P/ty, the model `data_samples/paradata` records). So re-running stage 4 on the samples yields
different entities than the committed `UDP_NE`. The TEITOK samples follow `UDP_NE`, i.e. CNEC (consistent with
their paradata). Refreshing `UDP_NE/` + `summary_ne_counts.csv` + the TEITOK samples from `NE/` is a separate
sample refresh.

## 2026-09-24: Round 3 — #9/#10 close-out and the annotated flexiconv path (branch `claude/inspiring-cerf-2gdtd1`, local)

* **On `test` since 2026-09-23**: Stages 2–5 (nlp `67751ef`/`701b02c`, llm `f62921c`, hub `4d6ea10`), plus the six issue
comments. CI is green. `teitok-schema.yml` ran the conformance lane and the pinned-flexiconv round trip (run
35896731559), which meets #28's close criterion. The hub E2E (`SAVE_TEITOK=true`, `--teitok-dir`) is green. It runs the *published* image
`ghcr.io/ufal/atrium-nlp-enrich:${image-tag || latest}`, and `:latest` moves only on a version tag, so push and
schedule runs still test v0.20.3 (format 1). The first format-2 E2E run is a `workflow_dispatch` with
`image-tag=test` (user), or any run after v0.21.0 is tagged.
* **Found on alto-postprocess `test` (`103e30a`, #31)**: `--method text-lines` reads any text-bearing input (PDF, DOCX,
TXT, PAGE XML, hOCR, TEI/TEITOK, …) into `DOC_LINE_CATEG/<doc>.csv`, which is this repo's stage-1 input. So
converted documents can reach UDPipe/NameTag through alto-postprocess, but without layout. That shaped Stage 6 below:
the flexiconv file becomes the *layout source*, matched by `canonical_doc_id`, and a table with the same `doc_id` wins
at stage 1.
* **#9, tier-1 evidence**: `data_samples/pages/CTX000000001-1.png` is 827×1170 (half the ALTO page), 671 bytes, and
draws the ALTO boxes at half scale. `tests/test_teitok_integraion.py` is renamed `tests/test_teitok_integration.py`,
and its vacuous 1×1-PNG test is replaced by one that pins the surface `827×1170`, the block `110 80 710 140` and page 2
at tier 3. README has a worked example. #9 is ready to close.
* **#10, close-out tool**: `api_util/flexiconv_report.py DIR [--inputs DOCS]` prints the "Checking a real collection"
table: input/format, pages, rows, tokens, elements with bbox, and the `--profile core` verdict. It also lists
unconverted inputs, exits 0/1, and has tests.
* **Stage 6 — `FLEXICONV_ANNOTATE`** (opt-in; its own issue still to be opened). The design is this repo's stages, not
xmltokenizer/flexipipe: one writer, one id scheme, no new dependency, offline CI.
  * New `api_util/teitok_layout.py` reads a flexiconv TEITOK into `_parse_alto()`'s five structures:
    * pages from `<pb facs>`, sized by hOCR `pb@bbox` or `<surface lrx lry>`;
    * lines from `<lb bbox>`;
    * strings from `<tok bbox>`, or from block words without coordinates;
    * blocks with the element name as `subtype`;
    * converter/orgfile meta.
    * Its character stream equals `teitok_read`'s rows, and a test pins that invariant.
  * `teitok_alto.py`:
    * `_parse_alto` hands TEI roots to it;
    * alignment tolerates strings without coordinates (`has_coords`);
    * `<graphic url>`/`<pb facs>` keep the source's image names;
    * a page image is also found by that name, and an image without a page size sets the surface at scale 1;
    * the header names flexiconv (`<change who="flexiconv" type="converted">`, `<application ident="flexiconv">`)
      and the original document.
  * `build_manifest_row.py` reads `*.teitok.xml` (`--doc-id-only`). `api_1_manifest.sh` adds
    `TEITOK_FLEXICONV_DIR` when `FLEXICONV_ANNOTATE=true`; tables win, empty conversions are skipped, and it avoids
    bash-4 associative arrays.
  * `summarize_nt_udp.layout_source()` (ALTO, else the converted file) serves both the writer and the hook, via
    `--flexiconv-dir`, which `api_4_stats.sh` passes. `run_pipeline.py --with-flexiconv` runs `api_flexiconv.sh`
    first and exports `FLEXICONV_ANNOTATE=true` (`config_api.txt`: `${FLEXICONV_ANNOTATE:-false}`).
  * Evidence:
    * tests in `tests/test_teitok_layout.py` (18) and `tests/test_flexiconv_annotate.py` (24), with hand-written
      NER-merged CoNLL-U for the committed conversions in `tests/fixtures/teitok/flexiconv/annotated/`;
    * an offline `api_1_manifest.sh` → `api_4_stats.sh` run on PAGE XML / hOCR / txt: 3/3 pass the stage-4 XSD gate
      and the core profile;
    * the document records validate against the schema, with entity bboxes from flexiconv (`Praze` `620 100 820 150`),
      `teitok_ref`s that resolve, and `teitok_surface` `facs-1`;
    * flexiconv v0.3.10 reads every output back.
    * The live UDPipe/NameTag run needs LINDAT (user).
* **Docs/CI**: README (annotated path, tier-1 example, report tool), `config_api.txt`, `CONTRIBUTING.md` (flag + the
two layout sources), `schemas/teitok/README.md` (emitter table), `api_flexiconv.sh` header, and a new
`teitok-schema.yml` step plus path filters. Dev logs: #9 and #28 ready to close, #10 with close-out tool and D done,
umbrella plan §0 and §7 (roadmap).
* **Release prep** (separate commit): v0.21.0 in `CITATION.cff`, `para_config.txt`, and the `CONTRIBUTING.md` row
with the migration note (`REGENERATE_TEITOK=true`; TEITOK-local record ids). Tagging is the maintainer's call.
* **Fixed on the way — `REGENERATE_TEITOK` could not be switched on for one run.** `config_api.txt` assigned it bare,
so `REGENERATE_TEITOK=true bash api_4_stats.sh` was overwritten by `source` and silently kept the old files; only a
config edit worked. It is now `"${REGENERATE_TEITOK:-false}"`, like `FLEXICONV_ANNOTATE`, and a test sources the
config with and without each knob set.
* **Sample refresh, verified, not committed.** In a scratch worktree, a stand-in api_3_nt paradata record naming the
OntoNotes model (`data_samples/NE` already carries its tags) was used. Then
`rm -rf data_samples/UDP_NE/CTX00000000{1,2,3}` and `REGENERATE_TEITOK=true bash api_4_stats.sh` gave OntoNotes
entities in `UDP_NE`/`TEITOK`, and the full suite stayed green (1053 passed). The committed-sample test now reads the
model from the *newest* paradata record. The real refresh needs a genuine NameTag run (LINDAT), so it is a user
action: provenance is not fabricated here.
* **Roadmap found on the way**: `# page_break = true` has three consumers and no producer. So table inputs without
layout lose their pages before UDPipe, and their TEITOK has one `<pb>`. That is an R4 item (umbrella plan §7).

## 2026-09-24: v0.21.0 released; #9/#28 closed; #38 opened; round-4 audit (TEITOK / flexi*)

* **Landed and released.** Round 3 reached `test` as `8a1ded3` + `ecdac10` (the annotated CoNLL-U fixtures and the
tier-1 page image came in the second commit, which is why `teitok-schema.yml` was red on `8a1ded3` and green on
`ecdac10`, runs 35974285161/35974294357). **v0.21.0** is tagged at `ecdac10` and its image published, so `:latest`
now writes TEITOK format 2. The hub E2E has not run since (its last run was on 2026-09-23), so the first E2E on
format 2 is still to come. _(It ran later the same day, after the push: run 35990199050, green — see the next entry.)_
* **Issues.** #9 and #28 closed; their exports left `issues/` in `3654e73`, and their digest+plan pairs are removed as
for #35 (leftovers carried to #38 and the umbrella plan §7). **#38 "Annotate flexiconv-converted documents
(FLEXICONV_ANNOTATE)"** opened as #10's action D: [`digests/38.digest.md`](digests/38.digest.md) ·
[`plans/38.plan.md`](plans/38.plan.md). #10 stays open for its real-document report.
* **Round-4 audit.** Same upstream heads as on 2026-09-23 (teitok.org, the TEI wiki and RIDE are blocked by the
egress policy, so the TEITOK author's code stays the reference). Format 2 conforms upstream except for four details
(split punctuation keeps a box, page size not on `pb@bbox`, TEITOK-project naming, `xpos` vs `pos`). Found:
  * ▶ UDPipe **chunk starts are written as pages** (`call_udpipe.py:117-118`) and read as pages by NameTag, the
    summary and the writer: CTX000000002 has 4 pages but one NE file and `page_id` 1 everywhere; a mid-page chunk start
    adds a phantom `<pb>` to an ALTO document. #38's "`# page_break` has no producer" was wrong.
  * ▶ **A sentence crossing a page stays on its first page** — already in the released sample (CTX000000002, page 4's
    first line is `lb-3.3` under `<pb n="3">`).
  * converted-document identity differs between stages 1 and 4; the gate runs the XSD only; `<pb facs>` is invented
    without an image; flexiconv failures are logged as `skip`; the service never has layout and mislabels gate failures;
    `/rescale`/`fix_teitok_bboxes.py` are single-surface and unclamped; `BBOX_ORIGIN` is not overridable per run.
  * Readers elsewhere: llm-enrich enriches **zero lines** from `.teitok.xml` (quality forced to 0.0) and its GPU path —
    like this repo's `llm_utils.py` copy — calls the line filter with 6 of 7 arguments; `teitok_read` never resets line
    numbers at `<pb>`; alto-postprocess renumbers TEITOK pages.
  * Upstream bugs to report: flexipipe misreads heads with document-global ids; flexiconv ignores `<dtok>`; flexicorp's
    regexes never match.
* **Decisions (user):** layout-first pages (`<pb/>` may sit inside `<s>`; chunk starts stop being pages; the stamp stays
`teitok-2`); `/enrich` accepts a flexiconv `.teitok.xml` and an optional ALTO file, image stays GPL-free; #9/#28 pairs
removed; the hub's misfiled `13.*` pair rewritten for the CAA paper.
* **Dev logs refreshed:** new #38 pair; #10 pair; umbrella plan (progress, round-4 re-check U1–U4, findings R4-1…R4-10,
decisions 5–7, Stage 7, roadmap). The work itself is Stage 7 of the umbrella plan.
* **Stage 7 implemented (same day; delivered as files, then pushed as `8003051`).** Pages come from the layout: stage 1 writes
`<doc>.rows.tsv`, stage 2 keeps it next to the CoNLL-U, `api_util/page_rows.py` places tokens by UDPipe's line-end
marks; chunk starts are `# chunk_start = K`; the writer puts `<pb/>` inside `<s>`/`<name>` where a page changes (released
CTX000000002 now has `pb-4` before `lb-4.1` "Soubor"), `pb@facs` only with a surface, `pb@n` labels, `pb@bbox`, no box on
split-off punctuation; `api_util/doc_identity.py` (one converted-file identity rule for stages 1 and 4); the stage-4
gate's default profile `contract` (unique ids, resolvable refs, page rules) exits 5; `api_flexiconv.sh` exits 3/1;
`/enrich`/`/jobs` accept a converted `.teitok.xml` or a table + `alto`; `/rescale` and `fix_teitok_bboxes.py` are
page-aware and clamped; the LLM line filter treats a missing quality score as unknown. Samples regenerated (rows files,
NE re-split by page). Fast suite 1123 passed. Migration note in `CONTRIBUTING.md` (Unreleased; suggested v0.22.0).
Same round in llm-enrich (re-vendor, filter, `xml_to_md`), alto-postprocess (`read_tei`) and the hub (`assert_teitok`,
docs). The user applied the #9/#28 pair removal on `test` (`787b683`).


## 2026-09-24 (later): round 4 on `test`; round 5 — format docs, writer warnings, dev logs

* **Pushed.** Round 4 is `8003051` on `test` and `master` (all CI green; TEITOK Schema Contract 35989955130). The same
change set landed in llm-enrich (`951db5e`), alto-postprocess (`fb72526`) and the hub (`eec0682`, which `v1` now
points at). The hub's E2E pipeline smoke ran on it: run 35990199050, green, the first run on format 2 with the strict
`assert_teitok` (CTX000000003, 1/1 references resolved); the digital-born smoke (35990199010) is green too. Not
released yet: v0.22.0 is suggested in `CONTRIBUTING.md`.
* **Round 5 (research + docs; one small code change).**
  * `api_util/teitok_alto.py`: `_build_page_scale_map` warns on stderr, once per document, when `INPUT_PAGES_DIR` has
    no image for a page, when an image's pixel size cannot be read, and when non-pixel ALTO units stay unscaled. Output
    unchanged (samples byte-identical); new tests in `tests/test_teitok_preservation.py`; fast suite 1128 passed.
  * `README.md` § "TEITOK XML": the standards the format builds on, how a file is composed from the line table,
    UDPipe, NameTag and the layout, the tools that write or read TEITOK (with licences), and 14 pitfalls — each a
    valid file that is wrong for its purpose (page-image names, ALTO units, print-space origin, stale files, page
    numbering by ALTO order, …). `schemas/teitok/README.md` links them; `CONTRIBUTING.md` Unreleased row updated.
  * Findings recorded in the umbrella plan (§3, round 5): alto-postprocess's ALTO splitter reads ALTO v3 only; the
    writer numbers pages by their order in the ALTO file while alto-postprocess keys pages by `PHYSICAL_IMG_NR`; only
    ALTO (and flexiconv's PAGE XML/hOCR conversions) bring boxes into TEITOK.
  * Dev logs: #6 (releases since 09-06, milestone), #7 (mapping ready in `ner_types.py`), #10 and #38 (pushed, E2E
    green, two #38 boxes can be ticked), #11 (cross-reference to #19), **#19 ready to close**, #18 (`annotation/` on
    `test`, the 08-01 tool comparison), the umbrella plan. Milestones relabelled on 2026-09-08 are now in every pair.

## 2026-09-26: AMČR baseline (atrium-project#67) — every digest+plan pair refreshed

* **What arrived (motyc, 2026-09-26):** [atrium-project#67](https://github.com/ufal/atrium-project/issues/67), AMČR's
  bucket for every open issue — close #10 and #38 (delivered, and kept off the production chain), #19 already closed
  (*"we stay with the OntoNotes model"*), defer #6, #7, #18 — plus #10 16:25 (close with or without the report) and #38
  16:26 (`/enrich` with a table and its ALTO is the line-table input AMČR will send, Trash and Empty lines left out).
  #67 also asks for a nlp-enrich **`keywords` block** (R5) and **nlp-enrich without its `llm` stage and vocabulary
  code** (R7). **Adopted by ÚFAL as binding.**
* **Also on the threads:** #38 — K4TEL 2026-09-25 05:34 (round 4 on `test`, writer warnings, README § TEITOK XML),
  11:43 (re-vendor `d300d24`; Pitfall 14 for Tesseract ALTO) and 2026-09-26 08:05 (*verification complete*: the live
  flexiconv → UDPipe → NameTag → TEITOK run and service parity — #38's G done); #10 — K4TEL 2026-09-25 05:35. #19 —
  K4TEL's 2026-09-25 close-out (the `NER_onto_VS_cnec.zip` evidence; OntoNotes labels as `@onto` in TEITOK format 2);
  closed 2026-09-26, its log removed (`40c48f0`).
* **Dev logs:**
  * `10.*`, `38.*` 🔒 **close-out** — #10's report gate optional; #38's G marked done; AMČR's line-table contract
    recorded (the NER path does no category filtering itself, so Trash/Empty filtering is AMČR's).
  * `6.*`, `7.*`, `18.*` ⏸️ **defer** — with the #67 R7 re-framing: #6's LLM half becomes llm-enrich's and its
    vocabulary one hub artifact (§7's mirror superseded); #7's and #18's LLM pre-annotation go through llm-enrich's
    engine.
  * `plans/teitok_conformance_plan.md` — **Stage 8** (TEITOK layout from the record's `lines[].bbox` +
    `pages[].canvas`, for born-digital documents; llm-enrich#10 §12 W5) and **Stage 9** (the `keywords` block, #67 R5);
    Decision 2's xmltokenizer path and the roadmap's flexipipe/xmltokenizer item marked off the production chain.
* **Pairs to remove** (issues closed): `11.*` (06-28), `19.*` (2026-09-26).

  **Not pushed: files delivered in chat.**

## 2026-09-30 (after the meeting): keywords leave for `ufal/atrium-keyword-extractor` (#40)

* **What arrived:** the meeting with AMČR gave both keyword kinds a repository of their own (the report's §2.2 row
  `keyword-extractor` · `/extract_keywords`); K4TEL opened #40 at 13:50: nlp-enrich keeps only the LINDAT calls.
  This supersedes #67's *"Statistical keywords belong to nlp-enrich"* (09-30 06:56) and #73's owner line.
* **Dev logs:**
  * `40.*` 🆕 — the repository seeded with the history of both sources (llm-enrich's copy is the base for the three
    diverged files: `llm_utils.py` 404 diff lines, `vocab_build.py` 43, `llm_run.py` 11); one service,
    `/extract_keywords` (`kind=statistical|controlled|both`, KeyBERT default); the `keywords` block and the successor
    of the `llm-enrich` program; the vocabulary as a release asset; nlp-enrich 0.23.0 (keyword parameters deprecated)
    then 1.0.0 (removed; CPU-only image).
  * `6.*` 🔄 status: the code moves with #40; still deferred.
  * `7.*`, `18.*` 🧭 banners: custom NER stays here (served through NameTag); the LLM pre-annotation uses
    keyword-extractor's engine.
  * `plans/teitok_conformance_plan.md` — Stage 9 (nlp-enrich writes `keywords`) marked superseded; the projection
    reads the block via `/project_record` after keyword-extractor.
* **Found:** the default keyword method differs between the CLI (`keywords.py:80`, `yake`) and the service
  (`service/api.py:97`, `keybert`); the base image installs `yake`, `keybert`, `sentence-transformers`
  (`requirements.txt:7-9`), which is what makes it a torch image.

  **Not pushed: files delivered in chat.**

## 2026-09-30 — atrium-project#72 round 1: the production image declared; review tools off the images
* `.github/production-image.json` (the `api` target: the service, `run_pipeline.py`, the `api_*.sh` scripts and the
  `api_util/*.py` they run; the keyword/LLM files as `moving` rows until #40 takes them out), checked by the hub's
  `tools/ci/image_closure.py`.
* `.dockerignore` keeps `corpus_review.py` and `vocab_review.py` out of the images (unreached by every entrypoint);
  README notes they run from a checkout. `docker.yml` names `api` as the production target.
* Revendored the three declared-rename files. Tag draft: `v0.23.0`. **Not pushed: files delivered in chat.**


## 2026-10-05 — The hub round of 2026-10-05 re-vendored; born-digital `Garbage`/`Inverted` lines left out
* **Found in the round's end-to-end check** (digital-convert record → ocr-postprocess OCR hand-off → this service):
  `_SKIPPED_CATEGORIES` was `{"Trash", "Empty"}`, so the lines digital-convert labels `Garbage` or `Inverted` (a
  born-digital text layer that does not decode) were read as text, and keywords were extracted from mojibake
  (`sondì`, `høeby`). The hub registry `atrium_vocab.UNTRUSTWORTHY_LINE_CATEGORIES` (`Garbage`, `Inverted`, `Trash`)
  is the one declaration downstream filters key off; digital-convert's `json_to_md` already uses it.
* **Code:** `service/api.py` builds `_SKIPPED_CATEGORIES` from the vendored registry, plus `Empty`; the
  `document_json` help (the spec's description) names the four. `tests/test_api_service.py`: the record carries a
  `Garbage` and an `Inverted` line, and the set is pinned to the registry. README and `service/README.md` updated.
* **Re-vendored** (hub round of 2026-10-05): `atrium_document.py` (the OCR hand-off per page), the record schema
  (`pages[].text_layer`), `atrium_service.py` (`source_digest_mismatch`), `test_document_originators.py`,
  `test_schema_freeze.py`. `service/openapi.json` regenerated: the reason code and the description; compatible with
  `v1.0.0-beta`.
* **Checks:** full suite 756 passed, 4 skipped (with `yake` installed; `tests/test_api_service.py` skips without it).
  No version bump: the next release carries it.

  Files delivered in chat; pushed by the maintainer as `6a6619d`.

## 2026-10-05 (evening) — Issue logs refreshed after the split's releases
* **#1 pair:** rewritten for the released split:
  * the statistical service in `v1.0.0-beta`;
  * nlp-enrich LINDAT-only;
  * digital-convert's LLM copy gone in `v1.1.0-beta`.

  Of its 76 files, 52 are byte-identical here, 14 differ and 10 are absent, so no repository holds a complete copy on
  `test`. V-6 (`6a6619d`) is unreleased.
* **#2 digest:** a 2026-10-05 banner that points to the per-file list, posted on #2 at 11:37 UTC.
* **DEVLOG:** the 2026-10-05 entry names its commit (`6a6619d`).

  Files delivered in chat; the maintainer pushed the pairs as `57f2ce5`.

## 2026-10-07 — The LLM half received: the 24 files reconciled, the controlled kind in the service
* **#1/#2, the 24 files** digital-convert `31534d5` held differently (the list posted on #2 on 2026-10-05):
  * 10 absent ones ported and adapted (`llm_client_shared.py`, `openrouter_client.py`, `ollama_client.py`,
    `requirements_remote.txt`, six tests; `tests/test_service_document_json.py` now tests this service);
  * merged: `llm_utils.py` (taken whole: offload auto-sizing, quoted config values, the counted prompt cut),
    `llm_run.py`, `requirements_llm.txt`, `tests/test_limits.py`, `tests/test_llm_run.py`;
  * kept, this side newer: `vocab_build.py`, `vocab-drift.yml`, `docker-compose.gpu.yaml`, `tests/test_llm_utils.py`,
    and five vocabulary files that differ only in their generation stamps. File by file: plan 1 §A.
* **The prompt reaches every sender.** The arrived `llm_client_shared.py` sent its own literal (the strict guardrail
  after M11/M12, no `PROMPT_*` flag, no `teater_category_ids`, the qualifier left on). It now renders
  `prompts/system_prompt.txt` like `llm_run.py`, attaches the ids, strips the qualifier, and refuses a guardrail
  wording the vocabulary contradicts; a test pins its untruncated prompt to `prompts/prompt_full.txt`.
* **Service:** `POST /extract_keywords` `kind=controlled|both`: line mode over the record's lines through
  `LLM_BACKEND` (OpenRouter or Ollama); the record comes back with `enrichment` and `entities[].pid`; `/info`
  `controlled` says what runs or why not. 501 without a backend, 502 when every call fails, 422 when every reply is
  cut. The `LLM_*` limits joined `tool_limits.py`, `.env.example` and `service/README.md`; the spec is regenerated
  (additive: the pinned oasdiff finds no breaking change against `v1.0.0-beta`); `.github/production-image.json`
  gained the 5 files the entrypoint reaches; the images carry the built vocabulary (`.dockerignore`), no weights.
* **Found on the way:**
  * the clients and `llm_run.py` logged `llm_config.txt` whole into paradata, credentials included (now redacted);
  * `requirements_llm.txt`'s `torch==2.7.0` made the GPU lane's install unsatisfiable next to `vllm>=0.30.0`;
  * `llm_run.py --help` was read as a config path;
  * `llm_run.py` stamped its paradata `nlp-enrich`.
* **Checks:** 980 passed with a CPU torch (the 4 GPU-lane files skip without it); `ruff` clean; `prompt_template.py
  --check`, `vocab_build.py --from-flat --skos --check` and the hub's `image_closure.py` clean.
* **Dev logs:** #1 and #2 digests and plans refreshed (milestones as the live issues have them).

  Files delivered in chat as a zip; pushed as `f4b0118`.

## 2026-10-07 (later) — The API meta-contract lane installs `tqdm`
* **Red since `f4b0118`:** API Meta-Contract ([run](https://github.com/ufal/atrium-keyword-extract/actions/runs/37629003315))
  had 35 passed and 4 errors. The `controlled` fixture (`tests/conftest.py`) imports `openrouter_client`, which imports
  `tqdm` at module level. The hub's reusable lane installs `requirements-test.txt` only, and `tqdm` was declared in
  `requirements.txt` alone. The 980-test run of the previous entry had both files installed, so it could not see this.
* **Fix:** `tqdm` repeated in `requirements-test.txt`, like `jsonschema` and `lxml`. The image was never affected: the
  `api` stage inherits `requirements.txt`, and the service imports the clients only for a configured backend. The
  release gate's `atrium_openapi.py check` passes on the test deps alone, before and after.
* **Checks:** a fresh Python 3.11 venv with `requirements-test.txt` only: `tests/test_api_contract.py` +
  `tests/test_openapi_contract.py` 39 passed (was 35 + 4 errors); `tests/test_service_requirements.py` 9 passed.

  Files delivered in chat; pushed as `21ab612`.

## 2026-10-07 (later) — The controlled kind against a real backend in CI
* **Why:** every controlled-kind test stubs the model's chat function, so a provider that refuses the
  request (the vocabulary's schema as `response_format`, about 120 KB; a prompt of about 50k tokens) or
  replies that stop validating would stay green. The maintainer added an `OPENROUTER_KEY` secret here.
* **`tests/test_controlled_live.py`:** the service's own warm-up against the configured backend, then one
  `/extract_keywords` call (`kind=controlled`) with a schema-valid record after nlp-enrich, two lines. Asserts:
  `/info` ready; the response against the published spec; both lines answered within the vocabulary, not
  both meta-text; the record valid with its `enrichment` stamp and the entity's `pid`; the `CreateAction`
  valid, naming the model and both vocabularies. The categories chosen are printed, not asserted. The
  module skips unless `ATRIUM_LIVE_BACKEND=1` (the translator's live-backend switch); opted in without a
  backend, it fails.
* **`.github/workflows/controlled-live.yml`:** maps the secret to `OPENROUTER_API_KEY`; the model is the
  manual run's input, else a repository variable `OPENROUTER_MODEL`, else `openai/gpt-4o-mini`. It runs on
  demand, weekly, and on `test` pushes that touch the controlled kind's files, never on pull requests.
  It installs `requirements-test.txt` only.
* **Docs:** a CONTRIBUTING sentence under heavy tests, and a line in the service README.
* **Checks:**
  * against a local stand-in for OpenRouter's chat endpoint: 6 passed; both requests carried the key,
    `X-Title`, the model and a `json_schema` response format;
  * not opted in: 1 skipped; opted in without a key: fails, naming `OPENROUTER_API_KEY`;
  * the full suite in the test-deps-only venv: 920 passed, 6 skipped;
  * the hub's `workflow_lint.py` (v1) and actionlint: clean. The lint caught the first draft's concurrency
    group, which let a push cancel the weekly run; `github.event_name` is now in the group.
* **Not run:** a real OpenRouter call; there is no key in this sandbox.

  Files delivered in chat; pushed as `21ab612`.

## 2026-10-07 (evening) — A release carries the vocabulary
* **Why:** the translator's glossary and the hub's E2E read the built vocabulary, and building it takes a harvest
  of two upstream services. A release asset is the stable copy (atrium-project#72, #1 here).
* **`.github/workflows/release.yml`:** a step "Package the vocabulary (CC0)" before "Create GitHub Release" packs the
  committed `data_samples/vocab` files as `atrium-vocabulary-<version>.zip` (fixed timestamp and file order, so the
  same files give the same checksum) with a `.sha256`, and both are attached by the step that creates the release,
  because an immutable release refuses assets added afterwards. Gates first: `vocab_build.py --check` (the committed
  nesting is what the taxonomy config produces); the tag equals `para_config.txt`'s version; the three sidecars are
  stamped with that version (`--check` blanks `tool_version`, so the stamp is compared in the step); every source
  is CC0. A `workflow_dispatch` on a branch runs the gates without a tag.
* **`CONTRIBUTING.md`:** item 5 under the vocabulary gates: after the version bump, `python3 vocab_build.py
  --from-flat --skos`, commit, then tag.
* **Checks:** the step run locally on `test`: `atrium-vocabulary-v1.1.0-beta.zip`, 12 files, 4,718 terms, the same
  checksum on a second run; a wrong tag and a stale stamp each stop it; actionlint and the hub's `workflow_lint.py`
  clean.
* **Not changed:** no `llm_api` row in `para_config.txt`. The file records the missing row as an open item (the
  licence is the chosen model's, and a per-model lookup is still to be written); adding a blanket row would make
  every controlled-kind record "maximally restrictive" before hub #6 has settled what an output licence means.
* **For the maintainer:** the asset appears from the next tag; `v1.1.0-beta`, already released, has none.
* **Dev logs:** the pairs of #1 and #2 refreshed: `v1.1.0-beta` is released, the unpushed list is down to the
  vocabulary asset, and the live lane is recorded.

  Files delivered in chat; pushed as `0764363`.

## 2026-10-08 — The A1 facet layout and the malta split (#2)
* **Why:** @david-spacil's calls of 8 October (comment 6057405985): A1-facets, the nine collision groups the
  reinstatement added, and the D1 rubric. The next release is the first to carry the vocabulary asset, so it
  carries the approved layout.
* **`data_samples/taxonomy_config.json`:** `teater_branch_map["1"]` (Theory and approaches, 95 terms) → `Methods`;
  `heslar_map["jazyk"]` → `__exclude__`, registered in `_exclusions` as `settled` with his reason (a document's
  language: metadata, not content; includes `nerelevantní`); `heslar:jazyk` leaves `geo_guardrail.covers`, since
  the register check refuses a covered rule excluded for any reason other than `open_geo_ethnic`.
* **`data_samples/taxonomy_overrides.json`:** `amcr:HES-001366` gets `qualifier_cs: "stát"`. The country is offered
  as `Malta (stát)`; mortar (`HES-000910`) keeps the bare `malta`. The other eight groups merge, which the build
  already did.
* **Regenerated** in the runbook's order: the three nestings, sidecars and placement audits, `vocabulary.csv`
  (`union.skos.ttl` is unchanged: it carries the sources' records, not the layout), the review sheets
  (`facet_census.csv`, `context_budget.csv`, `exclusion_impact.csv`, `reinstatement_preview.csv`,
  `specificity_pairs.csv`) and `prompts/prompt_full.txt`. 4,718 terms → 4,711: Methods 198 → 293,
  Cultural & Geographic Context 972 → 965 (eight language names out, `Malta (stát)` in; `latina` stays as
  TEATER 2770, which dedup had folded into the excluded AMČR record), Related Disciplines & Society 1,666 → 1,571.
* **What the move costs:** at a 32k window `Cultural & Geographic Context` is now cut too (905 of 965 kept;
  Related Disciplines & Society was already cut and is now dropped whole). From 128k nothing is cut.
* **Tests:** `tests/test_vocab_build.py` (facet counts, teater:1 under Methods, the language list gone with
  `latina` kept, the malta split, eight splits in the verdict set) and `tests/test_vocab_review.py` (jazyk
  settled, out of `covers`; the Q1 reinstatement test no longer lists it). The 7 new tests and the 2 rewritten
  ones fail on the previous vocabulary.
* **Docs:** `data_samples/vocab/RUNBOOK.md` (the A1 section records the ruling; the malta warning is resolved;
  counts and truncation figures), `6.D-eval.decision-package.md` (a "Decided 2026-10-08" block: D1-a … D1-f,
  narrower-than-gold is wrong with its own cell, split homonyms scored on the qualified form resolved from
  `teater_category_ids`), the counts in `prompts/RUNBOOK.md`, `README.md`, `service/README.md` and three comments.
* **Not changed:** `atrium_vocab.py`, the hub-shared module. Its mirror maps still say `jazyk` → Cultural &
  Geographic Context and `1` → Related Disciplines & Society; nothing checks them against the config, and fixing
  them means a hub change and six revendors, so it waits for the next shared-module round.
* **Checks:** full suite 926 passed, 6 skipped; ruff clean; `vocab_build.py --from-flat --check` and
  `prompt_template.py --check` clean; the release workflow's vocabulary step run locally passes
  (4,711 terms), and after a simulated bump it refuses the stale stamp until `vocab_build.py --from-flat --skos`
  re-stamps it.

  Files delivered in chat; pushed as `4c72129`.

## 2026-10-09 — The `keywords` block (atrium-project#73); v1.2.0-beta carries the vocabulary
* **`llm_client_shared.write_document_record()`** takes an optional `keywords` block; `results=None` leaves
  `enrichment` and `entities[].pid` alone.
* **`service/api.py`:** `_run()` writes the record once, at the end, when a record was sent and the statistical kind
  ran or the controlled kind contributed: `keywords = {document, pages}` from the same lists the response returns,
  `enrichment` from the controlled results. `kind=both` puts both blocks into one record and never mixes them;
  `/extract_keywords_text` writes no record. The `document_json` description says so (spec regenerated).
* **Tests:** `tests/test_api_service.py` (5 new: the statistical kind writes the block, `per_page=false`, a rerun
  replaces it, a seed's `doc_id` is kept, the text endpoint returns no record); `tests/test_service_document_json.py`:
  the two tests that encoded "the statistical kind writes no record" now assert the new contract.
* **Docs:** README, `service/README.md` (the record paragraph, the table row, the example, the kinds).
* `atrium_document.py`, `atrium_document.schema.json`, `service/atrium_service.py`,
  `tests/test_document_originators.py` and `tests/test_schema_freeze.py` re-vendored from the hub.
* **Version `v1.2.0-beta`:** `CITATION.cff`, the `CONTRIBUTING.md` row, `para_config.txt`, the spec's `info.version`.
  `python vocab_build.py --from-flat --skos` restamped the three sidecars (`tool_version`, `generated_utc`; the
  vocabulary unchanged, `--check` up to date), so `release.yml`'s gate passes and the tag attaches
  `atrium-vocabulary-v1.2.0-beta.zip`.
* **Checks:** 965 passed, 5 skipped; ruff check and format clean; spec current; image closure OK; `vocab_build.py
  --from-flat --skos --check` up to date.
* **Dev logs:** the pair of #1 refreshed.

  Files delivered in chat; pushed as `ba89996`, tagged `v1.2.0-beta` at `523143a`.

## 2026-10-13 — Shared modules re-vendored (atrium-project#51, atrium-nlp-enrich#41)
* `atrium_rocrate.py`, `atrium_vocab.py`, `atrium_document.schema.json`, `service/atrium_service.py`,
  `tests/test_atrium_rocrate.py` and `tests/test_schema_freeze.py` re-vendored from the hub:
  * the crate names AMČR/TEATER concepts by their source URIs, from `teater_category_ids`, and no longer mints
    `w3id.org/atrium/theme/<label>`;
  * the schema declares `enrichment.items[].teater_category_ids`;
  * the registry's theme maps follow keyword-extract's taxonomy;
  * the shared 502 text says when to retry.
* `service/openapi.json` regenerated (the record schema and its sha, the 502 description). No behaviour change, no
  release.
* **`tests/test_vocab_theme_maps.py`** (new): the vendored `HESLAR_TO_THEME` and `TEATER_BRANCH_TO_THEME` must equal
  `_settings.heslar_map` and `_settings.teater_branch_map` in `data_samples/taxonomy_config.json` (less the
  `__exclude__` entries). The 2026-10-08 layout changed both, and nothing noticed. From now on a taxonomy edit
  fails here until the hub's registry follows.
* **Checks:** the API-contract and vendored shared tests, 222 passed; `tests/test_vocab_theme_maps.py`, 3 passed
  (2 of them fail against the maps before this round); vocabulary, record, service and LLM-client tests, 316 passed,
  1 skipped; ruff check and format clean on the new test.

  Files delivered in chat; pushed as `9c8d0c4`, except `tests/test_vocab_theme_maps.py`, which did not land (re-delivered on 2026-10-15).

## 2026-10-15 — Issue logs: the #2 runs of 11–13 October; the theme-map test re-delivered
* **#2, 11–13 October** (on `test` as `5c6ffe0` … `dab512c`; no entry was written then):
  * **10-11, the GPU path:** `llm_run.py` could not enrich a document on either backend. Fixed: the call signatures,
    vLLM's structured-output API, the prompt fitted to the served window (`vocab_prompt_budget_tokens`), the target
    line kept after a cut, `pysqlite3` optional, `config.prompt` in the paradata; `tests/test_llm_run_contract.py`.
    The `zeme` sub-header reads `země`.
  * **10-12/13, the cluster runs:** lm-format-enforcer's per-token state freed after each line, `REUSE_PROMPT_CACHE`,
    the label enum indexed by prefix, one BOS, YaRN for the 32k Qwen models, AWQ on vLLM, the allocator setting kept
    from vLLM's workers, FlashInfer's sampler off, `VLLM_BATCH_SIZE`, `--download` for the offline nodes, models for
    2× 24 GB.
  * **17 runs** in `data_samples/KW_PER_DOC_LLM_<model>/`: 19 documents, 1,029 lines each (three runs miss 3–71).
  * **`2bd5db4`:** the category enum takes either case of a label's first letter (`category_case_folding` in the
    paradata). No committed run has it: nine still carry forced labels (`Artemísion`, `Slovensko`, …), counted in the
    #2 digest.
* **`tests/test_vocab_theme_maps.py` (new):** the 10-13 entry names it, but it did not land. Five tests:
  `HESLAR_TO_THEME` and `TEATER_BRANCH_TO_THEME` equal `_settings.heslar_map` and `teater_branch_map` less the
  `__exclude__` entries; the facets equal `THEMES`; every mapped theme is one; `jazyk` is absent and branch `1` maps
  to Methods.
* **atrium-digital-convert#6, phase D:** the whole-document clients send the Markdown that digital-convert's renderer
  writes (`JSON_TO_MD_CONVERTER = "json_to_md@1.1"`, `llm_client_shared.py:1126`). The renderer escapes text that
  could forge a cue, so no second defence is added here. If the escaping bumps `CONVERTER_ID` there, this constant
  follows.
* **Dev logs:** this header (it named atrium-nlp-enrich). The #2 pair is consolidated:
  * the title is fixed (it said "Issue #6");
  * the runs and the case-fold fix are recorded;
  * the decision register keeps what is in force;
  * the plan runs: clean runs → a home for the corpus (atrium-project#16) → gold labels → scorer → score.
* **Checks:** `pytest tests/test_vocab_theme_maps.py`, 5 passed, and it fails when a map entry is changed;
  `vocab_build.py --from-flat --check` up to date; `prompt_template.py --check` clean.

  Files delivered in chat.

## 2026-10-16 — #2: the runs reviewed; the remote paths take either case; v1.3.0-beta
* **#2, K4TEL's review** (comment 6216185215): forced capital labels in ten runs (`qwen3-14b` too); the cause is
  the enum decoder finishing whatever label shares the prefix the model began (`zvonice` for Bell Beaker vessels,
  `Pentelikon` for *peníz*, `jámová kultura` for *jímka*); `confidence_score` cannot rank (91 % at 0.95 or 0.85);
  three options proposed: prompt blocks, the halves of composites, free decoding. Duplicated periods and
  `**suborál` for @david-spacil.
* **`500372a`:** the service and the OpenRouter/Ollama clients accept either case of a label's first letter after the
  reply; the schema sent stays the label enum. The comment cites it as `03b3306`, its hash before the rebase.
* **v1.3.0-beta** (`88cf1aa`; the vocabulary asset re-tagged in `59132b3`): the GPU path, 17 sample runs, the case
  fix on every path, `teater_category_ids` in the record schema, source URIs in the RO-Crate.

## 2026-10-19 — #2, round 3: Options 1 and 2, the scorer, `**suborál`, Known limits (delivered, not on `test`)
* **Option 1, three prompt blocks** before the vocabulary, each with a `PROMPT_*` flag, on by default:
  `rule.category_from_list`, `rule.most_specific`, `rule.confidence` (the rubric, moved from the schema
  descriptions the GPU path never shows). Fourteen blocks, twelve flags; the four prompt sheets and
  `context_budget.csv` regenerated (8 192 tokens: 397 terms; 32 768: 3 057). `/info` `controlled.prompt` and the GPU
  paradata `config.prompt` name the blocks (`blocks`).
* **Option 2, the halves of composites:** `vocab_review.py --composite-halves` writes
  `data_samples/vocab/composite_halves.csv` (115 rows; 103 halves of 76 composites). The rule accepts 79; 13 are
  `ambiguous` (the 7 shared by several composites, 6 that begin other labels), 11 `fragment`. A reviewer's `verdict`
  overrides it and survives regeneration. `llm_run.build_schema` decodes an accepted half and records its
  composite; `llm_client_shared.build_schema` and the document resolver accept it after the reply.
  `ACCEPT_COMPOSITE_HALVES` (default true) and `COMPOSITE_HALVES_PATH` in `llm_config.txt`; with the switch on and
  no sheet, the controlled kind and the runs stop with the fix. `.dockerignore` keeps the sheet in the api image.
  `/info` and paradata count the halves (`composite_halves`). The spec gains the two fields (additive).
* **`score_categories.py`** (top level, torch-free; not in the image): expected lines from `gold_workbook.csv` or
  the inputs through `should_process_line`; per run missing and unexpected lines, meta-text, forced capital labels
  and the 10-16 watch list, lines sharing no word with their category, confidence spread; agreement between runs;
  a `KW_PER_DOC_LLM_R<n>_<model>` run against its earlier run; strict accuracy where gold is filled. No line text
  in its output. On the committed runs it gives 1,029 expected, 71/15/3 missing, and the 10-16 table.
* **`**suborál`:** Markdown at the edge of a TEATER label is dropped at harvest and when a flat file is read (nine
  fields, `**suborál (paleoklimatologie)` and `*předmět ze zlata` among them). The committed harvest of 09-04 is not
  re-fetched: a fresh one adds fields to every record, and its labels equal what the read now gives. The nested
  files, `vocabulary.csv` and the SKOS view change, so the vocabulary asset of the next release does.
* **Docs:** `service/README.md` gets Known limits (forced labels, `confidence_score`, research output, the KeyBERT
  cache), the halves, and an `HF_HOME` row; README.md's "constrained" paragraph says what the enum does not
  guarantee; the data runbook has nine sheets and 31 files; `llm_config.txt:48` lists the six vLLM runs.
* **Cluster kit K1** (`atrium-keyword-extract__cluster__issue2_rerun_job.sh`): the five models, each into its own
  `OUTPUT_DIR`, then the scorer.
* **Checks:** `pytest -m "not slow"` 1,039 passed, 5 skipped; `vocab_build.py --from-flat --skos --check` and
  `prompt_template.py --check` clean; ruff clean; `atrium_openapi.py compare` against `v1.3.0-beta`: compatible.

  Files delivered in chat.

## 2026-10-19 (evening) — #2: K1 read; v1.4.0-beta prepared
* **On `test`:** round 3 (`672ab3e`; `dfa4560` fixed the Vocabulary Drift job, which has no pydantic); K1's runs
  (`ebee156`, `KW_PER_DOC_LLM_R3_*` with paradata: the three new blocks, 79 halves, case folding).
* **`score_categories.py`** on the four complete runs against their earlier runs (forced capitals; 10-16 watch list):
  - `qwen-3.8-27b-it`: 0 → 0; 0 → 0.
  - `qwen-3.8-27b-fp8`: 1 → 0; 2 → 0.
  - `qwen-3.6-35b-moe-fp8`: 0 → 0; `prahory` 2 → 2.
  - `qwen-3.6-27b-it`: 0 → 1; `zvonice` 12 → 10.

  The top-2 confidence share falls (0.97 → 0.92 for Qwen3.8). `qwen3-14b` is still running: 9 documents, `zvonice` 10.
* **`v1.4.0-beta` prepared:** `MODEL_KEY` (and `llm_run.py`'s fallback) = `qwen-3.8-27b-it`; `para_config.txt`,
  `CITATION.cff`, the spec (version; compatible with `v1.3.0-beta`), the CONTRIBUTING row (table re-padded).
  The vocabulary asset changes (`**suborál`).
* **`service/README.md` as a runbook** (atrium-project#77 A.3, before the `v1.4.0-beta` tag):
  - Start with the image;
  - Models and caches: the KeyBERT model is fetched into `HF_HOME` at start, at no pinned revision;
  - "What to do" on every error row;
  - Partial results: `kinds`, `limits_applied`, `controlled.stats`.

  Forced labels in Known limits now cite K1. The hub's `runbook_check.py` passes.
* **Release blocker removed:** the vocabulary sidecars were still stamped `v1.3.0-beta`, which `release.yml` refuses
  for a `v1.4.0-beta` tag; `vocab_build.py --from-flat --skos` restamped them (nothing else changed). README.md no
  longer says the asset "is to be published".
* **The first `v1.4.0-beta` tag** (on `2d633c8`, pushed before the restamp) failed exactly there: Release run
  39271331164, "the vocabulary sidecars are stamped … v1.3.0-beta". No release was published, so immutability does not
  hold the tag: it is deleted and set again on the `test` head that carries the restamp, as for `v1.3.0-beta` on 10-16.
* **`v1.4.0-beta` published** (10-19 20:20 UTC, immutable) on `a3dc910`: Release run 39318278363 and Docker run
  39318278919 green; the assets' checksums verify, and `openapi.json` (`360be5ae…`) is what `/info` reports.
  **The image tags moved once:** the first tag push had already built and promoted `1.4.0-beta` and `latest`
  (Docker run 39271331694), so from 15:05 to 20:41 UTC they named the `2d633c8` build, now only `sha-2d633c8`
  (API `sha256:41d975ca…`); since then the `a3dc910` build (API `sha256:3ce80276…`). Same code; the earlier image
  lacks the runbook and carries the `v1.3.0-beta` stamps. A tag ruleset would have refused the move and forced
  `v1.4.1-beta`; this repository has none yet (atrium-project#72).
* **Dev logs:** `{2}` (K1, the 13 ambiguous halves for @david-spacil, Option 3 open).

  Files and the #2 comment delivered in chat.

## 2026-10-21 — The adopted owner commit; the GPU lane's optional exit marked (atrium-project#82, #81)
* `tests/test_vendored_teitok_parity.py`: `ADOPTED` names atrium-nlp-enrich `6726124…` (`v1.1.0-beta`), with a test
  that it is a full commit SHA. Both pinned files match nlp-enrich at that commit.
* `.github/workflows/gpu-inference.yml`: the exit-5 path carries `# ci-optional:` (the hub's new lint rule) and
  writes its reason to the job summary.
* **Checks:** the parity module passes; the hub's `workflow_lint.py` passes on this repository.

## 2026-10-21 (round 2) — The agent-skill branch gets a skill of its own (atrium-project#77 C)
* The branch carried nlp-enrich's skill. Removed: its client, pipeline scripts, `api_util` stages, schemas,
  frontend, jobs and rescale modules and samples (30 files, none on `test`). New: `SKILL.md`
  (`atrium-keyword-extract`), the client `scripts/atrium_keywords.py` (records → `/extract_keywords`, texts and stdin
  → `/extract_keywords_text`; `--kind`, `--method`, `--out-dir`; `ATRIUM_KW_URL`; the 502 rule, so a 502 from the
  LLM backend is reported at once), `scripts/server.sh` (the release image, which carries the vocabulary; `--gpu`;
  `--local` in `venv-kw`; `/ready`), two synthetic samples (a text, and its record written by digital-convert), the
  branch README, and `service/README.md` as the runbook. The skill says that the controlled kind needs the published
  image and an LLM backend.
* **Checks:** the client against a local server (YAKE): records, texts, stdin, CSV/JSON, 501 without a backend,
  422 `invalid_record`, the legacy method without lemmas, `limit_exceeded`; skill-validate steps 1–4a; drift check
  aligned. Delivered as `atrium-keyword-extract-agent-skill.zip`, not pushed.

## 2026-10-21 (round 3) — The skill branch carries the vocabulary; a stray file; the TEITOK adoption prepared
* **The agent-skill branch carries what the image carries** (atrium-project#77): the hub's `skill_ify.py` now keeps
  the `data_samples/` files `.dockerignore` lets into the image, so the branch has the vocabulary and the taxonomy
  (7 files, 6.3 MB) and a server built or started from it serves the controlled kind. Checked with a local server
  from the skill tree and a stand-in backend: `/info` `controlled.ready` true, 4,712 terms. SKILL.md, the branch
  README, `service/README.md` and `scripts/server.sh` no longer say the controlled kind needs the published image;
  the runbook links the two vocabulary files the image leaves out (`RUNBOOK.md`, `gold_workbook.csv`) to `test`.
  `ker_data/` stays off the branch (no shipped code reads it).
* `api_util/__init__` (empty, no `.py`, read by nothing) is removed from `test` and `agent-skill`.
* `plans/2.plan.md`: `v1.4.0-beta` was published on 10-19, not "prepared". The closed #1's pair is removed.
* **The adoption of nlp-enrich's owner header (atrium-project#82), prepared:** `api_util/teitok_read.py` from
  nlp-enrich `477f68c`, `VENDORED` re-pinned, `ADOPTED` = `477f68c` / `v1.1.3-beta` (on `test` and `agent-skill`).
  A separate archive, to push after nlp-enrich's `v1.1.3-beta`. `tests/test_vendored_teitok_parity.py`: 6 passed.

## 2026-10-22 (round 4) — The README on the skeleton (atrium-project#79); #2 for the pilot; the lane notifier (#81)
* **atrium-project#79:** README 349 → 109 lines on the hub's template; the moved text, unchanged, in `docs/usage.md`
  (setup, the service, the batch CLI, the controlled kind's command lines, Docker), `docs/how-it-works.md` (the two
  kinds, the vocabulary), `docs/reference/outputs.md` (the CLI's files and scores) and `docs/reference/licences.md`.
  The Quick start was run (`/extract_keywords_text`, YAKE). Headings plain in README and CONTRIBUTING; the
  acknowledgements name ATRIUM, LINDAT/CLARIAH-CZ and AIS CR. Map: the hub's
  `plans/79.keyword-extract_relocation_map.md`. `docs_check` OK. It lands with the next code release.
* **#2:** motyc (10-22): the constrained vocabulary stays for the pilot; Option 3 after it, compared on the gold set
  and only as an intermediate step; curated mappings keep both sources' labels and ids. Dev logs `{2}` updated
  (ruling D2). No code change.
* **atrium-project#81:** `scheduled-smoke.yml` and `vocab-refresh.yml` open or update one issue per failing lane
  through the hub's `lane-failure-issue` action (needs the hub's new `v1`).
* **atrium-project#51:** `atrium_vocab.py` and its two shared tests re-vendored.
* **Checks:** 1,044 passed, 5 skipped; `ruff` clean; `workflow_lint.py` against the new hub.

## 2026-10-25 — The ORCID; the release gate; the live lane reports failures (atrium-project#13, #81)
* **Shared modules (hub re-vendor, atrium-project#13, #6, #79):** `atrium_rocrate.py` writes David Novák's
  correct ORCID (`0000-0001-6592-6291`) as a tool creator in every crate; `atrium_document.schema.json` describes
  `provenance.license*` as calculated from the components, not the output's licence (descriptions only, no
  `POST_FREEZE_CHANGES` entry); an `atrium_vocab.py` comment names page-classification's new categories page.
  `service/openapi.json` regenerated: description-only, and the `x-atrium-record-schema` digest.
* **`CITATION.cff`:** the ORCID corrected; each author's affiliation in its ROR name (Charles University;
  Czech Academy of Sciences, Institute of Archaeology, Prague). Authors unchanged until they confirm (#13).
* **atrium-project#81:** `release.yml` gains the `image` job (the hub's `docker-tool.reusable.yml` with this
  repository's `docker.yml` inputs and `release-gate: true`), the `simulate-probe-failure` dispatch input, and
  `images.json` in the release; `docker.yml` no longer runs on tags. It takes effect at the next tag, after
  digital-convert's dispatched demonstration. No version bump.
* **atrium-project#81:** `controlled-live.yml` opens or updates one issue when its weekly run fails (the hub's
  `lane-failure-issue`); its header no longer claims a push trigger it does not have.
* **#2:** pair refreshed; no new comment, nothing changes for the pilot.
* **Checks:** 1,017 passed, 6 skipped; `workflow_lint` OK.


## 2026-10-25 (evening) — CONTRIBUTING links the two checklists; the documentation check in CI (atrium-project#79, #81)
* **CONTRIBUTING (atrium-project#79, #81):** the "Repository Documentation Management" section links the
  hub's documentation style guide and `ci_policy.md#changing-ci`, the questions a new or changed CI check
  answers, as the hub's CONTRIBUTING template does. Nothing else in the file changed.
* **The documentation check in CI (atrium-project#79 E):** Workflow Policy Lint runs the hub's
  `tools/docs_check.py` over this repository, advisory until the newcomer review, from the pin to the hub commit
  that carries it (atrium-project#72 step B). It passes today.
* **Quick start:** every endpoint, field, flag and sample file it shows exists at `v1.4.0-beta`, the release it
  names (a static check; running it needs Docker and the Hugging Face Hub or LINDAT).
* **atrium-project#81:** the release gate gets one clean dry run (`release.yml` dispatched on `test`)
  before the next tag.


## 2026-10-25 (night) — The hub's reusables by commit (atrium-project#72)
* **Hub by commit (atrium-project#72 E.4):** every hub reusable caller (8) and hub-action step (3) runs at
  `@18f06680dfb6…  # v1`; `para-drift` and `workflow-lint` read the hub at the same `hub-ref`, and the lint has
  `require-sha-pins: true`, so a caller or action left at `@v1` fails it. A hub change reaches this repository only
  through a pin move (`scripts/pin_hub_reusables.py` in the hub).
* **The documentation check (atrium-project#79 E)** comes with this hub commit: Workflow Policy Lint now runs
  `docs_check.py` over this repository, advisory.

---
_Timeline index refreshed 2026-09-26 (AMČR baseline entry and header); 2026-09-24 (round 4) against `test` HEAD `3654e73` and again after the push (round 5) against `8003051`, using the `CONTRIBUTING.md` changelog, commit
subjects, the issue exports in `issues/`, GitHub Actions runs and tags, and the TEITOK/flexi* audit. Nothing removed from the issues themselves (per hub #29);
this file is a derived reading aid in `agent_dev_logs/`._

## 2026-10-26 — Triage (atrium-project): the README's SSHOMP record; the refresh workflow's comments
* **README** ("Where it fits in ATRIUM"): links the SSH Open Marketplace record `j9fqxo`, re-pointed to this
  repository on 10-24 (atrium-project#4); the hub's workflow page names it in its **Record** row too.
* **`vocab-refresh.yml`:** two comments cited the hub's `issue-log-refresh.yml`, deleted on 2026-09-06; they now
  stand on their own (comments only; the workflow lint passes with `--require-sha-pins`).
* **#2:** unchanged and already stated on the thread; the plan names the two cluster steps left before David's review.

## 2026-10-26 — v1.5.0-beta: the command line and the service read the same inputs (atrium-project#72)
* **One reader:** `kw_inputs.py` turns a record, CoNLL-U, TEITOK, a line CSV or a `.txt` into a `Document` (text,
  pages, KER lemmas, the controlled kind's rows). The service's `_doc_from_record`/`_doc_from_text` and
  `_record_stem` now call it (the old names stay as aliases); `keywords.py`'s CoNLL-U readers delegate to it.
  `kw_inputs.py` joins `.github/production-image.json`.
* **`keywords.py`:** reads every kind above from its folder; `--per-page` (+ `-p`, `PER_PAGE_OUT_DIR`) writes the
  pages' keywords; `--document-json-out-dir` (+ `--document-json-dir` for baselines) writes the `keywords` block
  through `llm_client_shared.write_document_record`; the worker extracts with `extract_from_texts`, so outputs for
  CoNLL-U and TEITOK are unchanged. The paradata program id is `keyword-extract` (was `nlp-enrich`).
* **`POST /extract_keywords`:** an optional `file` part (CoNLL-U, TEITOK, CSV, `.txt`; another kind 415);
  `document_json` optional, one of the two required; with both, the file's keywords go into the record.
* **Kept and documented** (`docs/usage.md` "The command line and the service"): KER without lemmas (CLI empty row,
  service 422), the lemma source per input, CoNLL-U without pages, per page off on the CLI and on in the service,
  the controlled kind through the batch clients, paradata file vs `CreateAction`.
* **Release:** v1.5.0-beta in `CITATION.cff`, `para_config.txt`, the spec and the runbook's image example; the
  `CITATION.cff` schema reference corrected to version 1.0 (2026-09-25) with the hub's authors (#13).
* **Checks:** 1056 passed, 5 skipped (torch, a live LLM); the new parity test 12/12; ruff 0.15.18 clean;
  `check_version.py`, `docs_check.py` and `image_closure.py` OK.

## 2026-10-27 — v1.5.1-beta: the release v1.5.0-beta did not get; KER and YAKE described as they are (atrium-project#72, #81, #6)
* **Why no release:** the v1.5.0-beta tag pushed its three images, but "Package the vocabulary (CC0)" refused the
  sidecars, still stamped `v1.4.0-beta` (`vocab_build.py --from-flat --skos` had not been re-run after the bump).
* **Fixed:** the sidecars rebuilt after the bump to v1.5.1-beta (only `tool_version` and `generated_utc` change;
  `--check` is clean). New `tests/test_vocab_release_stamp.py` applies the release's comparison on every push; it fails
  on `d2e76f2`. A local replay of the release step builds `atrium-vocabulary-v1.5.1-beta.zip` (12 files, 4,711 terms).
* **Docs review:** `docs/reference/licences.md` said the output's licence is computed; it now says what the agreed
  wording says (a calculated summary of the components, not the licence of the keywords; AMČR states the rights,
  atrium-project#6, 22 October). The legacy method is a lemma-frequency count named after ÚFAL's KER, which weights by
  tf-idf: README linked `ufal/ker` as "(MIT)" (that repository is LGPL-3.0 on GitHub, Apache-2.0 on LINDAT); it now
  cites KER's LINDAT record and says the code here is this repository's. `ker_data/` holds KER's two IDF tables, read
  by no shipped code and not in the images: recorded on the licences page. YAKE: the PyPI header says LGPLv3, the
  shipped `LICENSE` is AGPL-3.0; the declaration stays AGPL-3.0 and the page says why.
* **Release:** v1.5.1-beta in `CITATION.cff` (dated 2026-10-27), `para_config.txt` and the regenerated spec (version
  only).
* **Checks:** 1057 passed, 5 skipped (torch, a live LLM); ruff and format clean on the new test; compileall;
  `check_version.py`, `docs_check.py` and `image_closure.py` OK.

## 2026-10-28 — Documentation review: no decorative emoji, the image example (atrium-project#79)

* CONTRIBUTING's v1.5.1-beta row: "didn'ts get" → "did not get"; the footer ©.
* `service/README.md`: the image example names `1.5.1-beta`; the `HOST` warning takes the runbook template's
  `> **Note:**` form, without the emoji.
* `data_samples/vocab/RUNBOOK.md`: two emoji callouts become GitHub alerts, and a heading loses its emoji (nothing
  links to its anchor).
* No release (documentation only); it rides the next tag. `docs_check.py` and `runbook_check.py` OK.

## 2026-10-28 — v1.6.0-beta: the command line and the service, case by case (atrium-project#72, the pilot candidate)

* **Checked:** a differential run (research tooling in the session's scratchpad, not a repo test) of `keywords.py`
  against `POST /extract_keywords` on the same inputs: a record, CoNLL-U, TEITOK, a line table and a `.txt`; YAKE and
  KER for real, KeyBERT with a deterministic stub model; 5, 20 and 100 keywords; per page on and off. 90 cases, the
  same keywords, pages and record blocks; the only difference is KER without lemmas (an empty row against a 422), as
  documented. The licence components of the paradata now agree too (they did not for KeyBERT).
* **Fixed:** `BACKEND_COMPONENTS` in `keywords.py`, read by both entry points (the command line left out
  `keybert_model`); one document's failing record write no longer drops the rest of its batch or logs its written
  neighbours as skipped; the service's default method and `num_keywords` come from `kw_config.txt`, as the command
  line's (`DEFAULT_KW_METHOD` still overrides the method; the spec keeps `num_keywords=20`).
* **Docs:** the parity table of `docs/usage.md` gains a document with no text, the language, the KeyBERT settings and
  the limits; KER's lemma sources are stated where its needs are (no ATRIUM tool writes `lines[].lemma`); the flag
  table's `-i`, `-o`, `-d` defaults, `--paradata-dir` and `--batch_size`; the service README's endpoint, `method`,
  `num_keywords`, limits and intro rows; the `legacy` and `per_page` descriptions (the spec is regenerated).
* **Release:** `v1.6.0-beta` in `CITATION.cff`, `para_config.txt`, the spec and the vocabulary sidecars
  (`vocab_build.py --from-flat --skos`).

## 2026-10-28 — v1.6.0-beta, before the tag: paradata reads `para_config.txt` beside the code

* Found by the translator's harness: `ParadataLogger` looks for `para_config.txt` in the working directory unless it
  is told where. `keywords.py`, `llm_run.py`, `ollama_client.py`, `openrouter_client.py` and the service now pass
  the repository root; a CLI run started outside the checkout recorded `tool_version` "unknown" and every component
  licence as UNKNOWN. The images run from `/app` and were not affected.
* **Checks:** 1059 passed, 5 skipped; ruff clean.

## 2026-10-29 (evening) — v1.6.1-beta: a record that cannot be added to is refused (atrium-project#72)

* **Shared modules** (re-vendored from the hub with `scripts/revendor_shared.sh`): `atrium_document.py` raises
  `InvalidRecordError` when a list block the merge adds rows to is not a list of objects, before anything is written,
  and `service/atrium_service.py` answers it with 422 `invalid_record`. Here that is `entities`, where the controlled
  kind adds its `pid`s. The spec's registry text names the case, and the `invalid_record` row of `service/README.md`
  names `entities`.
* **README:** the quick start runs the image with `DEFAULT_KW_METHOD=yake`, so the service loads no KeyBERT model at
  start and "needs no model" holds (`service/api.py`'s warm-up loads KeyBERT when it is the default). The YAKE line
  says what `docs/reference/licences.md` says: a run that uses YAKE lists it, and the calculated licence summary
  becomes AGPL-3.0 (atrium-project#6).
* **Vocabulary sidecars** restamped `v1.6.1-beta` (`python vocab_build.py --from-flat --skos`; only `tool_version` and
  `generated_utc` change), so `tests/test_vocab_release_stamp.py` and the release's packaging step pass.
* **CI:** the hub's workflows are pinned to the commit that carries the modules (the maintainer's pin move; the Trivy
  database retry of `b07090f` is already in).
* **Release:** v1.6.1-beta in `CITATION.cff`, `para_config.txt`, the spec's version; CONTRIBUTING row; the service
  README's version example.
* **Checks:** 1058 passed, 5 skipped; pre-commit clean.

## 2026-11-02 — The calculated licence out of the docs (atrium-project#6)

* README's YAKE limit, `docs/reference/licences.md` and the runbook's `paradataRecord` line list components; the
  "calculated licence summary" is named once, as an older field, with the hub's link (motyc, 10-29).
* **Checks:** 1021 passed, 7 skipped, as before.

## 2026-11-02 — atrium-project#79 phase F, tool round: the docs for each kind of reader

Documentation only; no code, test or configuration change.
* **F3:** `docs/development.md` § Working records is the one Markdown pointer into `agent_dev_logs/`; other pages cite
  the issue. CONTRIBUTING's documentation table follows the hub template.
* **F4:** the opening is 76 words; the "assembled on 1 October 2026" paragraph moved to the new `docs/development.md`; the prompt-size limit gives both estimates (about 40,000 tokens at 4 characters a token, about 58,000 at 3.35).
* **F5:** the runbook follows the template's order, with "At a glance" under Start and "Shutdown behaviour"; tracker
  shorthand and version history are out of its running text. Errors moved before Limits.
* **F6/F7:** task headings on `docs/usage.md`; sentence passes on `reference/licences.md` and `how-it-works.md`. The vocabulary decision packages are unchanged.
* **Map:** the hub's `agent_dev_logs/plans/79.F-relocation_map.md` § atrium-keyword-extract (every moved block, corrected facts,
  renamed anchors).
* **Checks:** `docs_check` and `runbook_check` pass; 1021 passed, 7 skipped, as at the head.

## 2026-11-03 — What the green CI runs on the 11-02 `test` head hid (atrium-project, CI audit)

* **uvicorn gets the configured log level:** `uvicorn.run(…, log_level=…)` in `service/api.py`. Under `LOG_LEVEL=WARNING` uvicorn still logged its start-up lines and the access log, and the hub's probe, which read only the service's own format, reported none.
* **`llm_run` tests run:** `tests/test_llm_run.py` and `tests/test_cli_orchestration.py` no longer skip without pysqlite3, which `llm_run.py` treats as optional. Every lane had skipped them. `lm-format-enforcer` (45 KB) joins `requirements-test.txt`, so the enum-index test runs too.
* **`pydantic==2.13.5`** in `requirements.txt`, as the tests and `requirements_llm.txt` pin it (the image shipped 2.14.2).
* `httpx2` beside `httpx` (Starlette prefers it); pre-commit `ruff-check`; the weekly scan targets `-api`.
* **Checks:** 1021 passed, 7 skipped without torch, as before; with torch and transformers 5.x, the LLM tests 68 passed; no INFO line under `LOG_LEVEL=WARNING`.

## 2026-11-03 — v1.6.2-beta

* **Version:** v1.6.1-beta → v1.6.2-beta in `para_config.txt`, `CITATION.cff`, `service/openapi.json`, `service/README.md`'s example, and the three vocabulary sidecars (`python vocab_build.py --from-flat --skos`: only `tool_version` and `generated_utc` change). `CITATION.cff` `date-released` 2026-11-03.
* **CONTRIBUTING.md:** the release row. It covers the 11-02 licence wording (atrium-project#6), the documentation
  round (#79) and the 11-03 CI fixes, with the hub's workflows pinned to `6a10787` (the pin sweep, committed
  before this one).

## 2026-11-03 (evening) — The torch download retries; the hub pin moves again

* **`Dockerfile`:** the `llm` stage's pip install, which fetches torch from download.pytorch.org gets up to three attempts, 20 s
  apart. The base stage's `ENV` sets `PIP_DEFAULT_TIMEOUT=60`, so a stall may last 60 s instead of pip's 15.
  On 11-03 keyword-extract's `llm` build failed on "Read timed out" at 25.7 of 196.2 MB of the CPU torch wheel.
  `PIP_RESUME_RETRIES` would not help here: the `python:3.11` images ship a pip that predates it.
* **Hub pin:** the callers move to the hub commit that turns the build cache off on tags (a tag run cannot read
  the `test` caches) and lists each CRITICAL and HIGH finding in the scan summary.

## 2026-11-04 — v1.6.3-beta prepared: no licence asserted on a crate (atrium-project#6)

* **Shared modules (atrium-project#6, step 1 of the rights proposal; re-vendored from the hub, byte-identical):**
  * `atrium_rocrate.py`: a document or run crate's root `license` names `#no-licence-asserted`, a contextual
    entity that asserts nothing (the rights depend on the source and on AMČR's permission). The calculated
    licence is no longer exported as the crate's. A fragment carries no licence entity; `--wrap` gives its stub
    root `#no-licence-asserted`.
  * `atrium_document.py` and the schema: a record marks its calculated `provenance.license` with
    `provenance.license_basis: "calculated"` (declared, optional, `calculated` only; registered in
    `tests/test_schema_freeze.py`). `service/openapi.json` carries the new record schema.
  * `para_licenses.py`: the notes list the components and say that no output licence is asserted; the
    "Effective output license is X, the most restrictive among N" sentence is gone.
  * Tests: `tests/test_atrium_rocrate.py`, `tests/test_document_originators.py`, `tests/test_schema_freeze.py`.
* **Vocabulary sidecars:** `python vocab_build.py --from-flat --skos` re-stamped the three `*_nested.meta.json` (only `tool_version` and `generated_utc` change).
* **Version v1.6.3-beta** (prepared, not tagged): `para_config.txt`, `CITATION.cff` (`date-released` 2026-11-04), `service/openapi.json`, the version examples in `service/README.md`; the `CONTRIBUTING.md` row.
* **Yours:** push the hub first and move `v1` to it; then, in this repository, run
  `python3 scripts/pin_hub_reusables.py --sha <that commit>` from the hub so the pins and these copies land in one
  commit (para-drift compares them with the hub at the pin); then tag.
* **Checks:** the suite on Python 3.11 with `requirements-test.txt` (the release lane, no torch): 1030 passed, 7 skipped; `tests/test_openapi_contract.py` 12 of 12 against the app; `check_version.py --tag` agrees; the shared selftests pass; ruff clean.

## 2026-11-04 (after the push) — v1.6.3-beta: the tag fixed

* The first tag was `v1.6.3.-beta` (a stray dot) at `a137011`; no run was created for it, and the version gate would
  have refused it. `v1.6.3-beta` was pushed at 10:18Z; its Release run is 41813324882.
* **Left:** an admin deletes `v1.6.3.-beta` (the `v*` ruleset refuses everyone else; GitHub logs the bypass).
* Every push run on `a137011` (`master`) is green, para-drift included; the `test` push created no runs.

## 2026-11-04 (later) — v1.6.4-beta prepared: v1.6.3-beta released under the next number

* **Why:** v1.6.3-beta was tagged but not released: its CVE gate on the `llm` image stopped on `stream error: stream ID 5; PROTOCOL_ERROR` while Trivy pulled a layer, with no finding (run 41813324882; the first tag, `v1.6.3.-beta`, was mistyped and created no run). The maintainer's decision: release the same code as v1.6.4-beta
  rather than repair the v1.6.3-beta tag (the `v*` ruleset lets only an admin move or delete it).
* **Version v1.6.4-beta** (prepared, not tagged): `para_config.txt`, `CITATION.cff`, `service/openapi.json` (version only), `service/README.md`, the three vocabulary sidecars (`vocab_build.py --from-flat --skos`); the `CONTRIBUTING.md` row. No code changes against v1.6.3-beta.
* **Hub:** the CVE gate now runs once more after a 30 s pause, and the report-only scan's retry waits 30 s
  (atrium-project#81). Both reach this repository with the pin sweep committed with this version.
* **Yours:** push the hub and move `v1`; here, `python3 scripts/pin_hub_reusables.py --sha <v1>` from the hub, committed
  with these files; push `test`; then push the tag `v1.6.4-beta` on its own.

## 2026-11-04 (afternoon) — The pilot release out; records and comments aligned

* **Released:** v1.6.4-beta (11:20Z, release run 41817846546), the pilot release (atrium-project#77). v1.6.3-beta and the mistyped `v1.6.3.-beta` stay tags without a release; the `.3` CONTRIBUTING row now says so.
* **#6 wording:** the licence rationale in `para_config.txt` calls the most-restrictive value the run's calculated licence label, not the output's licence (the file still parses; version v1.6.4-beta).
* **Records:** the header names the pilot release.

## 2026-11-05 — #2: decision models over the vocabulary, a plan (page-classification#58)

* **New:** `plans/decision_models.plan.md`. This repository's part of the decision-model plan anchored on
  page-classification#58.
* **The method:** Clef, Clef-Flash and Strands Decider 2B (`POST /v1/systemone`) answer `choice`/`noul` questions
  with a probability per option, and generate no text. The descent goes meta-text, then facet, then group, then term,
  with `none_of_these` at every step.
* **Why:** D2 holds by construction (a listed term or unresolved). There is no prefix trap. The whole vocabulary is
  reachable at any window: the 58,260-token prompt reaches only ~1,100 of the 4,711 terms at 16k.
* **Measured** from `union_nested.json` and `specificity_pairs.csv`: 10 facets, 1–25 groups each. Below the groups,
  the terms' own tree has 797 inner nodes that are terms, and up to 11 levels. Only `historické oblasti a státní
  útvary` (~260 children) exceeds a `choice`'s 255 options; it is chunked.
* **Clef's backbone is Qwen3.8-27B,** the default model's.
* **Runs without gold:** on the 19 documents, scored by `score_categories.py` beside R3. With gold, the method joins
  the D2 comparison.
* **No change** to the service, the prompt or the defaults.
* **#2's plan and digest:** "Option 4" added.
* **Prepared:** a #2 comment, delivered in chat.
* Not pushed: files delivered in chat.

## 2026-11-06 — v1.6.5-beta prepared: the batch image starts Galaxy's job script (atrium-project#66)

* **Why:** Galaxy starts a tool's container as `docker run … IMAGE /bin/sh tool_script.sh` in the job's working
  directory. The old relative ENTRYPOINT passed `/bin/sh` to the program as an argument (exit 2) and failed outside `/app`.
* **Change:** the hub-canonical `container_entrypoint.py` and its shared test, vendored by `revendor_shared.sh`; the
  ENTRYPOINT names the program by its absolute path: `base` → `/app/keywords.py`, `llm` → `/app/llm_run.py` (CMD `llm_config.txt` kept). Arguments still go to the program; a first argument
  naming `sh`, `bash`, `dash`, `python` or `python3` runs as given. A Galaxy wrapper would offer the statistical kind only.
  `tests/test_batch_entrypoint.py` pins the stages; `ruff.toml` excludes the two vendored files from formatting.
* **Version v1.6.5-beta** (prepared, not tagged): `CITATION.cff`, `para_config.txt`, `service/openapi.json`, the version
  examples in the docs; the vocabulary sidecars restamped (`python vocab_build.py --from-flat --skos`, which
  `tests/test_vocab_release_stamp.py` requires); the `CONTRIBUTING.md` row; a paragraph on the entry point in `docs/usage.md`.
* **Yours:** push the hub commit with `container_entrypoint.py` and move `v1`; here, `python3 ../atrium-project/scripts/pin_hub_reusables.py --sha <v1>` committed with these files (para-drift checks the copy only at a pin that has it); push `test`; then `python3 ../atrium-project/scripts/tag_release.py v1.6.5-beta`, which tags the pushed HEAD only and pushes that one tag.

## 2026-11-06 (evening) — #3: the descent tree over the vocabulary, built (atrium-project#83)

* **Read:** the push of 16:51 (`24f9e6b`: `3.plan.md`, `3.digest.md`); #3, opened 16:40 under atrium-project#83.
* **Written (not pushed):** `dm_run.py --dump-tree OUT`, with `tests/test_dm_tree.py` (10).
  * **The tree** comes from `vocabulary_terms()`, `specificity_pairs.csv` (TEATER parents) and `amcr_flat.json`
    `broader` (AMČR parents), with the guardrail's `covers` and the prompt blocks' wording.
  * **Its shape:** 4,711 terms, 122 groups, 750 inner term nodes, parent chains ≤ 11, one chunked node, 885 choices of
    ≤ 251 options; digest `3ef6fced…`.
  * **11-05's 797 inner nodes do not reproduce.** The plan says why.
  * Line mode waits for the vendored client.
* **Checked:**
  * the new tests with `test_env_contract.py`: 22 passed;
  * ruff;
  * the hub's image closure, unchanged.
* **Records:** the #3 export; `plans/3.plan.md` and `digests/3.digest.md`; `plans/2.plan.md` and `digests/2.digest.md`
  point at `3.plan.md` and #3.
* **Yours:** push; the fixed #3 body and the comment for @david-spacil, delivered in chat.
* Not pushed: files delivered as per-repo zips.

## 2026-11-08 — #3: the document type, from the list shared with digital-convert (atrium-project#83)

* **Asked (K4TEL, in session):** like digital-convert, determine the document's type from the archive system's list,
  under question for AMČR. The answer: prepare the shared list now.
* **Written (not pushed):**
  * **The client:** `decision_client.py`, vendored from page-classification (`39a7bea`, `v1.13.0-beta`).
  * **The list:** `decisions/document_type.v1.json`, vendored from digital-convert (its v1 of the same day).
    * Both are pinned in `tests/test_vendored_decision_parity.py`.
    * The list's `ADOPTED` commit and release are `None` until digital-convert's commit exists.
  * **Settings:** `ruff.toml` (B905 for the copy, no formatting), `DECISION_*` under `NOT_PUBLISHED`,
    `decision_model` in `para_config.txt`.
  * **`dm_run.py --doc-type`:** one request per document from its `Clear`/`Noisy` lines up to `--max-chars`. It writes
    `DM_DOC_TYPE.csv` and a summary; `--gold` scores it.
  * **Tests:** `tests/test_dm_doc_type.py` (9).
* **Checked:**
  * the full suite: 1,073 passed, 8 skipped;
  * ruff;
  * `--doc-type` on `data_samples/DOC_LINE_CATEG/` against the fake server.
* **Records:** `plans/3.plan.md` (Phase A′), `digests/3.digest.md`.
* **Yours:**
  * unpack and push;
  * once digital-convert's commit with the list exists, fill the list's `ADOPTED` commit;
  * the comment for #3, delivered in chat.
* Not pushed: files delivered as per-repo archives.

## 2026-11-08 (round 2) — #3: the text-only view of the type list; the drift fix (atrium-project#83)

* **Asked (K4TEL):** keyword-extract works with text and no image; fix the failing GHA runs.
* **CI on `810e7b7`:**
  * **Paradata Drift:** `tests/test_vendored_decision_parity.py` nested `ADOPTED` per file, and the hub's
    `tools/ci/vendored_pins.py` reads one flat `ADOPTED` per pin file.
  * **API Meta-Contract:** GitHub's 504 on release downloads, reproduced; re-run it.
* **Written (not pushed):**
  * **The pins, split:**
    * `tests/test_vendored_decision_parity.py`: the client, page-classification `39a7bea`, `v1.13.0-beta`;
    * `tests/test_vendored_doctype_parity.py`: the list, digital-convert `2bb3f3c`, `v1.4.6-beta` (prepared there).
    * `.github/workflows/para-drift.yml`: `vendored-from: atrium-nlp-enrich atrium-page-classification
      atrium-digital-convert`.
  * **`dm_run.py --doc-type`:**
    * the text-only view: `document_type` over the 6 written types and `unspecified`, no `group`; derived from v1, or
      read from v2's `document_text`, with the same digest `34d45440…`;
    * `gold_offered`; `gold_not_offered`; accuracy over the offered types.
  * **Tests:** `tests/test_dm_doc_type.py` (11).
* **Checked:**
  * the full suite;
  * ruff;
  * the drift job's steps, locally: `vendored_pins.py list` with the three owners, then each pin test with its owner
    checked out at the adopted commit beside it. 15 passed, no skips.
  * `--doc-type` on the 3 synthetic documents against the fake server: 7 options, no `group`, no image.
* **Records:** `plans/3.plan.md` (Phase A′), `digests/3.digest.md`.
* **Yours:** push after digital-convert. Once digital-convert's v2 commit is on GitHub, re-vendor v2 and move the
  list pin.
* Not pushed: files delivered as per-repo archives.

## 2026-11-08 (round 3) — #3: digital-convert's list v2 adopted; review fixes (atrium-project#83)

* **Asked (K4TEL):** the review's fixes to `dm_run.py`; adopt digital-convert's document-type list v2.
* **Found:** the list pin named digital-convert `2bb3f3c` and called v1 "first released in v1.4.6-beta". That
  tag's commit, `427b690`, has only v2, and no release carried v1; the sibling byte check always skipped, as
  digital-convert's checkout has no v1. v1.4.6-beta itself was tagged, not released (GitHub's 504).
* **Written (not pushed):**
  * **The list:** `decisions/document_type.v2.json`, byte for byte from digital-convert `427b690`; v1 removed
    (`git rm`). `dm_run.DOC_TYPE_LIST`, the module docstring and the `--doc-type` help name v2.
  * **The pin:** `ADOPTED` digital-convert `427b690`, release `v1.4.7-beta`; `VENDORED` v2 (`8c1a2715…`). The
    hub's `vendored_pins.py list` reads it.
  * **The text view is unchanged:** its questions, item, offered types and digest (`34d45440…`) are the same from
    v1 and from v2.
  * **`dm_run.py --doc-type`:** `parser.error` for a threshold outside 0 to 1 or a `--review-below` above
    `--accept-at`, before any request. Docstrings for `tree_stats`, `doc_type_columns` and `main_doc_type`.
  * **Tests:** `tests/test_dm_doc_type.py` (+6; the v1 test now reads v2's own view): the refusals (exit 2),
    thresholds in range, `--max-chars`.
  * **Docs:** `docs/usage.md`, "Decision models, offline" (`--dump-tree`, `--doc-type`, the lanes, the outputs);
    a pointer in `README.md`; the file map in `docs/development.md`; `prompts/RUNBOOK.md`'s skipped heading level.
  * **`.github/workflows/para-drift.yml`:** the comment said the owners' `test` head; it is the owner at the
    adopted commit. It names v2. Comment only.
* **Checked:**
  * the suite without `slow`: 1,187 passed, 1 skipped (the live LLM test);
  * the pin tests with digital-convert at `427b690` beside this repository, no skips;
  * ruff; the hub's `docs_check.py`.
* **Yours:** push with the hub re-pin. No wait for digital-convert's release: para-drift compares the copy with
  the owner at `427b690`, which is already on GitHub. `plans/3.plan.md` and `digests/3.digest.md` still cite v1
  and `2bb3f3c` (history, left as written).
* Committed locally, not pushed.

## 2026-11-09 — #2: David Spáčil's review adopted (PR #4); the four pinned tests moved

* **Asked (K4TEL):** adapt the repository to @david-spacil's PR #4 (the 13 ambiguous composite halves, the 10-16
  duplicate spellings) and make its four failing tests pass.
* **Adopted:** PR #4's five commits, fast-forwarded onto `test`'s head `5817ec0` (author kept):
  * `composite_halves.csv`: all 13 `ambiguous` halves ruled; `plastika`, `souvrství` and `pozdní eneolit`
    accepted for one composite each, `výplň`, `vrstva` and `boží muka` accepted; five auto-accepted halves ruled
    fragments. The loader offers 80 halves (79 before).
  * `taxonomy_overrides.json`: 35 `same_as` pairs, declared from one side (29 Chronology periods,
    `kříž/boží muka` ≡ `boží muka a křížky`, five more). Scoring-time only; both labels and ids stay offered.
  * the rebuilt vocabulary and review sheets: `same_as` links 102 → 137 (237 terms carry one).
* **Written (not pushed):**
  * `tests/test_vocab_manager.py`: the `same_as` snapshot pins 237/137, the third stated move.
  * `tests/test_vocab_review.py`: the sheet's `manual` rows must be exactly the declared pairs; the fabricated
    `kostel`/`kaple` row is found by its ids, not as the only `manual` row; a shared half is accepted for one
    composite at most, with the review's three picks pinned (test renamed to say so).
  * `data_samples/vocab/RUNBOOK.md`: the one-composite rule for shared halves, and the review.
  * `digests/2.digest.md`, `plans/2.plan.md`; `issues/` export with David's 11-09 comment.
* **Checked:** before the test edits, exactly PR #4's four failures (377 passed); after, the six vocabulary test
  files (381 passed) and the suite without `slow` (1,187 passed, 1 skipped: the live LLM test); `atrium_vocab.py --selftest`,
  `vocab_build.py --from-flat --skos --check`, `prompt_template.py --check`; ruff 0.15.18.
* **Yours:** merge PR #4, then push these files on top.
* Committed locally, not pushed.

## 2026-11-09 (afternoon) — #2: the gold set's format and annotator, requested

* **Asked (K4TEL):** carry the annotated-dataset request of
  [nlp-enrich#7](https://github.com/ufal/atrium-nlp-enrich/issues/7#issuecomment-6741768360) (11-09 13:54) into the
  comment for @david-spacil and into #2's digest and plan.
* **The request:**
  * annotation by a Czech-speaking archaeologist;
  * the same sample documents (the 1,029 lines the runs answer in the 19 documents of `gold_workbook.csv`), or an
    equal-sized set;
  * per line: `line_text`, `is_vocab_term_present`, and `term_extracted_1` to `_3` (the first is empty only when the
    flag is `False`).
* **Written (not pushed):**
  * `digests/2.digest.md`: the 11-09 section and the status;
  * `plans/2.plan.md`: step 5 rewritten; step 6's scorer counts a pick that matches any gold term; the status and the
    table row. The ~500-line fallback is gone: the request asks for an equal-sized set.
  * The comment for David on #2: thanks for the review, plus the request. Drafted, not posted.
* **Left (a):** `gold_workbook.csv` (`corpus_review.gold_workbook_rows`) and `score_categories.gold_labels` move to
  the new columns before the sheet goes to the annotator. No code changed in this entry.

## 2026-11-09 — #3: content only; the document type removed, form terms withheld from the tree (atrium-project#83)

* **Asked (K4TEL):** terms about a document's form and terms about its content are two groups, never mixed.
  digital-convert gets images and no text; this repository gets text and no image, so it decides content only. The
  schemes are to suit a historical documentary archive.
* **Decided in session:** the form-like TEATER terms are withheld from the decision model's tree, not from the
  vocabulary; the written genres move to digital-convert, asked from a document's first page images.
* **Written (not pushed):**
  * **`dm_run.py`:** `--doc-type` and everything under it removed (the list's loader, the run, the table, the
    summary, the server options); `FORM_TERMS` (14 TEATER ids) and their subtrees withheld in `build_tree()` after
    the parents are found, recorded as `withheld_form`; the parent-edge counts now cover the offered terms only;
    the docstring.
  * **Deleted:** `decisions/document_type.v2.json`, `tests/test_dm_doc_type.py`,
    `tests/test_vendored_doctype_parity.py`.
  * **`.github/workflows/para-drift.yml`:** digital-convert out of `vendored-from`, and the comment.
  * **Tests:** `tests/test_dm_tree.py` (the term count net of the withheld ones; a new test of the list against
    `teater_flat.json` and the tree); `tests/env_contract_data.py` and `tests/test_vendored_decision_parity.py`
    (their text).
  * **Docs:** `docs/usage.md` ("Decision models, offline": content, never form; the withheld terms),
    `docs/development.md`, `README.md`.
* **Measured:** 22 terms withheld (Methods: `dokumentace` with its 8 kinds, `nálezová správa`, three
  remote-sensing products; Related Disciplines & Society: `fotografie`, `kresba`, 7 kinds of map). The tree: 4,689
  terms, 120 groups, 746 inner term nodes, 879 choices, digest `a306f653…`; before, 4,711 terms and `4167a9a2…`.
  Compared node by node with the head's tree: only the 22 terms, their 2 groups and their parents' child lists
  differ.
* **Kept as content:** `písmo`, `písemnost`, `muzejní dokumentace`, `grafická technika`, `mentální mapa`, the aerial
  methods; for review with the annotators.
* **Checked:** the full suite, 1,062 passed, 7 skipped; ruff check and format.
* **Records:** `plans/3.plan.md`, `digests/3.digest.md`.
* Committed locally, not pushed; files delivered as per-repo archives.

## 2026-11-10 — The TEITOK projection names each page's keyword lists (ufal/flexiconv#1)

* **Asked (K4TEL):** align the tools with the flexiconv maintainer's 11-09 answer on ufal/flexiconv#1.
* **Changed in nlp-enrich, not here:** its projection writes this repository's keywords per page too, and each
  page's `<pb>` points to its lists (`teater`, `kwcs`, `kwen`, `kwstat`). The record's `keywords` and
  `enrichment` blocks are read as before.
* **Docs:** `docs/how-it-works.md` says the projection carries the statistical and the controlled keywords.
* **No code change.** The vendored `teitok_read.py` and `bbox_scale.py` are unchanged, so `ADOPTED` stays.
* **Header:** the hub pin is `4435ffb`, as the workflows have it.
* Files delivered as per-repo archives.

## 2026-11-11 — The output contract: this repository's part of doc-schema-v2 (atrium-project, issue to be opened)

* **Asked (K4TEL):** carry the meeting of 11 November (ARÚP's output contract) into this repository's logs: its
  slice of the consolidated record and paradata change, and the statements the meeting supersedes in #2 and #3.
  Anchor: [meeting digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/project_state_1111.md) ·
  [hub plan](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/plans/84.plan.md).
* **Decided in session:** plans only this round; the schema issue is not opened yet (placeholder name
  `doc-schema-v2`); `categ` is ocr-postprocess's only, and digital-convert's verdicts become `decode` markers.
* **Found:**
  * the record path also re-bands lines from `quality_score` (`llm_client_shared.py:216-222`: below 0.40 `Trash`,
    below 0.70 `Noisy`), a second banding rule beside ocr-postprocess's;
  * three limits fail a job under D13: replies cut at `LLM_MAX_NEW_TOKENS` (`skipped`), the consecutive-error stop
    (`stopped`), KeyBERT chunks beyond the encoder's window (`trimmed`); the vocabulary fit (`trimmed`,
    `service/api.py:524-531`) is Q6;
  * the paradata's result names two files nobody stores (`<doc_id>.keywords.json`, `<doc_id>.enrichment.json`,
    `service/api.py:829-842`); the hub's `docs/rocrate_export.md` calls them `results.json`;
  * the controlled kind's LLM has no row in `para_config.txt`;
  * scheduled workflows: `controlled-live.yml` (weekly, and on `test` pushes), `vocab-refresh.yml` (monthly),
    `scheduled-smoke.yml` (weekly), and `codeql.yml`, `security.yml` (security, kept); `gpu-inference.yml`'s
    schedule is commented out.
* **Written here (not pushed):**
  * **`plans/doc-schema-v2.plan.md`** (new): this repository's slice: its fields, seven tasks with code locations,
    its paradata, what it depends on (hub tasks, Q1, Q6), the superseded statements, including closed #1's (listed,
    not edited);
  * **`digests/2.digest.md`, `plans/2.plan.md`:** the 11-11 status and section; superseded marks on the weekly live
    lane (atrium-project#81), the vocabulary fit (Q6) and the vocabulary's hashes in the paradata;
  * **`digests/3.digest.md`, `plans/3.plan.md`:** parked during the pilot phase (atrium-project#83); the existing
    content kept as the record; "possible now" and the tree's SHA-256 in the paradata marked;
  * **`DEVLOG.md`:** the header names the starting set of the pilot phase.
* **Not posted:** nothing on GitHub; Q6 is on the hub plan's question list for the next meeting.
* Plans only; no code changed. Files delivered as full files.

## 2026-11-12 — atrium-project#84; atrium-project#16: the real-text samples are not approved

* **Asked (K4TEL):** align the logs with ARÚP's output contract of 12 November (the .docx of that day, replacing the
  meeting document of 10 November) and with David Novák's comments of 11-12 (atrium-project#84 opened, #13, #16,
  #78); `test` fetched first (all seven working branches = `test`).
  Anchor: [contract digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/project_state_1211.md) · [hub plan of #84](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/plans/84.plan.md).
* **Decided in session:** the tool slices are named `plans/84.plan.md`; the translator keeps `amcr-fields.txt` as a
  documented example that nothing loads (no default list, D34); the hub's #84 plan carries a reply draft agreeing on
  points 1 and 2.
* **Found:** `data_samples/KW_PER_DOC_LLM_*` (22 directories) hold 16 real documents each (`R3_qwen3_14b` 6) besides
  the synthetic `CTX000000001–3`; `vocab/gold_workbook.csv` and `corpus_term_evidence.csv` quote real lines,
  `corpus_branch_evidence.csv` only terms. The tool reads none of the record fields that leave in v2.
* **Written here (not pushed):**
  * **`plans/84.plan.md`** (was `plans/doc-schema-v2.plan.md`): the 11-12 section (no per-block `run_uuid`; `result`
    with blocks and fields; `categ` five values; D35 on `entities[].pid`);
  * **`plans/2.plan.md`, `digests/2.digest.md`:** 11-12 sections: #16 answered, item 4(c)'s "If not" branch (keys-only
    sheets, synthetic outputs, the text on the cluster);
  * **`DEVLOG.md`:** the header and this entry.
* **Not posted:** nothing on GitHub; questions stay on the hub's list for the next meeting.
* Plans only; no code changed. Files delivered as full files.
