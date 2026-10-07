# Keyword extraction API service

One service for the stage "keywords" of the ATRIUM pipeline (atrium-keyword-extract#1): the
document record after [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich), or a plain text,
goes in, and two kinds of keywords come out, chosen by `kind` and always kept apart, plus the
run's **paradata** (a Process Run Crate `CreateAction`):

| Kind          | What it is                                                                                                                                                                                                  | Needs                                                                                          |
|---------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| `statistical` | the keywords of the document and of each page, every one with its method, score and rank: KeyBERT (the default), YAKE, or the legacy KER method — the methods of nlp-enrich's `keywords.py`                 | nothing                                                                                        |
| `controlled`  | per line, the AMČR/TEATER vocabulary term that describes it and the keywords found in it, chosen by an LLM (atrium-keyword-extract#2), with entity links to AMČR and AAT — llm-enrich's `/extract_keywords` | an LLM backend (`LLM_BACKEND`); without one, asked for alone → 501, with `kind=both` `skipped` |

The record: when the controlled kind ran, the response's `document_json` is the record sent with
keyword-extract's `enrichment` block (and `entities[].pid`) written and every other block as it came.
The statistical keywords are answered in the response only: the record's `keywords` block is
atrium-project#73.

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
  -d '{"text": "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou.", "method": "yake", "kind": "statistical"}'

# the record after nlp-enrich, per document and per page
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@CTX000000001.document.json;type=application/json" -F kind=statistical
```

The controlled kind, with OpenRouter (or `LLM_BACKEND=ollama OLLAMA_MODEL=…` for a local Ollama):

```bash
export OPENROUTER_API_KEY=sk-... OPENROUTER_MODEL=openai/gpt-4o-mini
python -m service.api
curl -s localhost:8000/info | jq .controlled        # ready: true, the model, the vocabulary, the prompt
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@CTX000000001.document.json;type=application/json" -F kind=both
```

## Endpoints

| Method | Path                     | Purpose                                                                                                                                                                                                                    |
|--------|--------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/info`                  | service id, endpoints, the methods (default, descriptions, the KeyBERT model), the kinds available, `controlled` (ready or why not, backend, model, vocabulary, prompt), `limits` and `limits_meta`, `openapi_sha256`      |
| GET    | `/health`                | liveness — 200 always, even mid-shutdown                                                                                                                                                                                   |
| GET    | `/ready`                 | readiness — 503 until the startup warm-up (the KeyBERT model when it is the default; the controlled kind's vocabulary and prompt when it is configured) has finished, 200 while serving, 503 the instant `SIGTERM` arrives |
| POST   | `/extract_keywords`      | **the entry point** — the record as an upload (`document_json`): statistical keywords per document and per page, controlled keywords per line, and the record with its `enrichment` block                                  |
| POST   | `/extract_keywords_text` | the same on a plain text in a JSON body (no pages, no record)                                                                                                                                                              |

### `POST /extract_keywords` (multipart form)

| Field           | Default    | Notes                                                                                                                                                                                                                      |
|-----------------|------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `document_json` | *required* | the ATRIUM document record. Its `lines[].text` are read per page (lines with `categ` `Trash`, `Garbage`, `Inverted` or `Empty` are left out); `content.text` when there are no lines. Not openable → 422 `invalid_record`  |
| `kind`          | `both`     | `statistical`, `controlled` or `both`. `controlled` needs the LLM backend (`/info` `controlled.ready`); with `both`, a controlled kind that cannot run is reported in `kinds` and the statistical keywords still come back |
| `method`        | server's   | `keybert` \| `yake` \| `legacy`; absent → the server's `DEFAULT_KW_METHOD` (`keybert` unless set; `/info` `methods.default`). The spec's default is null                                                                   |
| `num_keywords`  | `20`       | per statistical list; at most `MAX_KEYWORDS`                                                                                                                                                                               |
| `lang`          | `cs`       | Czech-pinned in v1 (YAKE's stop words)                                                                                                                                                                                     |
| `per_page`      | `true`     | also extract per page, from `lines[].page` (statistical)                                                                                                                                                                   |

`POST /extract_keywords_text` takes the same options as a JSON body (`text`, `doc_id`, `kind`,
`method`, `num_keywords`, `lang`); the controlled kind reads the text's non-empty lines as one page.

### The methods

| `method`  | What it is                                                                           | Score                                     | Needs                                                                          |
|-----------|--------------------------------------------------------------------------------------|-------------------------------------------|--------------------------------------------------------------------------------|
| `keybert` | embedding-based; best quality, uses a GPU when there is one                          | cosine similarity, [0, 1]                 | the embedding model (first use)                                                |
| `yake`    | unsupervised statistical, CPU only (**AGPL-3.0**: a run that uses it is declared so) | inverted YAKE score, normalised to [0, 1] | —                                                                              |
| `legacy`  | KER: counts the lemmas of nouns, proper nouns and adjectives                         | an occurrence count                       | `lines[].lemma` and `lines[].upos` (written by nlp-enrich); without them → 422 |

Scores mean different things per method, so compare them only within one method and one list; every
keyword carries `method` and `rank`.

### The controlled kind

Each line the quality filter keeps (not `Trash`, `Garbage`, `Inverted` or `Empty`, and long enough to
read) is sent to the model on its own, marked inside its neighbours on the same page, with the
document's first lines and the current heading as context. The model answers in a JSON schema whose
`teater_category` is an enum of the vocabulary's terms, so it cannot invent one:

| Field                   | What it is                                                                                                                                                                                                                               |
|-------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `teater_category`       | the vocabulary term that describes the line, or `Nerelevantní (meta-text)` for a line that is not archaeology. A homonym the vocabulary build qualified (`zámek (sídlo elity)`) comes back bare (`zámek`); its ids tell the senses apart |
| `teater_category_ids`   | every AMČR/TEATER record the term stands for (`{source, id}`): its own and those of the same label the build merged into it. `EMIT_CATEGORY_IDS=false` in `llm_config.txt` leaves it out                                                 |
| `extracted_keywords_cs` | the archaeological terms found in the line, in Czech; empty for meta-text                                                                                                                                                                |
| `extracted_keywords_en` | their English translations, in the same order                                                                                                                                                                                            |
| `confidence_score`      | the model's confidence in `teater_category`, 0–1                                                                                                                                                                                         |

The prompt is the research GPU path's (`llm_run.py`): `prompts/system_prompt.txt` with the blocks the
`PROMPT_*` flags of `llm_config.txt` select, then the vocabulary in the `PROMPT_VOCAB_GROUPING` layout,
then the examples — `python3 prompt_template.py --preview` prints it, and `prompts/RUNBOOK.md` explains
every block and flag. The vocabulary is `data_samples/vocab/union_nested.json` (4718 terms, built by
`vocab_build.py`; `data_samples/vocab/RUNBOOK.md`). A service whose configured guardrail wording
contradicts the vocabulary (`PROMPT_GEO_GUARDRAIL` against `taxonomy_config.json`'s `geo_guardrail`)
does not start the controlled kind, and `/info` `controlled.detail` says why.

The entity links: `entities[]` rows of the record (nlp-enrich's) whose lemma or surface is a vocabulary
term get a `pid` with the term's AMČR URI and its AAT exact match (`vocab_manager.resolve_pid`).

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
    {"kind": "controlled", "status": "ok", "detail": null}
  ],
  "words": 412,
  "enrichment": {"items": [{
    "page": "2", "line": 1,
    "extracted_keywords_cs": ["základy", "gotický kostel"], "extracted_keywords_en": ["foundations", "Gothic church"],
    "teater_category": "kostel",
    "teater_category_ids": [{"source": "amcr", "id": "HES-000021"}, {"source": "teater", "id": "1333"}],
    "confidence_score": 0.92, "citation": "[Source: CTX000000001, Page 2]"
  }]},
  "controlled": {"backend": "openrouter", "model": "openai/gpt-4o-mini", "outcome": "contributed",
                 "stats": {"processed": 37, "attempted": 37, "skipped_filter": 5, "skipped_error": 0, "truncated": 0, "aborted": 0}},
  "document_json": { "doc_id": "CTX000000001", "lines": ["…"], "enrichment": {"items": ["…"]}, "…": "…" },
  "paradata": { "@type": "CreateAction", "…": "…" },
  "limits_applied": []
}
```

`kinds` has one entry per kind asked for: `ok` (it ran), `skipped` (asked for with the other and not
available here) or `failed` (the LLM backend failed every call; the statistical keywords still come
back). `controlled.outcome` separates a model that was asked and found nothing (`empty`: an `enrichment`
block with no items is still written) from one that was never asked (`not-asked`: no line passed the
filter, nothing written). `document_json_schema_error` appears when the returned record does not validate
— only ever because the record sent did not.

`paradata` is the run's Process Run Crate `CreateAction` (atrium-project#71): its `@id` is the run's
`run_uuid`, `object` is what the call was sent, `result` the keywords it answered with and the record
blocks it wrote, and `paradataRecord` the paradata itself, including the licence of the run computed from
the methods and the vocabularies used. `limits_applied` lists every limit that shaped the result without
refusing it: a KeyBERT document chunked, a chunk over the encoder's window, vocabulary terms left out of
the prompt (`vocab_prompt_budget_tokens`, `trimmed`), lines whose reply was cut (`llm_max_new_tokens`,
`skipped`), a document given up after too many failed lines (`llm_max_consecutive_errors`, `stopped`).

## How it works

The record's lines are joined per page and per document (`Trash`, `Garbage`, `Inverted` and `Empty` lines
left out). One call runs the chosen method over the document and, with `per_page`, over each page —
KeyBERT in one batch — in a worker thread, inside one of `MAX_CONCURRENT_REQUESTS` slots. The batch CLI
(`keywords.py`) shares the three method implementations: it reads CoNLL-U or TEITOK files instead of a
record. The KeyBERT model is loaded at startup when it is the default, so the first request does not pay
for it; a model that does not load does not stop the service, and the first request that needs it answers
500 with the cause.

The controlled kind is built once at startup when `LLM_BACKEND` and its model are configured: the
vocabulary is loaded, the prompt rendered and the JSON schema built, and the backend's chat function
bound (`llm_client_shared.py` with `openrouter_client.py` or `ollama_client.py`, the clients the batch
runs use). A request then makes one call per qualifying line, in the same slot as its statistical kind,
each bounded by `LLM_TIMEOUT` and retried `LLM_MAX_RETRIES` times; a long record takes as many calls as it
has lines. The image carries no model: the weights stay in the inference service.

## Configuration (environment)

| Variable              | Default                                | Meaning                                                                                                                     |
|-----------------------|----------------------------------------|-----------------------------------------------------------------------------------------------------------------------------|
| `PORT`                | `8000`                                 | port the service **binds**, and the one `service/healthcheck.py` probes (issues #55, #58)                                   |
| `HOST`                | `0.0.0.0`                              | bind address (issue #58). ⚠️ see the warning below                                                                          |
| `GRACEFUL_SHUTDOWN_S` | `20`                                   | seconds uvicorn waits for in-flight requests (issue #55)                                                                    |
| `RELOAD`              | `false`                                | filesystem auto-reload — development only                                                                                   |
| `LOG_LEVEL`           | `INFO`                                 | root logger level for the `python -m service.api` start path (issue #61)                                                    |
| `ALLOWED_ORIGINS`     | `*`                                    | CORS origins                                                                                                                |
| `DEFAULT_KW_METHOD`   | `keybert`                              | default statistical method                                                                                                  |
| `LLM_BACKEND`         | `openrouter`                           | the controlled kind's backend: `openrouter` or `ollama`                                                                     |
| `LLM_CONFIG`          | `llm_config.txt`                       | config file for what the environment does not set: the `PROMPT_*` flags, `VOCAB_PATH`, `EMIT_CATEGORY_IDS`, the line filter |
| `OPENROUTER_API_KEY`  | —                                      | **secret**, required for the controlled kind with `openrouter`                                                              |
| `OPENROUTER_MODEL`    | —                                      | required with it — an OpenRouter model id                                                                                   |
| `OLLAMA_HOST`         | `http://localhost:11434`               | the Ollama server (compose supplies the host's: `http://host.docker.internal:11434`)                                        |
| `OLLAMA_MODEL`        | —                                      | required for the controlled kind with `ollama` — an Ollama model tag                                                        |
| `VOCAB_PATH`          | `data_samples/vocab/union_nested.json` | the built vocabulary (and, beside it, the flat files that resolve `entities[].pid`)                                         |

Every limit — `MAX_UPLOAD_MB`, `MAX_DOCUMENT_WORDS`, `MAX_KEYWORDS`, `MAX_CONCURRENT_REQUESTS`, the
KeyBERT chunk settings and the LLM settings — is listed under [Limits](#limits).

`PORT` and `HOST` are read by `service/api.py`'s `__main__` block, which is what the `api` image's
`ENTRYPOINT` (`python -m service.api`) runs.

> ⚠️ `HOST=127.0.0.1` yields a container that reports **healthy** and serves nobody:
> `service/healthcheck.py` always probes loopback by design and never reads `HOST`, so a loopback bind
> passes every probe while being unreachable from outside the container.

## Limits

Every limit is an environment setting (atrium-project#53, factor III), declared in `tool_limits.py`
and reported with its current value by `GET /info` (`limits`; `limits_meta` says which variable sets it
and whether the value came from the environment, `llm_config.txt` or the default). A malformed value stops
the service at startup, naming the variable. An input over a limit is refused with the
[harmonised error](#errors); a limit that shapes a result without refusing it is named in
`limits_applied`. `tests/test_limits_contract.py` checks this table against `tool_limits.py` and
`.env.example`.

| Key (`/info`)                | Variable                                                            | Default | Unit     | Over the limit                                                                                                                                                                                                                                |
|------------------------------|---------------------------------------------------------------------|---------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `max_upload_mb`              | `MAX_UPLOAD_MB`                                                     | 10      | MB       | 413 `limit_exceeded` — the uploaded record, and the whole `/extract_keywords_text` body                                                                                                                                                       |
| `max_document_words`         | `MAX_DOCUMENT_WORDS`                                                | 200000  | words    | 413 `limit_exceeded` — the record's lines or the text                                                                                                                                                                                         |
| `max_keywords`               | `MAX_KEYWORDS`                                                      | 100     | keywords | 422 `limit_exceeded` — `num_keywords` over it                                                                                                                                                                                                 |
| `max_concurrent_requests`    | `MAX_CONCURRENT_REQUESTS`                                           | 2       | requests | 429 `busy` with `Retry-After: 15`                                                                                                                                                                                                             |
| `keybert_chunk_words`        | `KEYBERT_CHUNK_WORDS`                                               | 400     | words    | a longer document is embedded in overlapping chunks and its keywords merged — `split` note                                                                                                                                                    |
| `keybert_chunk_overlap`      | `KEYBERT_CHUNK_OVERLAP`                                             | 50      | words    | the words two consecutive KeyBERT chunks share                                                                                                                                                                                                |
| `keybert_max_seq_tokens`     | — (derived from the KeyBERT model, `kw_config.txt` `KEYBERT_MODEL`) | —       | tokens   | a longer chunk is embedded from its start — `trimmed` note; 128 for the default model, `null` until it is loaded                                                                                                                              |
| `llm_context_window`         | `LLM_CONTEXT_WINDOW`                                                | 128000  | tokens   | sizes the vocabulary prompt: terms that do not fit are left out — standing `trimmed` note. The default depends on the backend — 128000 `openrouter`, 32000 `ollama` — after `CONTEXT_WINDOW` in `llm_config.txt`; sent to Ollama as `num_ctx` |
| `llm_max_new_tokens`         | `LLM_MAX_NEW_TOKENS`                                                | 2048    | tokens   | a reply cut at it is never used: the line gets no result — `skipped` note. OpenRouter `max_tokens`, Ollama `num_predict`                                                                                                                      |
| `llm_timeout`                | `LLM_TIMEOUT`                                                       | 300     | s        | the call is retried (`LLM_MAX_RETRIES`)                                                                                                                                                                                                       |
| `llm_max_retries`            | `LLM_MAX_RETRIES`                                                   | 3       | attempts | only a timeout, a connection error, HTTP 429 or 5xx is retried; once they run out the line is an error                                                                                                                                        |
| `llm_max_consecutive_errors` | `LLM_MAX_CONSECUTIVE_ERRORS`                                        | 10      | errors   | the document is given up — `stopped` note (the lines before keep their results); every line failing is 502 for `kind=controlled`, `failed` in `kinds` for `kind=both`                                                                         |
| `vocab_prompt_budget_tokens` | — (derived: `LLM_CONTEXT_WINDOW` − `LLM_MAX_NEW_TOKENS` − 512)      | —       | tokens   | vocabulary terms past it are left out of the prompt — standing `trimmed` note, and a warning at startup                                                                                                                                       |

`KEYBERT_CHUNK_WORDS` stays 400 until an evaluation says otherwise: with the default encoder's 128-token
window, most 400-word chunks are embedded from their start, and `limits_applied` says how many. Token
counts of the controlled kind are estimates at 4 characters per token
(`llm_client_shared.approx_token_count`): the whole vocabulary prompt is about 40000, so it fits the
OpenRouter default whole and is cut at Ollama's. There is no per-request time limit: the work runs in a
thread that cannot be stopped, and each LLM call has its own (`LLM_TIMEOUT`).

## Errors

Every error has one JSON body (hub `docs/agent_skill_strategy.md` §4.4, atrium-project#32 item 2):
`{"status": <int>, "reason": <code or null>, "detail": "<text>"}`. `detail` is always a string. A limit
refusal adds `limit` (`{key, env, value, observed, unit}`); a request validation error adds FastAPI's list
of problems as `errors`.

| Status | `reason`         | When                                                                                                                                                    |
|--------|------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| 413    | `limit_exceeded` | over `MAX_UPLOAD_MB` or `MAX_DOCUMENT_WORDS`                                                                                                            |
| 422    | `invalid_record` | the `document_json` sent cannot be opened (not UTF-8 JSON, not an object, a newer `schema_version` major)                                               |
| 422    | `limit_exceeded` | `num_keywords` over `MAX_KEYWORDS`                                                                                                                      |
| 422    | `null`           | a record or text with nothing to read, the legacy method without lemmas, a value outside the spec's enums or bounds                                     |
| 429    | `busy`           | every extraction slot taken; retry after `Retry-After` seconds                                                                                          |
| 500    | `null`           | a method's package is missing or the KeyBERT model could not be loaded, or the record this service built does not validate — the detail names the cause |
| 501    | `null`           | `kind=controlled` alone in a deployment without a working LLM backend — the detail says what is missing (`/info` `controlled.detail`)                   |
| 502    | `null`           | `kind=controlled` alone, and every call to the LLM backend failed — the detail carries the first failure                                                |

## Shutdown behavior (issue #55)

The `api` image declares `HEALTHCHECK` (shallow `GET /health`, via the vendored `service/healthcheck.py`)
and `STOPSIGNAL SIGTERM`, and sets `ENV GRACEFUL_SHUTDOWN_S=20`, which `service/api.py`'s `__main__` block
passes to uvicorn as `timeout_graceful_shutdown`.

On `SIGTERM` the service flips `GET /ready` to **503** immediately, so an orchestrator stops routing new
requests here (`GET /health` deliberately stays 200 — a liveness probe failing mid-shutdown would get the
container killed before it finished draining), then lets uvicorn drain in-flight HTTP requests (up to 20s).
Every request is synchronous, so there is no background work to wait for; a controlled-kind request over a
long record can outlast the drain, so give such a deployment a longer `GRACEFUL_SHUTDOWN_S` and grace
period. The container exits **143** (128 + SIGTERM) after a clean shutdown, not 0 — uvicorn re-raises the
captured signal on purpose so a supervisor sees the real cause. That is a normal stop, not a crash. See
`docs/k8s_deployment.md` in the hub for the full grace-period budget and the Kubernetes probe contract.

## OpenAPI (the typed contract)

The service's OpenAPI document is committed as [`service/openapi.json`](openapi.json) and attached to every
release as `openapi.json` with its `openapi.json.sha256` (atrium-project#32 round 2). It is what a client is
generated from: every request and response field is typed (the response as `ExtractResponse`, the returned
record as `AtriumDocument`), every error response is the body above, the registered `reason` codes are
listed in `x-atrium-reason-codes`, and `paradata` is typed as the `CreateAction`. `GET /info` reports
`openapi_sha256`, the digest of the spec the running image serves — equal to the release's
`openapi.json.sha256` for an image built from that tag.

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
is stubbed), `tests/test_service_document_json.py` drives the controlled kind against a stubbed LLM backend
(the record returned, the ids, the outcomes, 501 and 502), and `tests/test_api_contract.py` holds every
response, refusals included, to the schema the published spec declares for it.
