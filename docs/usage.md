# Using keyword-extract

How to install keyword-extract, run the service, run the batch command line for the statistical kind, run the
controlled kind from the command line, and use the Docker images. What each kind does:
[how it works](how-it-works.md).

**On this page:**

- [Set it up](#set-it-up)
- [Run the service](#run-the-service)
- [Extract keywords from a folder](#extract-keywords-from-a-folder), and [which setting wins](#which-setting-wins)
- [Run the controlled kind from the command line](#run-the-controlled-kind-from-the-command-line)
- [Run the Docker images](#run-the-docker-images)
- [The command line and the service](#the-command-line-and-the-service): where they differ

## Set it up

```bash
git clone https://github.com/ufal/atrium-keyword-extract.git
cd atrium-keyword-extract
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt                      # KeyBERT, YAKE, the shared contract
pip install -r service/requirements.txt              # + the service (fastapi, uvicorn)
```

KeyBERT downloads its embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) from the Hugging Face Hub on first
use; set `HF_HOME` to keep the cache. A GPU is used when `torch` finds one. The environment of the service is
[`.env.example`](../.env.example).

## Run the service

[`service/README.md`](../service/README.md) is the reference: the endpoints, the options, the response, the limits,
the errors and the OpenAPI contract. In short:

```bash
python -m service.api                  # PORT / HOST; default 0.0.0.0:8000; leave it running
```

Then, from another terminal, the statistical keywords of a record nlp-enrich wrote:

```bash
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@<doc>.document.json;type=application/json" \
  -F kind=statistical -F method=keybert -F num_keywords=10
```

Both kinds need the controlled one's backend configured when the service starts:

```bash
OPENROUTER_API_KEY=sk-... OPENROUTER_MODEL=openai/gpt-4o-mini python -m service.api   # leave it running
```

```bash
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@<doc>.document.json;type=application/json" -F kind=both
```

## Extract keywords from a folder

> [!NOTE]
> `keywords.py` is the command-line form of the statistical kind, for a whole collection at once. It reads what the
> [service](#run-the-service) reads, with the same code (`kw_inputs.py`): the CoNLL-U and TEITOK files
> [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich) writes, ATRIUM records (`*.document.json`), line tables
> (`.csv`) and plain text (`.txt`). It writes CSV tables and, when asked, the records. Both run the same three methods.

Run `keywords.py` on a directory of such files; other files are passed over.

### Which setting wins

`keywords.py` takes its settings from three places, from the highest priority to the lowest:

1. **Command-line flags** (e.g., `-m yake`, `-w 3`) always override everything else.
2. **`kw_config.txt`** (the `[DEFAULTS]` section) is read automatically if placed next to the script.
3. **Hardcoded fallbacks** are used if no config file or flags are provided.

So once your settings are in `kw_config.txt`, you can simply run:

```bash
python3 keywords.py
```

### Choose a method

| Flag value            | Method                                                   | Dependencies                                | Score semantics                       | Best for                                  |
|-----------------------|----------------------------------------------------------|---------------------------------------------|---------------------------------------|-------------------------------------------|
| `legacy`              | NOUN/PROPN/ADJ lemma frequency, named after KER          | none (stdlib only)                          | raw occurrence count                  | reproducing original ATRIUM results       |
| `yake`                | YAKE — unsupervised statistical, CPU-only (**AGPL-3.0**) | `pip install yake`                          | normalised inverse YAKE score, [0, 1] | fast CPU runs, no model download          |
| `keybert` *(default)* | KeyBERT — embedding-based, GPU-accelerated               | `pip install keybert sentence-transformers` | cosine similarity, [0, 1]             | highest semantic quality, GPU recommended |

You can override any `kw_config.txt` setting via the command line:

```bash
python3 keywords.py -i <input_dir> -m <method> -l <lang> -w <integer> \
                    -n <integer> -d <output_dir> -o <output_file>.csv
```

All available flags:

| Flag | Long form                 | Default in `kw_config.txt`                     | Description                                                                               |
|------|---------------------------|------------------------------------------------|-------------------------------------------------------------------------------------------|
| `-i` | `--input_dir`             | `data_samples/UDP`                             | The folder to read: CoNLL-U, TEITOK, records, line tables, `.txt`                         |
| `-m` | `--method`                | `keybert`                                      | Backend: `legacy`, `yake`, or `keybert`                                                   |
| `-l` | `--lang`                  | `cs`                                           | Language code for YAKE stopwords (`cs`, `en`, `de`, …). Ignored by `legacy` and `keybert` |
| `-w` | `--max_words`             | `3`                                            | Maximum words per keyword phrase (n-gram upper bound)                                     |
| `-n` | `--num_keywords`          | `20`                                           | Number of keywords to extract per document                                                |
| `-d` | `--per_doc_out_dir`       | `data_samples/KW_PER_DOC_{METHOD}`             | Output directory for per-document CSV files (`{METHOD}`: `L`, `Y` or `KB`)                |
| `-o` | `--output_file`           | `data_samples/keywords_summary_{method}.csv`   | Master keywords CSV (`{method}`: `l`, `y` or `kb`)                                        |
|      | `--per-page`              | *(off)*                                        | Also extract each page's keywords, for inputs with pages (the service's `per_page`)       |
| `-p` | `--per_page_out_dir`      | `data_samples/KW_PER_PAGE_{METHOD}`            | Output directory for the per-page CSV files (`page`, `keyword`, `score`)                  |
|      | `--document-json-out-dir` | *(none)*                                       | Write each document's record with its `keywords` block here, as the service writes it     |
|      | `--document-json-dir`     | *(none)*                                       | Baselines `<doc_id>.document.json` for inputs that are not records themselves             |
|      | `--paradata-dir`          | `PARADATA_DIR`, else `<input_dir>/../paradata` | Where the run's paradata file goes                                                        |
|      | `--keybert-model`         | `paraphrase-multilingual-MiniLM-L12-v2`        | Sentence-Transformer model name (KeyBERT only)                                            |
|      | `--no-mmr`                | *(False)*                                      | Disable Maximal Marginal Relevance diversification (KeyBERT only)                         |
|      | `--diversity`             | `0.5`                                          | MMR diversity parameter, 0 = max relevance → 1 = max diversity (KeyBERT only)             |
|      | `--batch_size`            | `16`                                           | Documents per KeyBERT batch (KeyBERT only)                                                |
|      | `--workers`               | `0` *(Auto / CPU count)*                       | Parallel worker processes. Auto-forced to 1 for KeyBERT + GPU                             |

Examples:

**YAKE** — Czech, up to 3-word phrases, 20 keywords per document

```bash
python3 keywords.py -i OUTPUT_DIR/UDP -m yake -l cs -w 3 -n 20 \
        -o keywords_summary.csv -d KW_PER_DOC
```

**KeyBERT** — multilingual model, GPU-accelerated (the default)

```bash
python3 keywords.py -i OUTPUT_DIR/UDP -m keybert -w 3 -n 20 \
        --keybert-model paraphrase-multilingual-MiniLM-L12-v2 \
        -o keywords_summary.csv -d KW_PER_DOC
```

**Legacy (KER)** — (English/Czech) the original ATRIUM lemma-frequency approach, no extra dependencies. It is named
after ÚFAL's KER but, unlike KER, does not weight lemmas by IDF ([licences](reference/licences.md#licences))

```bash
python3 keywords.py -i OUTPUT_DIR/UDP -m legacy -n 20 \
        -o keywords_summary.csv -d KW_PER_DOC
```

**The record** — per-page keywords into the records, as the service writes them:

```bash
python3 keywords.py -i records/ -m yake --per-page --document-json-out-dir records_kw/
```

> [!WARNING]
> For **KeyBERT with a GPU**, the script automatically forces `--workers 1` to
> prevent competing CUDA context initialisation across subprocesses.  On CPU,
> any worker count is safe.

## Run the controlled kind from the command line

The three paths and what they read and write are in [how it works](how-it-works.md#the-controlled-kind-and-the-vocabulary).

```bash
pip install -r requirements_remote.txt
export OPENROUTER_API_KEY=sk-...
python openrouter_client.py --input <doc>.document.json --model openai/gpt-4o-mini \
  --document-json-out <doc>.kw.document.json
python ollama_client.py --input data_samples/DOC_LINE_CATEG --model qwen2.5:14b
```

The research run on a GPU node:

```bash
pip install -r requirements.txt -r requirements_llm.txt   # vLLM brings its own torch pin
$EDITOR llm_config.txt     # MODEL_KEY; INPUT_DIR (line CSVs or *.teitok.xml), OUTPUT_DIR, PARADATA_DIR
python llm_run.py --download   # where huggingface.co is reachable: MODEL_KEY into the HF cache
python llm_run.py          # or: python llm_run.py <another config>
```

A GPU node without internet access (`HF_HUB_OFFLINE=1`) loads a model only from the Hugging Face cache. Fetch it first
on a machine that has access, into the same `HF_HOME`; `--download KEY ...` takes several keys. The download fetches
what a run reads (configs, tokenizer, weights; not README or LICENSE) and skips files already cached, for which
huggingface_hub then reports 0 B. It ends with what the cache holds. A run whose model files are not all cached stops
before loading and names what is missing.

What the research run does:

- It writes `<OUTPUT_DIR>_<model>/<doc_id>_enriched.json` per document, and `<doc_id>_enriched.abort.json` after ten
  consecutive errors.
- It skips a document whose output already exists, so a stopped job resumes. To redo an aborted document, delete its
  two files.
- It writes a paradata record that names the vocabulary build and the SHA-512 of the prompt it used
  (`prompt.sha512`). It names the files and folders of `llm_config.txt` and its output folder, never their paths.

The whole prompt is about 58k tokens. A model served with a smaller window sees only a prefix of the vocabulary, and
the paradata record it as `sampled`, with how many terms were left out. A line whose prompt is still over the window
is sent with fewer neighbouring lines as context (`llm_context_window`, `split`); a line that does not fit even alone
stops the run. The large vLLM models do this at their default `MAX_MODEL_LEN` of 16384.

To keep the run fast and within memory:

- vLLM computes the prompt's shared part once and reuses it (prefix caching). So does `BACKEND=transformers` with
  `REUSE_PROMPT_CACHE=true`; without it, every line re-reads the whole prompt.
- `PREFILL_CHUNK_SIZE` keeps the transformers prefill within a 24 GB card.
- Hybrid models (Qwen3.5, Qwen3.6) need `flash-linear-attention`, which `requirements_llm.txt` lists. Without it their
  linear-attention layers run on a reference kernel that is far slower and does not fit.

The `llm` image carries no sample inputs, and whatever it writes outside `/data` goes with the container. Point
`INPUT_DIR`, `OUTPUT_DIR` and `PARADATA_DIR` under `/data` in the `llm_config.txt` the compose file mounts.

## Run the Docker images

The Dockerfile builds three images, one per target:

| Target | Image                                     | What it is                                                          |
|--------|-------------------------------------------|---------------------------------------------------------------------|
| `api`  | `ghcr.io/ufal/atrium-keyword-extract-api` | the service, both kinds — **the production image** (no LLM weights) |
| `base` | `ghcr.io/ufal/atrium-keyword-extract`     | the batch CLI (`keywords.py`)                                       |
| `llm`  | `ghcr.io/ufal/atrium-keyword-extract-llm` | the research LLM batch run, GPU                                     |

The batch image passes its arguments to `keywords.py` (`docker run IMAGE -i /data/UDP -m yake`). Its entry point,
the hub-canonical `container_entrypoint.py`, names `keywords.py` by its absolute path: a first argument that names a
shell or Python runs that program instead (`docker run IMAGE /bin/sh job.sh`), so a job script can run in the image.
Only those interpreters run, so an input folder that happens to be called `sh`
is still a folder; the `llm` image does the same for `llm_run.py`.

```bash
docker compose --profile api up                       # the service on :8000
docker compose run --rm kw -i /data/UDP -m yake       # the batch CLI
docker compose -f docker-compose.yaml -f docker-compose.gpu.yaml --profile llm run --rm kw-llm
```

## The command line and the service

`keywords.py` and `POST /extract_keywords` read every input through [kw_inputs.py](../kw_inputs.py). They run the same
methods (`keywords.extract_from_texts`) and write the record's `keywords` block through the same writer
(`llm_client_shared.write_document_record`). So the same input gives the same keywords, per document and per page,
and the same components in the paradata; [tests/test_cli_service_parity.py](../tests/test_cli_service_parity.py)
checks this. Both take their defaults from `kw_config.txt`: `METHOD` and `NUM_KEYWORDS` (the service's
`DEFAULT_KW_METHOD` setting overrides its method), and the KeyBERT model, `MAX_WORDS`, MMR and diversity. Where they
differ:

| What                         | Command line                                                       | Service                                                           | Why they differ                                              |
|------------------------------|--------------------------------------------------------------------|-------------------------------------------------------------------|--------------------------------------------------------------|
| How much per run             | a folder                                                           | one document per request                                          | the service is stateless                                     |
| The record                   | `*.document.json` in the folder; `--document-json-out-dir`         | `document_json`                                                   |                                                              |
| CoNLL-U, TEITOK, CSV, `.txt` | files in the folder                                                | the `file` part (with `document_json`, the record gets the block) |                                                              |
| Lines as JSON                | none; write them to a `.txt`                                       | `POST /extract_keywords_text`                                     | an HTTP convenience                                          |
| Per page                     | `--per-page` (off by default)                                      | `per_page` (on by default)                                        | the CSV outputs of a batch run stay as they were             |
| Pages of a CoNLL-U file      | none                                                               | none                                                              | CoNLL-U carries no pages: send the record or the TEITOK file |
| KER without lemmas           | an empty row                                                       | 422                                                               | a batch run goes on; a call is told why it got nothing       |
| A document with no text      | an empty row                                                       | 422                                                               | the same                                                     |
| Language                     | `-l`: any language YAKE has stop words for                         | `lang`: `cs` only                                                 | the service takes Czech only                                 |
| KeyBERT and YAKE settings    | `-w`, `--keybert-model`, `--no-mmr`, `--diversity`, `--batch_size` | `kw_config.txt` in the image                                      | deployment settings, not request fields                      |
| Limits                       | none                                                               | `MAX_DOCUMENT_WORDS` (413), `MAX_KEYWORDS` (422), `MAX_UPLOAD_MB` | the service bounds what one request may cost                 |
| The controlled kind          | `openrouter_client.py`, `ollama_client.py`; `llm_run.py` on a GPU  | `kind=controlled\|both`                                           | the LLM backend is configured per deployment in the service  |
| Outputs                      | CSV tables, the records                                            | JSON, with the record                                             |                                                              |
| Paradata                     | a file in `--paradata-dir` (program `keyword-extract`)             | the response's `paradata`, a `CreateAction`                       | the service keeps no files                                   |

KER (`legacy`) counts lemmas, and where they come from depends on the input. CoNLL-U and TEITOK give every noun's,
proper noun's and adjective's lemma. A record gives one lemma per line at most: `lines[].lemma`, which nlp-enrich
sets to the lemma of the line's head word, counted when its `upos` is a noun, a proper noun or an adjective. So KER
counts fewer lemmas in a record than in the CoNLL-U or TEITOK file of the same document. A CSV or a `.txt` gives
none. The pages' lemmas come from a record only.
