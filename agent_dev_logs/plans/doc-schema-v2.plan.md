# Strategy — doc-schema-v2 (atrium-project, issue to be opened): atrium-keyword-extract's part

> _Written **2026-11-11** after the meeting of that day (ARÚP's output contract; K4TEL's points in session). The
> change as a whole is the hub's: [plan](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/plans/doc-schema-v2.plan.md)
> · [digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/doc-schema-v2.digest.md) (today's
> fields and writers) · [meeting digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/project_state_1111.md).
> This file is this repository's slice only. The issue is not opened; rename this file to the issue number once it
> is. Code read at the checkout of 11-11._

**Status (2026-11-11)**: 📋 **Planned, not started. keyword-extract reads the record and writes three blocks; in v2
it stops writing run data into the record, reads lines by `categ` only, fails a job on a limit that skips, trims or
stops, and names what it reads and writes by distribution and SHA-512. Code follows the hub's shared modules.**

## Its fields

| Record node                                 | In v2         | Note                                                                                                                                                                                                                          |
|---------------------------------------------|---------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `enrichment` (`items`, `summary`, `topics`) | written       | the controlled kind                                                                                                                                                                                                           |
| `keywords` (`document`, `pages`)            | written       | the statistical kind (atrium-project#73)                                                                                                                                                                                      |
| `entities[].pid`                            | written       | one field in nlp-enrich's block (`llm_client_shared.py:1436-1444`)                                                                                                                                                            |
| `lines[]`                                   | read          | filtered by `categ` only: `Trash` and `Empty` skipped, `Non-text` by config; `Garbage` and `Inverted` leave the vocabulary of `categ` (D17, D18) and become digital-convert's `decode` markers, which this tool does not read |
| `derived_from.enriched`                     | stops (D1)    | `llm_client_shared.py:1450-1452`                                                                                                                                                                                              |
| `regenerable.markdown`                      | stops (D1)    | `llm_client_shared.py:1454-1462` (the recipe id at `:1233`)                                                                                                                                                                   |
| `provenance` licence detail                 | stops (D2)    | passed from `service/api.py:800` through `llm_client_shared.py:1464-1465`                                                                                                                                                     |
| `forms`                                     | removed (D19) | granted to this tool, never written                                                                                                                                                                                           |

## Tasks (next rounds)

1. **No run data in the record** (D1, D2): drop `derived_from.enriched`, `regenerable.markdown` and the licence
   detail at the locations above. Contributors and stamps go with the hub's `_provenance()`/`_stamp()` (hub task 1).
2. **One `run_uuid` per block** for `enrichment` and `keywords`, in the shape Q1 settles; `entities[].pid` sits in
   nlp-enrich's block, so Q1 also settles which run it names.
3. **Lines by `categ` only:** `_ALWAYS_SKIP_CATEG` (`llm_client_shared.py:186-191`) follows the hub's
   `UNTRUSTWORTHY_LINE_CATEGORIES` (hub task 5), and its comment stops naming digital-convert. The re-banding from
   `quality_score` in `should_process_line()` (`llm_client_shared.py:216-222`: below 0.40 `Trash`, below 0.70
   `Noisy`) is a second banding rule beside ocr-postprocess's; it leaves the record path.
4. **Paradata in the stored form** (§5.5): the `file_entity` calls (`service/api.py:829-842`, `:1130-1142`,
   `:1177`) take SHA-512 and the distribution names that come with the job (hub task 3). The result names record
   blocks only; `<doc_id>.keywords.json` and `<doc_id>.enrichment.json` (`:829-842`; the hub's
   `docs/rocrate_export.md` calls them `results.json`) are not stored outputs and leave it.
5. **A limit that skips, trims or stops fails the job** (D13), with no partial `enrichment` or `keywords`: replies
   cut at `LLM_MAX_NEW_TOKENS` (`service/api.py:737-742`, `skipped`); the consecutive-error stop (`:745-750`,
   `stopped`); KeyBERT chunks longer than the encoder's window (`keywords.py:864-873`, `trimmed`). KeyBERT's
   chunking (`keywords.py:855-862`, `split`) stays a recorded limit. The vocabulary fit waits on Q6 (below).
6. **Components as facts** (D2): `para_config.txt` keeps its rows with their terms; no effective licence (hub
   task 2). The controlled kind's LLM has no row today; it is listed with its terms like the others.
7. **Tests** that pin the dropped nodes and the licence block (`tests/test_document_record.py`,
   `tests/test_service_document_json.py` and others) move with the code; the shared ones come re-vendored.

## Paradata

One action per call in `paradata/atrium/document-json`, as the meeting digest gives it:

- **object:** the record version read (SHA-512);
- **result:** the record blocks written: `enrichment`, `keywords`, `entities` (its `pid`);
- **parameters:** the LLM model; the vocabulary versions (the asset and the build);
- **limits:** `split` (KeyBERT chunks) and the vocabulary fit as a note until Q6 is answered;
- **components:** the model in use and the vocabularies (AMČR thesaurus, TEATER) with their terms, and the
  statistical method's software and model; facts only, never merged.
- **Internal hashes stay SHA-256** (`vocab_build.py:65`, `llm_run.py:511`, `dm_run.py:150`): not AMČR file identities.

## Depends on

- Hub tasks 1 (grants, `_migrate_1_to_2()`), 2 (no licence block), 3 (`file_entity` with SHA-512), 4 (the limit
  effects), 5 (one line-category originator); then re-vendoring.
- **Q1:** the shape of the per-block `run_uuid`.
- **Q6:** the prompt carries only the vocabulary that fits the model's context (`service/api.py:524-531`, noted
  `trimmed`; 8,192 → 397 terms, `../digests/2.digest.md`). Whether that is the trimming D13 forbids is for the
  meeting. Until then it is recorded as a `limits` note and the behaviour does not change; it must not go through
  the raising path that hub task 4 gives `trimmed`.
