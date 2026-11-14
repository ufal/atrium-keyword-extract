# Strategy — [atrium-project#84](https://github.com/ufal/atrium-project/issues/84) (doc-schema-v2): atrium-keyword-extract's part

> _**Refreshed 2026-11-13**: "Status — round 2" (the code, pushed 11-13 to `doc-schema-v2`) and round 4's notes. The file keeps
> the name `doc-schema-v2.plan.md` (it was `84.plan.md` on 11-12 and 11-13)._
> _**Refreshed 2026-11-12** on ARÚP's output contract of 12 November and atrium-project#84 (motyc, 11-12); code read
> at `0c91740` (= `test`). The change as a whole is the hub's:
> [plan](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/plans/doc-schema-v2.plan.md) ·
> [digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/doc-schema-v2.digest.md) ·
> [contract digest](https://github.com/ufal/atrium-project/blob/test/agent_dev_logs/digests/project_state_1211.md).
> This file is this repository's slice only; its 11-11 version was written before the
> issue existed. The section "2026-11-12" is the current reading; where the 11-11 text below differs, it is
> superseded._

**Status (2026-11-13)**: 🟡 **Implemented, pushed 11-13 to `doc-schema-v2`; see "Status — round 2". Deferred items are listed there.**

**Status (2026-11-12)**: 📋 **Planned, not started. Little changes for keyword-extract: no run data at all in the
record (not even a per-block `run_uuid`), the paradata `result` names the blocks and fields it writes, and its
`entities[].pid` sits on NameTag's entities, so it is not published until atrium-project#78 is settled (D35).
Separately, atrium-project#16 (11-12): the real document text in `data_samples/` is not approved (its #2 plan).**

## 2026-11-12 — what the contract of 12 November changes here

- **Q1 answered:** no per-block `run_uuid` (D1 extended; #84 §2). Task 2 below goes; which run wrote `enrichment`,
  `keywords` and `entities[].pid` is named by each run's paradata `result`.
- **`result` names blocks and fields** (#84 §4): `enrichment` (`items`, `summary`, `topics`), `keywords`
  (`document`, `pages`), `entities` (`pid`). The record version read is in `object` by SHA-512.
- **Lines:** `categ` holds the five categories only (rule 2); `_ALWAYS_SKIP_CATEG` (`llm_client_shared.py:191`) then
  reduces to `Trash` and `Empty` through the hub's `UNTRUSTWORTHY_LINE_CATEGORIES`. The decode flag lives in docproc,
  which this tool does not read. Task 3 stands.
- **Fields the record loses** (`tables[]`, `content.reading_order`, `lines[].group_id`, `style`, page verdicts):
  this tool reads none of them (grep, 11-12).
- **D35:** `entities[].pid` links NameTag's entities to the vocabulary; it is held with the entities until #78.
  Not a code change.
- **Unchanged:** tasks 1, 3–7; Q6 (the vocabulary fit) is still open on the hub list.
- **Shared code:** `service/atrium_service.py`'s `ocr_text_layer` code (185-246) is the hub's shared module and goes
  with digital-convert's refusal (hub task 5).

**Status (2026-11-11)**: _(superseded 11-12)_ 📋 **Planned, not started. keyword-extract reads the record and writes three blocks; in v2
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
2. ~~**One `run_uuid` per block**~~ _(superseded 11-12: none; the paradata `result` names blocks and fields)_ for `enrichment` and `keywords`, in the shape Q1 settles; `entities[].pid` sits in
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

## Status — round 2 (11-13)

Local branch from `test`, on the re-vendored shared modules (record 2.0, paradata 3.0,
`ContentLimitError`); delivered as an archive with the commands to run; pushed 11-13 (below). Nothing posted.

- **Tasks 1, 6:** no `derived_from`, `regenerable` or licence in the record; `write_document_record` returns
  `written()`. The controlled kind's LLM has a `para_config.txt` row.
- **Task 3:** lines skipped by `categ` only (`Trash`, `Empty`); the `quality_score` re-banding left the record path.
- **Task 4, paradata:** `object`: the record read, or a text upload as `original`; `result`: the record's fields
  written; parameters: kind, method, model, vocabulary versions. `keywords.json` / `enrichment.json` left out.
- **Task 5, D13:** a reply cut at `LLM_MAX_NEW_TOKENS` and the consecutive-error stop fail the job, so no partial
  `enrichment`. KeyBERT and the LLM context now run in windows over the whole text (`split`); the vocabulary prompt
  budget is `sampled`.
- **Deviation:** `kind=both` with a failed controlled kind now fails the call (502 or 422) instead of returning the
  statistical half.
- **Tests:** 1014 passed.
- **Pushed** to `doc-schema-v2` (11-13). Round 4 re-vendors the addendum's shared files; the suite then passes
  (1014).

## Depends on

- Hub tasks 1 (grants, `_migrate_1_to_2()`), 2 (no licence block), 3 (`file_entity` with SHA-512), 4 (the limit
  effects), 5 (one line-category originator); then re-vendoring.
- **Q1:** the shape of the per-block `run_uuid`. _(answered 11-12: none)_
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
