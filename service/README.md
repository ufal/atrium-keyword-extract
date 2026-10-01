# NLP enrichment API service

Single-file entry point for the ATRIUM NLP enrichment pipeline (issue
[#8](https://github.com/ufal/atrium-nlp-enrich/issues/8)): upload ordered text
lines — a table, a `.txt`, or a TEITOK file converted by flexiconv — get back enriched
**TEITOK XML + keywords + paradata**. The four core
stages (`manifest → udp → nt → stats`) always run; **LLM enrichment is excluded
from every API entry point**.

## Quick start

```bash
./setup_api_service.sh                 # venv + deps + KeyBERT prefetch + serve
# or, manually:
pip install -r requirements.txt -r service/requirements.txt
python -m service.api                  # honours PORT/HOST; default 0.0.0.0:8000
# or, for development with auto-reload:
uvicorn service.api:app --host 0.0.0.0 --port 8000
```

Two-terminal smoke test:

```bash
# terminal 2
python service/test_api.py -f data_samples/DOC_LINE_CATEG/CTX000000001.csv
```

## Endpoints

| Method | Path                | Purpose                                                                                                                                                                      |
|--------|---------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/`                 | minimal landing page (see `/docs` for OpenAPI UI)                                                                                                                            |
| GET    | `/info`             | service id, endpoints, stage plan, pinned models, keyword methods + default, `limits` (every [limit](#limits), current value) and `limits_meta` (the variable behind each)   |
| GET    | `/health`           | liveness — 200 always, even mid-shutdown. `?deep=true` adds config validity via `run_pipeline.py --dry-run` + UDPipe/NameTag reachability (503 on failure or while draining) |
| GET    | `/ready`            | readiness — 503 until warmup finishes, 200 while serving, 503 the instant `SIGTERM` arrives. The Kubernetes `readinessProbe`/`startupProbe` target                           |
| POST   | `/enrich`           | **single-file entry point** — upload CSV/XLSX/TXT, or a converted TEITOK `.xml`; optionally the ALTO of a table's pages                                                      |
| POST   | `/enrich_text`      | same pipeline for inline JSON                                                                                                                                                |
| POST   | `/jobs`             | the `/enrich` form as a background job: returns `{"job_id", "status": "queued"}` at once; 429 `busy` when `MAX_QUEUED_JOBS` jobs already wait                                |
| GET    | `/jobs/{id}`        | the job's `status` (`queued` until it holds a slot, `running`, `done`, `failed`), `error` and `reason` (`limit_exceeded` when `API_JOB_TIMEOUT` stopped it)                  |
| GET    | `/jobs/{id}/result` | the `/enrich` JSON envelope of a finished job (409 while it runs)                                                                                                            |
| DELETE | `/jobs/{id}`        | forget a job (finished jobs are also forgotten `JOB_TTL_S`, an hour, after they end); job ids are local to the replica                                                       |
| POST   | `/rescale`          | rescale a TEITOK's bboxes to page images of another size, page by page                                                                                                       |
| POST   | `/project_record`   | project a finished record's page categories and llm-enrich categories/keywords onto its TEITOK header (opt-in, atrium-project#70)                                            |

### `POST /enrich` (multipart form)

| Field               | Default    | Notes                                                                                                                                                                                                                                                             |
|---------------------|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `file`              | *required* | `.csv` (needs a `text` column; optional `page_num`, `line_num`), `.xlsx`, `.txt` (a form feed starts a new page), or a TEITOK `.xml` (`*.teitok.xml`, or any `.xml` starting with `<TEI`) — see [Layout inputs](#layout-inputs)                                   |
| `alto`              | *optional* | ALTO XML of the pages a `.csv`/`.xlsx` lists the lines of — see [Layout inputs](#layout-inputs)                                                                                                                                                                   |
| `kw_method`         | server's   | `keybert` \| `yake` \| `legacy` \| `none`; absent → the server's `DEFAULT_KW_METHOD` (`keybert` unless set; `/info` `keyword_methods.default`). The spec's default is null: it no longer changes with the setting (atrium-project#32)                             |
| `num_keywords`      | `20`       | 1–100                                                                                                                                                                                                                                                             |
| `lang`              | `cs`       | Czech-pinned in v1                                                                                                                                                                                                                                                |
| `format`            | `json`     | `json` envelope, or `zip` of the workspace `OUTPUT_DIR`; any other value → 422 (it silently became `json` before atrium-project#32 round 2)                                                                                                                       |
| `document_json`     | *optional* | baseline ATRIUM Document JSON (or an AMČR seed) to accrete onto — see below; not a JSON object → 422 `invalid_record`                                                                                                                                             |
| `teitok_enrichment` | `false`    | opt-in (atrium-project#70): the returned TEITOK also carries the record's page categories (`pb/@ana`) and this run's keywords, per document and per page, in its header — see [`POST /project_record`](#post-project_record-multipart-form). `/jobs` takes it too |

`keybert` is the best/default backend. If its preflight fails at runtime the
service **degrades once to `yake`** and reports `method_requested` vs
`method_used` rather than failing the enrichment.

### Layout inputs

The TEITOK the service returns has the layout of what it was given (issue
[#38](https://github.com/ufal/atrium-nlp-enrich/issues/38)); `layout_source` in the envelope says which:

| Upload                                 | `layout_source` | The TEITOK                                                                                         |
|----------------------------------------|-----------------|----------------------------------------------------------------------------------------------------|
| `.csv`/`.xlsx`/`.txt`                  | `rows`          | one `<pb>` per page and one `<lb>` per line of the input; no boxes, no facsimile, no page images   |
| `.csv`/`.xlsx` + `alto`                | `alto`          | as the CLI with `INPUT_ALTO_DIR`: word, line and block boxes, `<facsimile>`, `<figure>`s           |
| a TEITOK `.xml` converted by flexiconv | `teitok`        | as the CLI with `FLEXICONV_ANNOTATE=true`: its pages, lines and word boxes, its page images' names |

* A **TEITOK upload** is text and layout at once: its rows (`teitok_read`) go through the
  pipeline as the document's table, and the file itself becomes that document's layout — the
  same claim the CLI's stage 1 makes. Convert PDF, DOCX, PAGE XML, hOCR, … to TEITOK with
  `api_flexiconv.sh` (CLI) first: flexiconv is GPL-3.0 and is **not** in the service image. A file
  that is not well-formed, or breaks TEITOK-core rules (duplicate ids, references that point
  nowhere), is refused with 422 and the diagnostics.
* An **`alto` part** goes with a `.csv`/`.xlsx` (e.g. alto-postprocess's `DOC_LINE_CATEG` table and
  the ALTO it was made from); with a `.txt` or a TEITOK file it is refused (422). A PAGE XML or
  hOCR file in its place is refused with the hint to convert it with `api_flexiconv.sh`.
* The `doc_id` is the file name without `.teitok.xml`, `.alto.xml` or the table extension.

### `POST /enrich_text` (JSON)

```json
{ "doc_id": "CTX1", "lines": ["Výzkum odhalil základy kostela.", "..."],
  "kw_method": "keybert", "num_keywords": 20, "format": "json",
  "document_json": { "...optional baseline record, inline..." },
  "teitok_enrichment": false }
```

### The `document_json` accretion part

Rule 1 of the document-JSON contract (the hub's `docs/document_schema.md`, issue
[atrium-llm-enrich#13](https://github.com/ufal/atrium-llm-enrich/issues/13)): a service **accepts
and returns an optional `document_json` part**. `/enrich` and `/jobs` take it as an upload part;
`/enrich_text` takes it as an embedded object.

When supplied, the response's `document_json` carries the record back with only
nlp-enrich's contribution merged in — its `entities[]` rows, whose `teitok_ref` is the
entity's `<name id>` (`n-1`, …) in the returned TEITOK — while every other tool's block
(`page_categories`, `lines`, `translations`, `enrichment`, …) passes through **untouched**.
(`pages[].teitok_surface`, the `<surface id>` `facs-P` of a page, is written for pages that
have a surface: with an `alto` part, or a TEITOK upload whose pages name an image or a size.)
This is the same accretion the CLI performs via
`run_pipeline.py --document-json/--document-json-out`; the service simply threads the flags
through to it, so there is one implementation, not two.

* Omit the part and the key is **absent** from the envelope — not `null`. Existing clients
  see no change at all.
* Supply it and get `null` back, and the pipeline produced no record (no CoNLL-U reached the
  document hook, or the hook failed and degraded per rule 3). `run_pipeline.py` prints
  `[document-json] NOT WRITTEN` on stdout in that case; the service's `stages` and the
  pipeline log say why.
* A baseline that does not validate against `atrium_document.schema.json` is still accepted
  (rule 6): the pipeline warns, names the schema error, and accretes onto it anyway rather
  than turning one bad upstream record into a stalled pipeline.
* A baseline that cannot be opened at all — not UTF-8 JSON, not a JSON object, or a
  `schema_version` with a newer major — is refused before the pipeline runs, with 422
  `reason: invalid_record` (atrium-project#32 round 2). It used to reach the stats stage,
  which warned and ran on, so the envelope came back with `document_json: null` and no word
  of why.

### JSON envelope

```json
{
  "doc_id": "...", "pages": 2,
  "stages": [ {"script": "api_4_stats", "successfully_processed": 1, ...} ],
  "teitok_xml": "<?xml ...>",
  "keywords": [ {"keyword": "...", "score": 0.91} ],
  "ne_summary": [ {"file": "...", "page": "1", "entities": [...] } ],
  "paradata": { "@id": "urn:uuid:...", "@type": "CreateAction", "...": "..." },
  "limits_applied": [ {"limit": "keybert_chunk_words", "value": 400, "effect": "split",
                       "count": 1, "detail": "...", "program": "nlp-enrich"} ],
  "method_requested": "keybert", "method_used": "keybert",
  "llm": null,
  "layout_source": "rows",
  "teitok_schema_valid": true, "teitok_schema_errors": [],
  "document_json": { "...only when a baseline was supplied..." }
}
```

`limits_applied` lists every [limit](#limits) that shaped the result without refusing it
(atrium-project#53) — a document embedded in KeyBERT chunks, chunks longer than the encoder's
window, pages whose entity summary kept its top N. The stages record them in their paradata;
this is the merged record's list (`[]` when no limit applied).

**`paradata`** is the call's provenance (atrium-project#71): one Process Run Crate `CreateAction`,
built by `atrium_rocrate.create_action()` from the run's merged pipeline-run record (its
`paradataRecord`, with the licence union of every stage). Its `@id` is the `run_uuid` the stats
stage stamped on the blocks it wrote into `document_json`, or, without a record, the merged run's
own; `object` is what the call was sent (the upload or `lines.json`, a separate `alto` part, the
record), `result` the blocks written and the TEITOK; `agent` is `ATRIUM_RUN_AGENT` when set. It
is `null` only for a run that left no paradata. An error response carries no action. Hub
[`docs/rocrate_export.md`](https://github.com/ufal/atrium-project/blob/main/docs/rocrate_export.md) §5
describes it.

`layout_source` is `rows`, `alto` or `teitok` ([Layout inputs](#layout-inputs)).
`teitok_schema_valid`/`teitok_schema_errors` are the output-contract verdict on `teitok_xml`
(`validate_teitok_xml.py`'s default `contract` profile); a run whose TEITOK fails the contract
never gets here — stage 4 stops with exit code 5, answered as 500.

`format=zip` instead streams the full workspace `OUTPUT_DIR`
(`TEITOK/`, `UDP_NE/`, `KW_PER_DOC_*/`, summary CSVs, `paradata/`, and
`<doc_id>.document.json` when a baseline was supplied).

### `POST /rescale` (multipart form)

A standalone coordinate transform — **not** part of the NLP pipeline (no
subprocess, no models, no workspace). Given a TEITOK document and the size of its page
images, it rescales every facsimile coordinate (the `bbox="x1 y1 x2 y2"` pixel boxes,
`pb@bbox` and the `<surface>` `lrx`/`lry` extents) from the document's own coordinate space,
page by page, so annotations line up exactly on top of images of that size. Each box is
scaled by the `<surface>` of the page it is on (the one its `<pb corresp>` names, or the k-th
surface for the k-th `<pb>`) and clamped to that page; `clamped` counts the coordinates that
had to move. A `<change type="rescaled">` in `<revisionDesc>` records the transform. This works for both coordinate origins the writer offers
(`BBOX_ORIGIN=page`, the default, and `printspace`): in both, `<surface>` declares the
extent the boxes are measured in.

| Field       | Default    | Notes                                                                                                                             |
|-------------|------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `file`      | *required* | a `.teitok.xml` (or `.xml`)                                                                                                       |
| `width`     | —          | target image width in pixels (1–`MAX_RESCALE_DIM`), with `height`                                                                 |
| `height`    | —          | target image height in pixels (1–`MAX_RESCALE_DIM`), with `width`                                                                 |
| `scale`     | —          | instead of `width`/`height`: every page image is this fraction of its `<surface>` (0–100); required when the pages differ in size |
| `format`    | `json`     | `json` envelope, or `xml` to download the rescaled `.teitok.xml`                                                                  |
| `fix_names` | `true`     | repair malformed `<name>…</n>` closings to `</name>`                                                                              |

The **source** coordinate space is read from the document itself: each page's
`<surface>` `lrx`/`lry` (the authoritative page extent); `width`/`height` are refused (422)
for a document whose surfaces differ in size — they would distort some pages — so give
`scale` there. Without any sized `<surface>` it falls back to the maximum extent of all `bbox`
boxes (`source_kind: "bbox-extent"`, approximate). The transform is a surgical,
text-level rewrite that only touches the numeric values, so it is robust to the
non-well-formed quirk of older TEITOK exports (named entities open `<name>` but close
`</n>`; the current writer closes `</name>`) that makes a strict XML parse fail.

Because that `</n>` quirk produces invalid XML, the endpoint also **repairs it by
default** — rewriting stray `</n>` closings to `</name>` so the returned document
parses cleanly (`name_tags_fixed` reports how many were fixed). This is a no-op
on already-valid TEITOK. Pass `fix_names=false` to leave the markup byte-for-byte
as-is and only rescale coordinates.

```bash
curl -s -F "file=@CTX000000001.teitok.xml" -F "width=827" -F "height=1170" \
     http://localhost:8000/rescale            # JSON envelope
curl -s -F "file=@CTX000000001.teitok.xml" -F "width=827" -F "height=1170" \
     -F "format=xml" -OJ http://localhost:8000/rescale   # download rescaled XML
curl -s -F "file=@mixed_pages.teitok.xml" -F "scale=0.5" \
     http://localhost:8000/rescale            # pages of different sizes
```

`format=json` response:

```json
{
  "teitok_xml": "<?xml ...>",
  "source": { "width": 1654, "height": 2339 },
  "source_kind": "surface",
  "target": { "width": 827, "height": 1170 },
  "scale": { "sx": 0.5, "sy": 0.500214 },
  "pages": [
    { "surface": "facs-1", "source": { "width": 1654, "height": 2339 }, "target": { "width": 827, "height": 1170 } },
    { "surface": "facs-2", "source": { "width": 1654, "height": 2339 }, "target": { "width": 827, "height": 1170 } }
  ],
  "boxes_rescaled": 37,
  "clamped": 0,
  "name_tags_fixed": 0,
  "schema_valid": true, "schema_errors": []
}
```

`source`, `target` and `scale` describe the first page; `pages` lists every page with a sized
`<surface>`.

### `POST /project_record` (multipart form)

A standalone header transform (no pipeline) for a record that is complete only after this
service ran: after page-classification and llm-enrich (atrium-project#70 item 2, ufal/flexiconv#1).
Opt-in by being called; AMČR's stored TEITOK keeps linguistics and layout only.

| Field           | Default    | Notes                                                                                   |
|-----------------|------------|-----------------------------------------------------------------------------------------|
| `file`          | *required* | the document's `.teitok.xml` as nlp-enrich wrote it (format `teitok-2`)                 |
| `document_json` | *required* | the document's finished record                                                          |
| `format`        | `json`     | `json` envelope, or `xml` to download the projected `.teitok.xml`                       |

What is written — `pb/@ana` and a `classDecl` taxonomy for the page categories,
`profileDesc/textClass/keywords` for llm-enrich's TEATER/AMČR categories and controlled
keywords, each pointing at its pages — is the table in the main README's
[Record projection onto TEITOK](../README.md#record-projection-onto-teitok-opt-in). Nothing
below the header changes but `pb/@ana`; projecting again replaces an earlier projection. 422
when the TEITOK is not the record's document (its `<title>` is neither `doc_id` nor the id of
`source.filename`), is not this writer's `teitok-2` output, or does not validate.

```bash
curl -F file=@TEITOK/CTX000000001.teitok.xml -F document_json=@CTX000000001.document.json \
     http://localhost:8000/project_record                  # JSON envelope
curl -F file=@TEITOK/CTX000000001.teitok.xml -F document_json=@CTX000000001.document.json \
     -F format=xml -OJ http://localhost:8000/project_record  # download the projected XML
```

```json
{ "doc_id": "CTX000000001", "teitok_xml": "<?xml ...",
  "report": { "page_categories": 2, "teater_categories": 1,
              "controlled_keywords": { "cs": 2, "en": 2 },
              "statistical_keywords": { "document": 0, "pages": 0 },
              "unresolved_pages": [], "notes": [], "changed": true },
  "schema_valid": true, "schema_errors": [] }
```

## How it works

`PipelineManager` treats `run_pipeline.py` as the **only** execution interface —
it never calls the stage scripts directly. Each request gets a fresh workspace
under `TEMP/api_jobs/<job_id>/` with every pipeline directory relocated inside
it, so resume / paradata-collision / `FAIL_ON_EMPTY` semantics behave as a clean
first run and concurrent requests can't collide. Every input form is normalized
to a canonical `text[,page_num,line_num]` CSV so stage 1 always runs on the same
path and no input type bypasses a mandatory step.

The runner's exit codes map to HTTP: `0`→200; `3` (keyword preflight)→retry with
`yake`, else 503; `4` (keyword backend failed at runtime)→503; `5` (the TEITOK failed its
output contract — a writer defect, "please report it")→500; `1` (empty run)/`2` (missing
stage)/other→502; an input over a limit → 413/422 `limit_exceeded`, a run over
`API_JOB_TIMEOUT` → 504 `limit_exceeded`, every slot or the queue full → 429 `busy`
([Limits](#limits), [Errors](#errors)); an unusable upload→422.

UDPipe/NameTag models stay operator-pinned in `config_api.txt` and are surfaced
read-only via `/info`. The layout comes with the upload ([Layout inputs](#layout-inputs)):
an uploaded TEITOK file is written to `<workspace>/layout/flexiconv/<doc_id>.teitok.xml`
(`TEITOK_FLEXICONV_DIR`, `FLEXICONV_ANNOTATE=true`), an `alto` part to
`<workspace>/layout/alto/<doc_id>.alto.xml` (`INPUT_ALTO_DIR`); both are outside `in/`, which
stage 1 reads as tables. Page images are never uploaded, so a surface keeps the size its
layout declares.

## Configuration (environment)

| Variable              | Default   | Meaning                                                                                   |
|-----------------------|-----------|-------------------------------------------------------------------------------------------|
| `PORT`                | `8000`    | port the service **binds**, and the one `service/healthcheck.py` probes (issues #55, #58) |
| `HOST`                | `0.0.0.0` | bind address (issue #58). ⚠️ see the warning below                                        |
| `GRACEFUL_SHUTDOWN_S` | `20`      | seconds uvicorn waits for in-flight requests (issue #55)                                  |
| `RELOAD`              | `false`   | filesystem auto-reload — development only                                                 |
| `LOG_LEVEL`           | `INFO`    | root logger level for the `python -m service.api` start path (issue #61)                  |
| `ALLOWED_ORIGINS`     | `*`       | CORS origins                                                                              |
| `UDPIPE_URL`          | LINDAT    | attachable UDPipe 2 endpoint (issue #63); same variable name as atrium-translator         |
| `NAMETAG_URL`         | LINDAT    | attachable NameTag 3 endpoint (issue #63)                                                 |
| `DEFAULT_KW_METHOD`   | `keybert` | default keyword backend                                                                   |
| `API_JOBS_ROOT`       | see below | where per-job workspaces are created; computed from the repo root, not a literal          |
| `API_KEEP_WORKSPACES` | unset     | keep per-request workspaces for debugging -- survives only as long as the pod (#35)       |

Every limit — `MAX_UPLOAD_MB`, `MAX_WORDS`, `MAX_CONCURRENT_JOBS`, `API_JOB_TIMEOUT` and the
rest — is listed under [Limits](#limits).

`PORT` and `HOST` are read by `service/api.py`'s `__main__` block, which is what the `api`
image's `ENTRYPOINT` (`python -m service.api`) runs. Before issue #58 the entrypoint baked
`--port 8000` into an exec-form array — which runs no shell, so `$PORT` could not expand —
while `service/healthcheck.py` read it. Setting `PORT` therefore moved the health *probe*
and not the listener, and the container reported unhealthy forever.

> ⚠️ `HOST=127.0.0.1` yields a container that reports **healthy** and serves nobody:
> `service/healthcheck.py` always probes loopback by design and never reads `HOST`, so a
> loopback bind passes every probe while being unreachable from outside the container.

## Limits

Every limit is an environment setting (atrium-project#53, factor III), declared in
`tool_limits.py` and reported with its current value by `GET /info` (`limits`; `limits_meta`
says which variable sets it and whether the value came from the environment, `config_api.txt`
or the default). A malformed value stops the service at startup, naming the variable. An input
over a limit is refused with the [harmonised error](#errors); a limit that shapes a result
without refusing it is named in `limits_applied`. The three stage limits are also keys of
`config_api.txt` (named in the table): for an API job the variable wins over the template,
which wins over the default, and the service writes the effective value into the job's
config. `tests/test_limits_contract.py` checks this table against `tool_limits.py` and
`.env.example`.

| Key (`/info`)            | Variable                                                            | Default | Unit     | Over the limit                                                                                                                                      |
|--------------------------|---------------------------------------------------------------------|---------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| `max_upload_mb`          | `MAX_UPLOAD_MB`                                                     | 5       | MB       | 413 `limit_exceeded` — per part (the file, `document_json`, `alto`) and for the whole `/enrich_text` body                                           |
| `max_words`              | `MAX_WORDS`                                                         | 30000   | words    | 413 `limit_exceeded` — `/enrich`, `/enrich_text` and `/jobs` alike                                                                                  |
| `max_concurrent_jobs`    | `MAX_CONCURRENT_JOBS`                                               | 2       | jobs     | a synchronous request: 429 `busy` with `Retry-After: 30`; a `/jobs` job stays `queued`                                                              |
| `max_queued_jobs`        | `MAX_QUEUED_JOBS`                                                   | 8       | jobs     | `/jobs`: 429 `busy` with `Retry-After: 30` (0: a job only when a slot is free)                                                                      |
| `api_job_timeout`        | `API_JOB_TIMEOUT`                                                   | 600     | s        | the run and every process it started are stopped, the workspace removed: 504 `limit_exceeded`; a `/jobs` job ends `failed`, reason `limit_exceeded` |
| `job_ttl_s`              | `JOB_TTL_S`                                                         | 3600    | s        | a finished job is forgotten: `/jobs/{id}` answers 404                                                                                               |
| `max_rescale_dim`        | `MAX_RESCALE_DIM`                                                   | 100000  | px       | 422 `limit_exceeded` — `width`/`height` over it, or a page that `scale` takes past it                                                               |
| `word_chunk_limit`       | `WORD_CHUNK_LIMIT`                                                  | 900     | words    | UDPipe gets the text in pieces cut at a line end, annotated in full (`config_api.txt` `WORD_CHUNK_LIMIT`)                                           |
| `lindat_timeout_s`       | `LINDAT_TIMEOUT_S`                                                  | 60      | s        | the UDPipe or NameTag call is retried (`config_api.txt` `TIMEOUT`)                                                                                  |
| `lindat_max_retries`     | `LINDAT_MAX_RETRIES`                                                | 5       | retries  | the stage fails → 502 (`config_api.txt` `MAX_RETRIES`)                                                                                              |
| `keybert_chunk_words`    | `KEYBERT_CHUNK_WORDS`                                               | 400     | words    | a longer document is embedded in overlapping chunks and its keywords merged — `split` note                                                          |
| `keybert_chunk_overlap`  | `KEYBERT_CHUNK_OVERLAP`                                             | 50      | words    | the words two consecutive KeyBERT chunks share                                                                                                      |
| `ne_summary_top_n`       | `NE_SUMMARY_TOP_N`                                                  | 20      | entities | a page keeps its N most frequent entities in `ne_summary` — `trimmed` note (the TEITOK and `document_json` carry every entity)                      |
| `keybert_max_seq_tokens` | — (derived from the KeyBERT model, `kw_config.txt` `KEYBERT_MODEL`) | —       | tokens   | a longer chunk is embedded from its start — `trimmed` note; 128 for the default model, `null` until it is loaded                                    |

`KEYBERT_CHUNK_WORDS` stays 400 until an evaluation says otherwise: with the default encoder's
128-token window, most 400-word chunks are embedded from their start, and `limits_applied`
now says how many.

Not settings: `num_keywords` (1–100) is a bound on a request parameter, part of the API schema
(atrium-project#32 item 1); Starlette's multipart parser keeps its own defaults.

## Errors

Every error has one JSON body (hub `docs/agent_skill_strategy.md` §4.4, atrium-project#32
item 2): `{"status": <int>, "reason": <code or null>, "detail": "<text>"}`. `detail` is always
a string. A limit refusal adds `limit` (`{key, env, value, observed, unit}`); a request
validation error adds FastAPI's list of problems as `errors`.

| Status | `reason`                 | When                                                                                                                         |
|--------|--------------------------|------------------------------------------------------------------------------------------------------------------------------|
| 409    | `null`                   | `/jobs/{id}/result` of a job that is not `done`                                                                              |
| 413    | `limit_exceeded`         | over `MAX_UPLOAD_MB` or `MAX_WORDS`                                                                                          |
| 415    | `unsupported_media_type` | the upload is not `.csv`, `.xlsx`, `.txt` or a TEITOK `.xml`; `accepted` lists them (a 422 before atrium-project#32 round 2) |
| 422    | `invalid_record`         | the `document_json` sent cannot be opened (not UTF-8 JSON, not an object, a newer `schema_version` major)                    |
| 422    | `limit_exceeded`         | `/rescale` over `MAX_RESCALE_DIM`                                                                                            |
| 422    | `null`                   | an unusable upload, a bad parameter (a value outside the spec's enums or bounds), or request validation (`errors`)           |
| 429    | `busy`                   | every processing slot taken (synchronous endpoints), or the `/jobs` queue full; retry after `Retry-After` seconds            |
| 500    | `null`                   | the TEITOK failed its output contract (exit 5) — a writer defect, please report it                                           |
| 502    | `null`                   | a stage failed: an empty run, a missing stage, UDPipe or NameTag after their retries                                         |
| 503    | `null`                   | the keyword backend failed (exit 3/4), or the replica is shutting down                                                       |
| 504    | `limit_exceeded`         | the run took longer than `API_JOB_TIMEOUT` and was stopped                                                                   |

## Shutdown behavior (issue #55)

The `api` image declares `HEALTHCHECK` (shallow `GET /health`, via the vendored
`service/healthcheck.py`) and `STOPSIGNAL SIGTERM`, and sets `ENV GRACEFUL_SHUTDOWN_S=20`,
which `service/api.py`'s `__main__` block passes to uvicorn as
`timeout_graceful_shutdown`. (It was the `--timeout-graceful-shutdown 20` CLI flag until
issue #58 moved the whole start command into that block so `$PORT` could be honoured.)

On `SIGTERM` the service:

1. flips `GET /ready` to **503** immediately, so an orchestrator stops routing new
   requests here (`GET /health` deliberately stays 200 — a liveness probe failing
   mid-shutdown would get the container killed before it finished draining);
2. lets uvicorn drain in-flight HTTP requests (up to 20s);
3. **then waits up to a further 25s for any background `/jobs` run to finish.** This
   step is what a plain in-flight-request count cannot do: `POST /jobs` returns
   `{"status": "queued"}` straight away, so the request is long gone while the job is
   still running. Jobs are registered with `ServiceState.track()`
   (`service/atrium_service.py`) specifically so shutdown waits for them.

⚠️ A job that needs longer than that drain budget is still cut short, and the job
**record** is in-memory (`service/jobs.py`) — so a client polling `/jobs/{id}` across a
restart gets 404 rather than a result. Durable job storage is out of scope here (hub
issue #53, factors IV/VI). See `docs/k8s_deployment.md` in the hub for the full
grace-period budget and the Kubernetes probe contract.

The container exits **143** (128 + SIGTERM) after a clean shutdown, not 0 — uvicorn
re-raises the captured signal on purpose so a supervisor sees the real cause. That is a
normal stop, not a crash.

## OpenAPI (the typed contract)

The service's OpenAPI document is committed as [`service/openapi.json`](openapi.json) and
attached to every release as `openapi.json` with its `openapi.json.sha256` (atrium-project#32
round 2). It is what a client is generated from: every request and response field is typed
(the envelope as `EnrichResponse`, the jobs API, `/rescale`), every error response is the
body above, the registered `reason` codes are listed in `x-atrium-reason-codes`, and a
returned record is typed by the vendored record schema (`AtriumDocument`). `paradata` is
typed as the `CreateAction` of atrium-project#67 R2; until R2 lands it holds the merged
pipeline-run record, which carries the action's paradata properties without its own members.
`GET /info` reports `openapi_sha256`, the digest of the spec the running image serves — equal
to the release's `openapi.json.sha256` for an image built from that tag.

- **After an API change**, regenerate and commit it:
  `python atrium_openapi.py export --app service.api:app --out service/openapi.json`.
  `tests/test_openapi_contract.py` fails while it is stale, and when any setting
  (`DEFAULT_KW_METHOD`, every limit) changes it.
- **Compatibility.** Each release compares its spec with the previous release's
  (`release.yml`, `atrium_openapi.py compare` with oasdiff): a breaking change fails the
  release unless the major version went up (for 0.x, that means 1.0), and a removed reason
  code always fails. New fields, endpoints and reason codes are additive.
- **fastapi and pydantic are pinned** exactly (`service/requirements.txt`,
  `requirements-test.txt`): the spec is generated by them. Bump both by hand and regenerate.

## Tests

`tests/test_api_contract.py` drives every endpoint with the pipeline stood in and holds each
response — 200s and refusals — to the published schema; `tests/test_openapi_contract.py`
(vendored from the hub) checks the committed spec itself.
`tests/test_api_service.py` is fully hermetic (no LINDAT, no models): it
monkeypatches the pipeline subprocess to drop fixture outputs into the
workspace, then exercises the full HTTP contract via FastAPI `TestClient`,
plus input normalization, `doc_id` sanitization, and exit-code→HTTP mapping.
`tests/test_rescale.py` covers the `/rescale` transform and endpoint (including
the non-well-formed `<name>…</n>` TEITOK quirk and documents whose pages differ in size).
`tests/test_teitok_project.py` covers the record projection, `/project_record` and the
`teitok_enrichment` switch.
`tests/test_service_layout_inputs.py` runs the real stage-1 and stage-4 scripts in the
service's workspace (UDPipe/NameTag stood in for) with a TEITOK upload, a table with and
without its ALTO, and the refused combinations.

```bash
pytest -m "not slow" tests/test_api_service.py tests/test_rescale.py tests/test_service_layout_inputs.py tests/test_teitok_project.py
```
