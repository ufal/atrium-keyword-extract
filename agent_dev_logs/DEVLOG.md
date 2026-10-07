# 📓 atrium-nlp-enrich — agent_dev_logs/DEVLOG.md (timeline index)
> _NLP enrichment of OCR text lines. 5 open issues (#6, #7, #10, #18, #38); #8/#9/#11/#19/#28/#35 closed. AMČR baseline (atrium-project#67, 2026-09-26): #10, #38 close · #6, #7, #18 defer; the flexiconv route stays off the AMČR production chain. `test` = `40c48f0` (2026-09-26: the `doc-schema-v1` freeze files) · **v0.22.0** (2026-09-25). TEITOK/flexi* work (#10/#38, formerly #9/#28) is coordinated in [`plans/teitok_conformance_plan.md`](plans/teitok_conformance_plan.md)._
> _Per-issue detail: `digests/{id}.digest.md` · `plans/{id}.plan.md` · `issues/` exports (source of truth). #6's saga (April→September) is condensed below; `digests/6.digest.md` is the authoritative 13-phase record. Cross-repo/hub history lives in `ufal/atrium-project/agent_dev_logs/DEVLOG.md` (deduplicated out of this file)._

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

  Files delivered in chat as a zip; not pushed.

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

  Files delivered in chat; not pushed.

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

  Files delivered in chat; not pushed.

---
_Timeline index refreshed 2026-09-26 (AMČR baseline entry and header); 2026-09-24 (round 4) against `test` HEAD `3654e73` and again after the push (round 5) against `8003051`, using the `CONTRIBUTING.md` changelog, commit
subjects, the issue exports in `issues/`, GitHub Actions runs and tags, and the TEITOK/flexi* audit. Nothing removed from the issues themselves (per hub #29);
this file is a derived reading aid in `agent_dev_logs/`._
