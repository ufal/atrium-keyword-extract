<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11-blue.svg" title="Python Version"></a>
  <a href="https://github.com/MaartenGr/KeyBERT"><img src="https://img.shields.io/badge/dep-KeyBERT-lightgrey.svg" title="KeyBERT"></a>
  <a href="https://github.com/LIAAD/yake"><img src="https://img.shields.io/badge/dep-YAKE%20(AGPL--3.0)-lightgrey.svg" title="YAKE (AGPL-3.0)"></a>
  <a href="https://github.com/ufal/ker"><img src="https://img.shields.io/badge/dep-KER-lightgrey.svg" title="KER Keyword Extraction"></a>
  <a href="https://opensource.org/license/mit/"><img src="https://img.shields.io/github/license/ufal/atrium-keyword-extract" title="MIT License"></a>
  <a href="https://atrium-research.eu/"><img src="https://img.shields.io/badge/funded%20by-ATRIUM-8A2BE2.svg" title="ATRIUM Project"></a>
</p>

---

# 📦 Keyword extraction — statistical and vocabulary-controlled

Keywords of archival documents, **of two kinds kept apart** — and every keyword says which method produced it,
with its score and rank:

* **statistical** keywords — **KeyBERT** (the default), **YAKE** (selectable) and the legacy **KER**, from the
  document or from each of its pages;
* **controlled** keywords — per line, the term of the **AMČR** and **TEATER** vocabularies a language model
  chooses for it (with the AMČR/TEATER records behind the term), the Czech and English keywords found in the line,
  and the page and line it came from, plus entity links to AMČR and AAT.

