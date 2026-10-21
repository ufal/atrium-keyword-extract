---
name: atrium-keyword-extract
description: Extracts keywords from Czech archival text, as an ATRIUM document record or plain text, of two kinds kept apart - statistical keywords of the document and of each page (KeyBERT, YAKE or a lemma count, each with its score and rank), and, when the server has a language-model backend, per line the AMČR/TEATER vocabulary term that describes it with the Czech and English keywords found in it. Use this skill after OCR quality filtering and NLP enrichment, to index or summarise archaeological documents by their terms.
---

# ATRIUM keyword-extract Skill 🗝️

This skill gives agents access to the **ATRIUM keyword-extract** service, the "keywords" stage of the ATRIUM
pipeline. It follows a **server-client** design: a FastAPI server (in `service/`) runs the keyword methods and
the vocabulary-guided language-model calls, and a zero-dependency client script (`scripts/atrium_keywords.py`) is
the only thing the agent calls directly.

## Operational Requirements ⚙️

- **Server**: a running instance is required. Default `http://localhost:8000`; override with `--base-url` or the
  `ATRIUM_KW_URL` environment variable. `ATRIUM_KW_URL` is *inbound*, where the client finds this service. It is
  unrelated to the server's *outbound* `LLM_BACKEND` settings, which say where the controlled kind finds its
  language model.
- **Client dependencies**: none - Python 3 standard library only.
- **Server dependencies**: Docker (recommended, compose `api` profile; `--gpu` adds the GPU overlay for KeyBERT)
  or a Python venv with `requirements.txt` and `service/requirements.txt`.
- **The two kinds need different things.** The statistical kind needs nothing beyond the server. The controlled
  kind needs an LLM backend (`LLM_BACKEND=openrouter` with `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`, or
  `LLM_BACKEND=ollama` with `OLLAMA_HOST` and `OLLAMA_MODEL`), and the AMČR/TEATER vocabulary, which the
  **published image** carries and this branch does not. Without either, `--kind both` returns the statistical
  keywords and reports the controlled kind as `skipped`; `--info` says why (`controlled.detail`).
- **First launch**: the KeyBERT model (`paraphrase-multilingual-MiniLM-L12-v2`, about 500 MB) is downloaded into
  the Hugging Face cache. Warmup takes minutes, not seconds; do **not** treat a slow first start as failure.
  YAKE needs no model.
- **Limits**: 10 MB per record or text, 200,000 words per document, at most 100 keywords per list, 2 requests at
  once (HTTP 429 with `Retry-After` when busy). The controlled kind makes one language-model call per line, so a
  long record takes minutes.
- **Readiness**: `GET /health` is liveness (stays 200 while draining); `GET /ready` is the readiness probe, 503
  until the startup warm-up has finished and while shutting down.

## Keyword kinds and methods 🔑

| Kind          | What comes back                                                                                                                        | Needs                             |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------|
| `statistical` | the keywords of the document and of each page, each with its `method`, `score` and `rank`; written to the record's `keywords` block    | nothing                           |
| `controlled`  | per line: `teater_category` (a vocabulary term), its AMČR/TEATER ids, the Czech and English keywords in the line, a `confidence_score` | an LLM backend and the vocabulary |

| `--method` | What it is                                                      | Score                                       |
|------------|-----------------------------------------------------------------|---------------------------------------------|
| `keybert`  | embedding-based; the best quality; uses a GPU when there is one | cosine similarity, 0 to 1                   |
| `yake`     | statistical, CPU only, no model (AGPL-3.0)                      | inverted YAKE score, 0 to 1                 |
| `legacy`   | counts the lemmas of nouns, proper nouns and adjectives         | a count; needs nlp-enrich's `lines[].lemma` |

Scores mean different things per method: compare them only within one method and one list. Lines marked `Trash`,
`Garbage`, `Inverted` or `Empty` by ocr-postprocess or digital-convert are left out.

## Workflows 🪄

### 1. Ensure the server is running