- The distribution names: aiscr-docs-pipeline#13 (the store step's list of outputs).

## Superseded in this repository's logs

Open issues (marked in place, 11-11):

- `digests/2.digest.md:192`, `plans/2.plan.md:13-14`: `controlled-live.yml` on every push, the weekly live lane →
  atrium-project#81; also the CI row, `digests/2.digest.md:262`.
- `digests/2.digest.md:256`: the vocabulary trimmed to the context budget → Q6.
- `digests/2.digest.md:259`: the vocabulary build's sha256s in the paradata → stored files by SHA-512; internal
  hashes unchanged.
- `digests/3.digest.md:28`, `:148`, `plans/3.plan.md:303`: runs that can start now → parked during the pilot
  phase.
- `digests/3.digest.md:130-131`, `plans/3.plan.md:295-297`: the tree's SHA-256 in the paradata → moot while parked.

Closed #1 (listed, not edited):

- `digests/1.digest.md:34`, `:52`, `:249`, `plans/1.plan.md:17`, `:29`: an output or run-level licence → none is
  computed; the model is a component with its terms (D2).
- `digests/1.digest.md:45`: `controlled-live.yml` weekly and on `test` pushes → atrium-project#81.
- `plans/1.plan.md:70`: `Garbage` and `Inverted` among the untrustworthy categories → they leave `categ` (D17, D18).

## Not in scope

- #2 (research, deferred past the pilot phase) and #3 (parked with atrium-project#83).
- The cluster research runs (`llm_run.py`, its `trimmed` notes at `:538` and `:665`): not pipeline outputs.
- CI schedules: atrium-project#81, CI on pull requests and releases only, security updates excepted. The schedules
  of `controlled-live.yml`, `vocab-refresh.yml` and `scheduled-smoke.yml` go; `codeql.yml` and `security.yml` keep
  theirs; `gpu-inference.yml` has no active schedule, and its commented-out "restore" note goes.
- The document's licence: AMČR's RO-Crate only.
- `plans/teitok_conformance_plan.md` (a copy of nlp-enrich's; left as it is).