One service, `POST /extract_keywords`, takes the ATRIUM document record after nlp-enrich and answers with the
statistical keywords of the document and of its pages, and the record with its controlled keywords written in
(the `enrichment` block). This repository is where both kinds live: it was assembled on
1 October 2026 from the keyword extraction of [atrium-nlp-enrich](https://github.com/ufal/atrium-nlp-enrich)
(`keywords.py`) and of `atrium-llm-enrich` (the LLM engine and the vocabulary code), after the meeting of
30 September (atrium-keyword-extract#1; atrium-project#72). nlp-enrich keeps only the LINDAT calls (UDPipe,
NameTag) and what is built from them.

> [!NOTE]
> **State of this branch.** Both kinds run in the service. The controlled kind calls a language model in an
> inference service — OpenRouter, or a local Ollama — configured by `LLM_BACKEND`; a deployment without one answers
> `kind=controlled` with 501 and reports it `skipped` under `kind=both`. Its quality is not evaluated yet: the
> evaluation rubric (D1) of atrium-keyword-extract#2 is open, so treat its output as research output. Since
> v1.2.0-beta the statistical keywords are also written into the record, as its `keywords` block (atrium-project#73).

---

## 📖 Table of Contents

- [The service](#the-service)
- [Setup](#setup)
- [The batch CLI: `keywords.py`](#the-batch-cli-keywordspy)
- [The controlled kind and the vocabulary](#the-controlled-kind-and-the-vocabulary)
- [Licences](#licences)
- [Docker](#docker)
- [Contributing and contacts](#contributing-and-contacts)

---

## The service

[`service/README.md`](service/README.md) is the reference: the endpoints, the options, the response, the limits,
the errors and the OpenAPI contract. In short:

```bash
python -m service.api                  # PORT / HOST; default 0.0.0.0:8000

curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@CTX000000001.document.json;type=application/json" \
  -F kind=statistical -F method=keybert -F num_keywords=10

# both kinds, with the controlled one's backend configured
OPENROUTER_API_KEY=sk-... OPENROUTER_MODEL=openai/gpt-4o-mini python -m service.api
curl -s -X POST localhost:8000/extract_keywords \
  -F "document_json=@CTX000000001.document.json;type=application/json" -F kind=both
```

The record is read: its `lines[].text` per page (lines labelled `Trash`, `Garbage`, `Inverted` or `Empty` are left out), and for the
legacy method its `lines[].lemma` and `lines[].upos`, which [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich)
writes. In the pipeline it comes after nlp-enrich (and after digital-convert on the born-digital route), and its
keywords can be projected into the TEITOK header by nlp-enrich's `/project_record`.

| Method    | Needs                                   | Score                                     |
|-----------|-----------------------------------------|-------------------------------------------|
| `keybert` | the embedding model, a GPU if available | cosine similarity, [0, 1]                 |
| `yake`    | nothing (CPU)                           | inverted YAKE score, normalised to [0, 1] |
| `legacy`  | `lines[].lemma` / `lines[].upos`        | an occurrence count                       |

Scores are compared only within one method.

## Setup

```bash
git clone https://github.com/ufal/atrium-keyword-extract.git
cd atrium-keyword-extract
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt                      # KeyBERT, YAKE, the shared contract
pip install -r service/requirements.txt              # + the service (fastapi, uvicorn)
```

KeyBERT downloads its embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) from the Hugging Face Hub on first
use; set `HF_HOME` to keep the cache. A GPU is used when `torch` finds one. The environment of the service is
[`.env.example`](.env.example).

---

## The batch CLI: `keywords.py`

> [!NOTE]
> The command-line form of the statistical kind, for a whole collection at once. It reads the CoNLL-U
> files [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich) writes (or its TEITOK files) and writes CSV
> tables; the [service](#the-service) reads the document record instead. Both run the same three methods.

Extract keywords 🔎 from your documents by running `keywords.py` on a directory of CoNLL-U files.

### Configuration Priority

The keyword extraction script uses a three-tier configuration hierarchy (from highest to lowest priority):

1. **Command-line flags** (e.g., `-m yake`, `-w 3`) always override everything else.
2. **`kw_config.txt`** (the `[DEFAULTS]` section) is read automatically if placed next to the script.
3. **Hardcoded fallbacks** are used if no config file or flags are provided.

This means if you configure your settings in `kw_config.txt`, you can simply run:

```bash
python3 keywords.py
```

### Backends

| Flag value            | Method                                                   | Dependencies                                | Score semantics                       | Best for                                  |
|-----------------------|----------------------------------------------------------|---------------------------------------------|---------------------------------------|-------------------------------------------|
| `legacy`              | Original KER — NOUN/PROPN/ADJ lemma frequency            | none (stdlib only)                          | raw occurrence count                  | reproducing original ATRIUM results       |
| `yake`                | YAKE — unsupervised statistical, CPU-only (**AGPL-3.0**) | `pip install yake`                          | normalised inverse YAKE score, [0, 1] | fast CPU runs, no model download          |
| `keybert` *(default)* | KeyBERT — embedding-based, GPU-accelerated               | `pip install keybert sentence-transformers` | cosine similarity, [0, 1]             | highest semantic quality, GPU recommended |

You can override any `kw_config.txt` setting via the command line:

```bash
python3 keywords.py -i <input_dir> -m <method> -l <lang> -w <integer> \
                    -n <integer> -d <output_dir> -o <output_file>.csv
```

All available flags:

| Flag | Long form           | Default in `kw_config.txt`              | Description                                                                               |
|------|---------------------|-----------------------------------------|-------------------------------------------------------------------------------------------|
| `-i` | `--input_dir`       | `data_samples/UDP`                      | CoNLL-U directory to process                                                              |
| `-m` | `--method`          | `keybert`                               | Backend: `legacy`, `yake`, or `keybert`                                                   |
| `-l` | `--lang`            | `cs`                                    | Language code for YAKE stopwords (`cs`, `en`, `de`, …). Ignored by `legacy` and `keybert` |
| `-w` | `--max_words`       | `3`                                     | Maximum words per keyword phrase (n-gram upper bound)                                     |
| `-n` | `--num_keywords`    | `20`                                    | Number of keywords to extract per document                                                |
| `-d` | `--per_doc_out_dir` | `data_samples/KW_PER_DOC`               | Output directory for per-document CSV files                                               |
| `-o` | `--output_file`     | `keywords_summary.csv`                  | Master keywords CSV                                                                       |
|      | `--keybert-model`   | `paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformer model name (KeyBERT only)                                            |
|      | `--no-mmr`          | *(False)*                               | Disable Maximal Marginal Relevance diversification (KeyBERT only)                         |
|      | `--diversity`       | `0.5`                                   | MMR diversity parameter, 0 = max relevance → 1 = max diversity (KeyBERT only)             |
|      | `--workers`         | `0` *(Auto / CPU count)*                | Parallel worker processes. Auto-forced to 1 for KeyBERT + GPU                             |

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

**Legacy KER** — (English/Czech) original ATRIUM lemma-frequency approach, no extra dependencies

```bash
python3 keywords.py -i OUTPUT_DIR/UDP -m legacy -n 20 \
        -o keywords_summary.csv -d KW_PER_DOC
```

> [!WARNING]
> For **KeyBERT with a GPU**, the script automatically forces `--workers 1` to
> prevent competing CUDA context initialisation across subprocesses.  On CPU,
> any worker count is safe.

### Inputs and outputs

* **Input:** Directory of per-document CoNLL-U files (nlp-enrich's `UDP/`), or `*.teitok.xml` files.
* **Output 1:** Master table with keywords per document (e.g., `keywords_summary.csv`).
* **Output 2:** Per-document CSV files (e.g., `KW_PER_DOC/`).

```
KW_PER_DOC/
├── <docname1>_keywords.csv
├── <docname2>_keywords.csv
└── ...
```

Each per-document file contains two columns — **keyword** and **score** — sorted
by score in descending order.  The master summary uses the same column structure
as the original pipeline (`document_id`, `kw-1`, `score-1`, `kw-2`, `score-2`, …).

### Score interpretation by backend

**`legacy`** — raw lemma count; higher = more frequent in the document. Examples in directory: [KW_PER_DOC_L](data_samples/KW_PER_DOC_L) 📂 and summary file
[kw_summary_l.csv](data_samples/keywords_summary_l.csv) 📎.

| Score range | Interpretation                                           |
|-------------|----------------------------------------------------------|
| 1–5         | Common functional nouns, low informativeness             |
| 5–20        | Topic-representative vocabulary                          |
| > 20        | Dominant terms, likely named entities or domain headings |

**`yake`** — normalised inverse YAKE score, [0, 1] per document. Examples in directory: [KW_PER_DOC_Y](data_samples/KW_PER_DOC_Y) 📂 and summary file
[kw_summary_y.csv](data_samples/keywords_summary_y.csv) 📎.

| Score range | Semantic category | Interpretation                               |
|-------------|-------------------|----------------------------------------------|
| 0.0–0.2     | Noise floor       | Common words, low local relevance            |
| 0.2–0.6     | Context layer     | General vocabulary defining the broad topic  |
| 0.6–0.9     | Topic layer       | Specific nouns and verbs central to the text |
| 0.9–1.0     | Entity layer      | Rare terms, neologisms, named entities       |

**`keybert`** — cosine similarity to document centroid, [0, 1]. Examples in directory: [KW_PER_DOC_KB](data_samples/KW_PER_DOC_KB) 📂 and summary file
[kw_summary_kb.csv](data_samples/keywords_summary_kb.csv) 📎.

| Score range | Interpretation                   |
|-------------|----------------------------------|
| < 0.3       | Weakly related phrases           |
| 0.3–0.6     | Contextually relevant terms      |
| > 0.6       | Highly representative keyphrases |

---

## The controlled kind and the vocabulary

The controlled kind maps each line onto the AMČR keyword lists and the TEATER thesaurus with a language model whose
answer is constrained to the vocabulary's terms (a JSON schema whose category is an enum of all 4712 of them). One
prompt serves every path: [`prompts/system_prompt.txt`](prompts/system_prompt.txt), whose blocks the `PROMPT_*` flags
of `llm_config.txt` select — [`prompts/RUNBOOK.md`](prompts/RUNBOOK.md) explains each — followed by the vocabulary
and the examples; `python3 prompt_template.py --preview` prints it. Each answer carries the AMČR/TEATER records behind
the chosen term (`teater_category_ids`), and a homonym the vocabulary build qualified (`zámek (sídlo elity)`) comes
back as its plain label.

| Path                                               | Model                                    | Reads                                                        | Writes                                                          |
|----------------------------------------------------|------------------------------------------|--------------------------------------------------------------|-----------------------------------------------------------------|
| the service, `kind=controlled\|both`               | an inference service: OpenRouter, Ollama | the record's lines                                           | the record's `enrichment` block, `entities[].pid`               |
| `openrouter_client.py`, `ollama_client.py` (batch) | the same                                 | records, CSV, TEITOK (per line); `.md`/`.txt` (per document) | `<doc_id>_enriched.json`, the record with `--document-json-out` |
| `llm_run.py` (research, GPU)                       | local weights, vLLM or transformers      | CSV, TEITOK                                                  | `<doc_id>_enriched.json`                                        |

The first two share `llm_client_shared.py`, which needs no GPU stack (`requirements_remote.txt`); the third is the
bake-off path of atrium-keyword-extract#2 (`llm_utils.py`, `requirements_llm.txt`, the `llm` Docker target).

```bash
pip install -r requirements_remote.txt
export OPENROUTER_API_KEY=sk-...
python openrouter_client.py --input CTX000000001.document.json --model openai/gpt-4o-mini \
  --document-json-out CTX000000001.kw.document.json
python ollama_client.py --input data_samples/DOC_LINE_CATEG --model qwen2.5:14b
```

The vocabulary:

* `vocab_sources.py`, `vocab_build.py`, `vocab_review.py`, `vocab_manager.py` — harvest the AMČR and TEATER vocabularies,
  build the nested union, review it; the built files are in [`data_samples/vocab`](data_samples/vocab) (see its
  [RUNBOOK](data_samples/vocab/RUNBOOK.md)). The vocabularies are **CC0**; the build is to be published as a versioned
  release asset for the translator and the end-to-end test.
* `corpus_review.py` — the vocabulary-gap review used for the TEATER experiment.

The LLM engine and the vocabulary code existed twice, in nlp-enrich and in llm-enrich, and partly diverged. This
repository holds the one copy: nlp-enrich's came with the repository, and llm-enrich's (atrium-digital-convert
`31534d5`) was merged into it on 2026-10-07 — its remote clients, its service path and its later engine fixes.

## Licences

The code is **MIT**. The licence of a run's output is computed from the components it used, as declared in
[`para_config.txt`](para_config.txt), and the most restrictive one wins:

| Component                                           | Licence          | When                                                    |
|-----------------------------------------------------|------------------|---------------------------------------------------------|
| KER (legacy)                                        | MIT              | `method=legacy`                                         |
| KeyBERT, sentence-transformers, the embedding model | MIT / Apache-2.0 | `method=keybert`                                        |
| **YAKE**                                            | **AGPL-3.0**     | `method=yake` — a run that uses it is declared AGPL-3.0 |
| AMČR and TEATER vocabularies                        | CC0              | the vocabulary build, the controlled kind               |

The language model of the controlled kind has no row: its terms depend on the model a deployment chooses
(`OPENROUTER_MODEL`, `OLLAMA_MODEL`, `MODEL_KEY`), whose id every run records in its paradata. The source document's
own licence applies to its text.

## Docker

| Target | Image                                     | What it is                                                          |
|--------|-------------------------------------------|---------------------------------------------------------------------|
| `api`  | `ghcr.io/ufal/atrium-keyword-extract-api` | the service, both kinds — **the production image** (no LLM weights) |
| `base` | `ghcr.io/ufal/atrium-keyword-extract`     | the batch CLI (`keywords.py`)                                       |
| `llm`  | `ghcr.io/ufal/atrium-keyword-extract-llm` | the research LLM batch run, GPU                                     |

```bash
docker compose --profile api up                       # the service on :8000
docker compose run --rm kw -i /data/UDP -m yake       # the batch CLI
docker compose -f docker-compose.yaml -f docker-compose.gpu.yaml --profile llm run --rm kw-llm
```

The images of `atrium-nlp-enrich` (its `-llm` target) and `atrium-llm-enrich` that carried these stages before
1 October 2026 stay published for consumers pinned to them and receive no new tags.

## Contributing and contacts

See [CONTRIBUTING.md](CONTRIBUTING.md). For support write to **lutsai.k@gmail.com**, responsible for this
repository.

* **Developed by:** UFAL [^7]
* **Funded by:** ATRIUM [^4]

**©️ 2026 UFAL & ATRIUM**

[^4]: https://atrium-research.eu/
[^7]: https://ufal.mff.cuni.cz/home-page