```bash
bash scripts/server.sh          # Docker Compose api profile (or the local fallback)
bash scripts/server.sh --gpu    # Docker with the GPU overlay
bash scripts/server.sh --local  # force a local server in venv-kw (no Docker; statistical kind only)
```

Idempotent: exits at once if `GET /ready` already answers 200; otherwise waits for the first-run download.

### 2. Extract keywords

```bash
# A record (after digital-convert, ocr-postprocess or nlp-enrich): per document and per page
python3 scripts/atrium_keywords.py small_data_samples/report.document.json

# The same with YAKE, three per list, and the record with its keywords block written out
python3 scripts/atrium_keywords.py small_data_samples/report.document.json --method yake --num-keywords 3 --out-dir out/

# A plain text, statistical only, as CSV
python3 scripts/atrium_keywords.py small_data_samples/report.txt --kind statistical --format csv

# Text from stdin, with its document id
cat notes.txt | python3 scripts/atrium_keywords.py - --doc-id CTX000000042

# The controlled kind (the server needs an LLM backend), document keywords only
python3 scripts/atrium_keywords.py record.document.json --kind controlled --no-per-page --format json

# The legacy method on a record that nlp-enrich has lemmatised
python3 scripts/atrium_keywords.py enriched.document.json --method legacy

# Discover capabilities: methods, the default, the kinds available, the controlled kind's model and vocabulary
python3 scripts/atrium_keywords.py --info
```

### 3. Interpret the output

- **Table and CSV**: FILE, KIND, WHERE (`document`, `page N`, or `page N line M`), TERM, SCORE, DETAIL. For a
  statistical keyword, DETAIL is its method and rank. For a controlled line, TERM is the vocabulary term and
  DETAIL its Czech / English keywords. The table cuts DETAIL to 60 characters; CSV and JSON keep it whole.
- **JSON** (`--format json`): the server's whole answer per document, keyed by `doc_id`: `keywords`, `pages`,
  `kinds`, `enrichment`, `controlled` (backend, model, outcome, counts), `document_json`, `paradata` and
  `limits_applied`.
- **Files** (`--out-dir`): `<doc_id>.document.json`, the record with keyword-extract's blocks written and every
  other block as it came.
- One summary line per document goes to stderr (with any kind that did not run, and why); stdout stays clean for
  CSV and JSON.

## Agent Guidelines 🤖

1. **Pick the method for the job.** `keybert` (usually the server's default) for quality; `yake` when no model can
   be loaded; `legacy` only on records with lemmas. Name the method when you report keywords.
2. **Keep the two kinds apart.** Statistical keywords are extracted phrases; controlled terms come from the
   vocabulary. `confidence_score` is not calibrated (most lines get 0.95 or 0.85): do not rank or filter on it,
   and present the controlled terms as suggestions, not as checked results.
3. Prefer `--format json` when the result feeds further processing; pass the record on with `--out-dir`.
4. For full request and response schemas, fetch `GET /openapi.json` from the running server (Swagger UI at
   `/docs`); `service/README.md` is the runbook.
5. Exit code `2` (unreachable): start the server (`bash scripts/server.sh`) and retry once. Exit code `3` (server
   error): the client has already retried a 503 or 504, and a 502 that is not final, three times. A 502 from the
   service itself (every language-model call failed) is not retried; read the hint, check `GET /health?deep=true`
   and the server log, and do not loop.
6. **Busy (429):** wait for `Retry-After` and send again; do not start parallel requests against one server.
7. **501 on `--kind controlled`:** the server has no working LLM backend. Say so, and offer the statistical
   keywords (`--kind statistical`) instead.
8. **Size:** inputs over 10 MB or 200,000 words are refused. Split by page or section, and tell the user you did.
9. Do not bypass the API by importing the keyword code directly. Every call returns its provenance as `paradata`,
   a Process Run Crate `CreateAction`.

## Acknowledgements & Citations 🙏

Developed within the [ATRIUM](https://atrium-research.eu/) project at ÚFAL, Charles University, with the AMČR and
TEATER vocabularies of the Archaeological Map of the Czech Republic. If you use this service for research, cite
the repository's `CITATION.cff`.
