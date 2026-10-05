# Keyword extraction API service

One service for the stage "keywords" of the ATRIUM pipeline (atrium-keyword-extract#1): the
document record after [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich), or a plain text,
goes in, and the **keywords of the document and of each page** come out, every keyword with its
method, score and rank, plus the run's **paradata** (a Process Run Crate `CreateAction`).

Two kinds of keywords are meant to run here, chosen by `kind`:

| Kind          | What it is                                                                                               | In this release                                                           |
|---------------|----------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| `statistical` | KeyBERT (the default), YAKE, or the legacy KER method — the methods of nlp-enrich's `keywords.py`        | built                                                                     |
| `controlled`  | the LLM over the AMČR and TEATER vocabularies, with entity links — from llm-enrich's `/extract_keywords` | not yet: asked for alone → 501; with `kind=both` it is reported `skipped` |

The record is read, not written. The `keywords` block of the record is atrium-project#73, so this
release answers with the keywords in the response and leaves the record's blocks to the stages that
own them. The kinds are always kept apart, and every keyword says which method produced it.

## Quick start

```bash
pip install -r requirements.txt -r service/requirements.txt
python -m service.api                  # honours PORT/HOST; default 0.0.0.0:8000
# or, for development with auto-reload:
uvicorn service.api:app --host 0.0.0.0 --port 8000
# or in Docker:
docker compose --profile api up
```

```bash
# a text, YAKE (no model to load)
curl -s -X POST localhost:8000/extract_keywords_text -H 'Content-Type: application/json' \
  -d '{"text": "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou.", "method": "yake"}'

# the record after nlp-enrich, per document and per page
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@CTX000000001.document.json;type=application/json" -F kind=statistical
```

## Endpoints

| Method | Path                     | Purpose                                                                                                                                                     |
|--------|--------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/info`                  | service id, endpoints, the methods (default, descriptions, the KeyBERT model), the kinds (available, planned), `limits` and `limits_meta`, `openapi_sha256` |
| GET    | `/health`                | liveness — 200 always, even mid-shutdown                                                                                                                    |
| GET    | `/ready`                 | readiness — 503 until the startup warm-up (the KeyBERT model, when it is the default) has finished, 200 while serving, 503 the instant `SIGTERM` arrives    |
| POST   | `/extract_keywords`      | **the entry point** — the record as an upload (`document_json`); keywords per document and per page                                                         |
| POST   | `/extract_keywords_text` | the same on a plain text in a JSON body (no pages)                                                                                                          |

### `POST /extract_keywords` (multipart form)

| Field           | Default    | Notes                                                                                                                                                                                                                     |
|-----------------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `document_json` | *required* | the ATRIUM document record. Its `lines[].text` are read per page (lines with `categ` `Trash`, `Garbage`, `Inverted` or `Empty` are left out); `content.text` when there are no lines. Not openable → 422 `invalid_record` |
| `kind`          | `both`     | `statistical`, `controlled` or `both`                                                                                                                                                                                     |
| `method`        | server's   | `keybert` \| `yake` \| `legacy`; absent → the server's `DEFAULT_KW_METHOD` (`keybert` unless set; `/info` `methods.default`). The spec's default is null                                                                  |
| `num_keywords`  | `20`       | per list; at most `MAX_KEYWORDS`                                                                                                                                                                                          |
| `lang`          | `cs`       | Czech-pinned in v1 (YAKE's stop words)                                                                                                                                                                                    |
| `per_page`      | `true`     | also extract per page, from `lines[].page`                                                                                                                                                                                |

`POST /extract_keywords_text` takes the same options as a JSON body (`text`, `doc_id`, `kind`,
`method`, `num_keywords`, `lang`).

### The methods

| `method`  | What it is                                                                           | Score                                     | Needs                                                                          |
|-----------|--------------------------------------------------------------------------------------|-------------------------------------------|--------------------------------------------------------------------------------|
| `keybert` | embedding-based; best quality, uses a GPU when there is one                          | cosine similarity, [0, 1]                 | the embedding model (first use)                                                |
| `yake`    | unsupervised statistical, CPU only (**AGPL-3.0**: a run that uses it is declared so) | inverted YAKE score, normalised to [0, 1] | —                                                                              |
| `legacy`  | KER: counts the lemmas of nouns, proper nouns and adjectives                         | an occurrence count                       | `lines[].lemma` and `lines[].upos` (written by nlp-enrich); without them → 422 |

Scores mean different things per method, so compare them only within one method and one list; every
keyword carries `method` and `rank`.

### JSON response

```jsonc
{
  "doc_id": "CTX000000001",
  "kind": "both",
  "method_requested": "keybert",
  "method_used": "keybert",
  "keywords": [{"keyword": "sídlištní keramika", "score": 0.61, "method": "keybert", "rank": 1}],
  "pages": [{"page": "1", "keywords": [{"keyword": "keramika", "score": 0.58, "method": "keybert", "rank": 1}]}],
  "kinds": [
    {"kind": "statistical", "status": "ok", "detail": null},
    {"kind": "controlled", "status": "skipped", "detail": "not in this release of keyword-extract (atrium-keyword-extract#1)"}
  ],
  "words": 412,
  "paradata": { "@type": "CreateAction", "…": "…" },
  "limits_applied": []
}
```

`paradata` is the run's Process Run Crate `CreateAction` (atrium-project#71): its `@id` is the run's
`run_uuid`, `object` is what the call was sent, `result` the keywords it answered with, and
`paradataRecord` the paradata itself, including the licence of the run computed from the methods
used. `limits_applied` lists every limit that shaped the result without refusing it (a KeyBERT
document chunked, a chunk over the encoder's window).

## How it works

The record's lines are joined per page and per document (`Trash`, `Garbage`, `Inverted` and `Empty` lines left out). One
call runs the chosen method over the document and, with `per_page`, over each page — KeyBERT in one
batch — in a worker thread, inside one of `MAX_CONCURRENT_REQUESTS` slots. The batch CLI
(`keywords.py`) shares the three method implementations: it reads CoNLL-U or TEITOK files instead of
a record. The KeyBERT model is loaded at startup when it is the default, so the first request does not
pay for it; a model that does not load does not stop the service, and the first request that needs it
answers 500 with the cause.

## Configuration (environment)

| Variable              | Default   | Meaning                                                                                   |
|-----------------------|-----------|-------------------------------------------------------------------------------------------|
| `PORT`                | `8000`    | port the service **binds**, and the one `service/healthcheck.py` probes (issues #55, #58) |
| `HOST`                | `0.0.0.0` | bind address (issue #58). ⚠️ see the warning below                                        |
| `GRACEFUL_SHUTDOWN_S` | `20`      | seconds uvicorn waits for in-flight requests (issue #55)                                  |
| `RELOAD`              | `false`   | filesystem auto-reload — development only                                                 |
| `LOG_LEVEL`           | `INFO`    | root logger level for the `python -m service.api` start path (issue #61)                  |
| `ALLOWED_ORIGINS`     | `*`       | CORS origins                                                                              |
| `DEFAULT_KW_METHOD`   | `keybert` | default statistical method                                                                |

Every limit — `MAX_UPLOAD_MB`, `MAX_DOCUMENT_WORDS`, `MAX_KEYWORDS`, `MAX_CONCURRENT_REQUESTS` and the
KeyBERT chunk settings — is listed under [Limits](#limits).

`PORT` and `HOST` are read by `service/api.py`'s `__main__` block, which is what the `api` image's
`ENTRYPOINT` (`python -m service.api`) runs.

> ⚠️ `HOST=127.0.0.1` yields a container that reports **healthy** and serves nobody:
> `service/healthcheck.py` always probes loopback by design and never reads `HOST`, so a loopback bind
> passes every probe while being unreachable from outside the container.

## Limits

Every limit is an environment setting (atrium-project#53, factor III), declared in `tool_limits.py`
and reported with its current value by `GET /info` (`limits`; `limits_meta` says which variable sets it
and whether the value came from the environment or the default). A malformed value stops the service
at startup, naming the variable. An input over a limit is refused with the [harmonised error](#errors);
a limit that shapes a result without refusing it is named in `limits_applied`.
`tests/test_limits_contract.py` checks this table against `tool_limits.py` and `.env.example`.

| Key (`/info`)             | Variable                                                            | Default | Unit     | Over the limit                                                                                                   |
|---------------------------|---------------------------------------------------------------------|---------|----------|------------------------------------------------------------------------------------------------------------------|
| `max_upload_mb`           | `MAX_UPLOAD_MB`                                                     | 10      | MB       | 413 `limit_exceeded` — the uploaded record, and the whole `/extract_keywords_text` body                          |
| `max_document_words`      | `MAX_DOCUMENT_WORDS`                                                | 200000  | words    | 413 `limit_exceeded` — the record's lines or the text                                                            |
| `max_keywords`            | `MAX_KEYWORDS`                                                      | 100     | keywords | 422 `limit_exceeded` — `num_keywords` over it                                                                    |
| `max_concurrent_requests` | `MAX_CONCURRENT_REQUESTS`                                           | 2       | requests | 429 `busy` with `Retry-After: 15`                                                                                |
| `keybert_chunk_words`     | `KEYBERT_CHUNK_WORDS`                                               | 400     | words    | a longer document is embedded in overlapping chunks and its keywords merged — `split` note                       |
| `keybert_chunk_overlap`   | `KEYBERT_CHUNK_OVERLAP`                                             | 50      | words    | the words two consecutive KeyBERT chunks share                                                                   |
| `keybert_max_seq_tokens`  | — (derived from the KeyBERT model, `kw_config.txt` `KEYBERT_MODEL`) | —       | tokens   | a longer chunk is embedded from its start — `trimmed` note; 128 for the default model, `null` until it is loaded |

`KEYBERT_CHUNK_WORDS` stays 400 until an evaluation says otherwise: with the default encoder's 128-token
window, most 400-word chunks are embedded from their start, and `limits_applied` says how many.
There is no per-request time limit yet: the extraction runs in a thread that cannot be stopped, and the
controlled kind (an LLM call) will bring its own.

## Errors

Every error has one JSON body (hub `docs/agent_skill_strategy.md` §4.4, atrium-project#32 item 2):
`{"status": <int>, "reason": <code or null>, "detail": "<text>"}`. `detail` is always a string. A limit
refusal adds `limit` (`{key, env, value, observed, unit}`); a request validation error adds FastAPI's list
of problems as `errors`.

| Status | `reason`         | When                                                                                                                |
|--------|------------------|---------------------------------------------------------------------------------------------------------------------|
| 413    | `limit_exceeded` | over `MAX_UPLOAD_MB` or `MAX_DOCUMENT_WORDS`                                                                        |
| 422    | `invalid_record` | the `document_json` sent cannot be opened (not UTF-8 JSON, not an object, a newer `schema_version` major)           |
| 422    | `limit_exceeded` | `num_keywords` over `MAX_KEYWORDS`                                                                                  |
| 422    | `null`           | a record or text with nothing to read, the legacy method without lemmas, a value outside the spec's enums or bounds |
| 429    | `busy`           | every extraction slot taken; retry after `Retry-After` seconds                                                      |
| 500    | `null`           | a method's package is missing or the KeyBERT model could not be loaded — the detail names the cause                 |
| 501    | `null`           | `kind=controlled` alone: the controlled kind is not in this release                                                 |

## Shutdown behavior (issue #55)

The `api` image declares `HEALTHCHECK` (shallow `GET /health`, via the vendored `service/healthcheck.py`)
and `STOPSIGNAL SIGTERM`, and sets `ENV GRACEFUL_SHUTDOWN_S=20`, which `service/api.py`'s `__main__` block
passes to uvicorn as `timeout_graceful_shutdown`.

On `SIGTERM` the service flips `GET /ready` to **503** immediately, so an orchestrator stops routing new
requests here (`GET /health` deliberately stays 200 — a liveness probe failing mid-shutdown would get the
container killed before it finished draining), then lets uvicorn drain in-flight HTTP requests (up to 20s).
Every request is synchronous, so there is no background work to wait for. The container exits **143**
(128 + SIGTERM) after a clean shutdown, not 0 — uvicorn re-raises the captured signal on purpose so a
supervisor sees the real cause. That is a normal stop, not a crash. See `docs/k8s_deployment.md` in the hub
for the full grace-period budget and the Kubernetes probe contract.

## OpenAPI (the typed contract)

The service's OpenAPI document is committed as [`service/openapi.json`](openapi.json) and attached to every
release as `openapi.json` with its `openapi.json.sha256` (atrium-project#32 round 2). It is what a client is
generated from: every request and response field is typed (the response as `ExtractResponse`), every error
response is the body above, the registered `reason` codes are listed in `x-atrium-reason-codes`, and
`paradata` is typed as the `CreateAction`. `GET /info` reports `openapi_sha256`, the digest of the spec the
running image serves — equal to the release's `openapi.json.sha256` for an image built from that tag.

- **After an API change**, regenerate and commit it:
  `python atrium_openapi.py export --app service.api:app --out service/openapi.json`.
  `tests/test_openapi_contract.py` fails while it is stale, and when any setting (`DEFAULT_KW_METHOD`, every
  limit) changes it.
- **Compatibility.** Each release compares its spec with the previous release's (`release.yml`,
  `atrium_openapi.py compare` with oasdiff): a breaking change fails the release unless the major version went
  up, and a removed reason code always fails. The spec declares `info.x-atrium-service-previous`
  (`atrium-nlp-enrich`), the id of the service the statistical keywords came from.
- **fastapi and pydantic are pinned** exactly (`service/requirements.txt`, `requirements-test.txt`): the spec is
  generated by them. Bump both by hand and regenerate.

## Tests

```bash
pip install -r requirements.txt -r service/requirements.txt -r requirements-test.txt
pytest -m "not slow"
```

`tests/test_api_service.py` drives the endpoints in-process (YAKE and the legacy method run for real; KeyBERT
is stubbed), and `tests/test_api_contract.py` holds every response, refusals included, to the schema the
published spec declares for it.
