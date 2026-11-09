# ATRIUM keyword-extract: keywords of archival documents, statistical and vocabulary-controlled

keyword-extract suggests keywords for an archival document and each of its pages, in two kinds kept apart.
Statistical keywords are the words and phrases that best describe the text. Controlled keywords are terms from the
keyword lists of the Czech archaeological database AMČR and from the TEATER thesaurus, chosen for each line by a
language model. Use it on documents whose text is already recognised. The controlled kind needs a language-model
service and is research output.

[Releases](https://github.com/ufal/atrium-keyword-extract/releases) · [MIT licence](LICENSE) ·
[ATRIUM documentation](https://ufal.github.io/atrium-project/workflows/keyword-extract/)

## Inputs and outputs

| Input                                                                              | Output                                                                                                                       |
|------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| the ATRIUM document record: its `lines[].text` (and `lemma`, `upos` where present) | statistical keywords of the document and of each page; the record with its `keywords` block                                  |
| the same record, with a language-model service configured                          | per line, an AMČR/TEATER term with its ids, the Czech and English keywords of the line, entity links; the `enrichment` block |
| a plain text (`/extract_keywords_text`)                                            | its statistical keywords                                                                                                     |
| nlp-enrich's CoNLL-U or TEITOK file, a line table (CSV), a `.txt`                  | the same statistical keywords, from the service (`file`) or the command line                                                 |
| for the batch command line: a folder of any of the above                           | a summary CSV, one CSV per document and per page, the records ([outputs](docs/reference/outputs.md))                         |

The record follows the hub's [document contract](https://ufal.github.io/atrium-project/ecosystem/document-contract/).
Lines labelled `Trash`, `Garbage`, `Inverted` or `Empty` are left out. `keywords.py` and the service read every input
with the same code (`kw_inputs.py`). What only one of them does, and why:
[the command line and the service](docs/usage.md#the-command-line-and-the-service).

## Quick start

**What you need:** Docker, or Python 3.11 (the version of the image and of CI) and a checkout of this repository.
Network access to the Hugging Face Hub on the first start, for KeyBERT's embedding model (not needed with YAKE). For
the controlled kind only, access to OpenRouter or to an Ollama server. No GPU: the service does not need one.

The service from the published image, on a sentence, with YAKE, which needs no model.
`DEFAULT_KW_METHOD=yake` keeps the service from downloading KeyBERT's embedding model when it starts:

```bash
docker run --rm -p 8000:8000 -e DEFAULT_KW_METHOD=yake \
  ghcr.io/ufal/atrium-keyword-extract-api:<version>   # the release without its v
curl --fail-with-body -sS -X POST localhost:8000/extract_keywords_text -H 'Content-Type: application/json' \
  -d '{"text": "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou.", "method": "yake", "kind": "statistical", "num_keywords": 5}'
```

Expected result (abridged):

```json
{"kind": "statistical", "method_used": "yake", "words": 8,
 "keywords": [{"keyword": "Archeologický výzkum odkryl", "score": 1.0, "method": "yake", "rank": 1}, "…"],
 "kinds": [{"kind": "statistical", "status": "ok", "detail": null}]}
```

`POST /extract_keywords` takes a record (`-F "document_json=@<doc>.document.json;type=application/json"`) and also
returns per-page keywords and the record with its blocks. KeyBERT, the default method, loads its embedding model from
the Hugging Face Hub at start-up. The controlled kind (`kind=controlled` or `both`) calls OpenRouter or a local
Ollama, set by `LLM_BACKEND`. Without a backend it answers 501, or reports itself `skipped` under `kind=both`. Every
option: [service/README.md](service/README.md).

## How it works

The statistical kind runs one of three methods over the record's text, for the whole document and page by page:
KeyBERT (the default), YAKE, or the legacy method KER. Every keyword carries its method, score and rank, and scores
compare only within a method. The controlled kind sends each line to a language model, with a prompt that carries the
whole vocabulary (about 58k tokens). The model's answer is constrained to the vocabulary's 4,711 terms. The chosen
term is written with its AMČR and TEATER ids. The details, and the batch and research paths:
[docs/how-it-works.md](docs/how-it-works.md).
`dm_run.py`, an offline research tool outside the service, prepares decision models over the content vocabulary
([usage](docs/usage.md#decision-models-offline)).

## Where it fits in ATRIUM

keyword-extract comes after nlp-enrich in the scanned-document pipeline, and after digital-convert on the
born-digital route. It reads the record's lines. The legacy method (KER) counts lemmas, which nlp-enrich's CoNLL-U
and TEITOK files carry. No ATRIUM tool writes them into the record today. keyword-extract writes the record's
`keywords` and `enrichment` blocks, which nlp-enrich's `/project_record` can carry into the TEITOK header. The
vocabulary build is also released as `atrium-vocabulary-<version>.zip`, which the translator and the end-to-end tests
read. The whole chain: the [hub's workflow page](https://ufal.github.io/atrium-project/workflows/keyword-extract/).
Its SSH Open Marketplace record: [Keyword extraction from archival documents (statistical and vocabulary-controlled) -
ATRIUM](https://marketplace.sshopencloud.eu/tool-or-service/j9fqxo).

## Limits and maturity

- **The controlled kind is not evaluated.** The rubric is decided, but the annotated gold set does not exist yet, so
  its categories are suggestions and its output is research output
  ([#2](https://github.com/ufal/atrium-keyword-extract/issues/2)).
- **A constrained answer stays in the vocabulary, not on topic.** A model can be forced onto an unrelated term that
  shares the start of the word it began. A valid category can still be wrong
  ([Known limits](service/README.md#known-limits)).
- **The prompt is large:** about 40,000 tokens by the service's estimate (4 characters a token), about 58,000 by the
  research path's (3.35). A model served with a smaller window sees only part of the vocabulary, and the paradata
  records how many terms were cut
  ([Limits](service/README.md#limits)).
- **YAKE is AGPL-3.0.** A run that uses it lists YAKE among its components. That licence is YAKE's, not the licence of
  the keywords ([licences](docs/reference/licences.md)).
- **The research path needs a GPU.** `llm_run.py` runs a model on local weights; the service needs neither a GPU nor
  weights ([usage](docs/usage.md#run-the-controlled-kind-from-the-command-line)).

## Documentation

| For                                    | To                                                | Read                                                           |
|----------------------------------------|---------------------------------------------------|----------------------------------------------------------------|
| using it                               | set it up, run the batch CLI, use the images      | [docs/usage.md](docs/usage.md)                                 |
|                                        | understand the two kinds and the vocabulary       | [docs/how-it-works.md](docs/how-it-works.md)                   |
|                                        | read the batch CLI's outputs and scores           | [docs/reference/outputs.md](docs/reference/outputs.md)         |
|                                        | see the licences of a run                         | [docs/reference/licences.md](docs/reference/licences.md)       |
| running the service                    | deploy and operate it, read its errors and limits | [service/README.md](service/README.md)                         |
|                                        | see the API contract                              | [service/openapi.json](service/openapi.json)                   |
| curating the vocabulary and the prompt | build or review the vocabulary                    | [data_samples/vocab/RUNBOOK.md](data_samples/vocab/RUNBOOK.md) |
|                                        | change the controlled kind's prompt               | [prompts/RUNBOOK.md](prompts/RUNBOOK.md)                       |
| changing the code                      | set up, test, find the layout and the history     | [docs/development.md](docs/development.md)                     |
|                                        | follow the conventions, release                   | [CONTRIBUTING.md](CONTRIBUTING.md)                             |

Terms used across the tools are explained in the [ATRIUM glossary](https://ufal.github.io/atrium-project/glossary/).
The documentation follows the ATRIUM
[documentation style](https://github.com/ufal/atrium-project/blob/main/docs/documentation-style.md).

## Licence, citation and acknowledgements

The code is MIT ([LICENSE](LICENSE)). It uses [KeyBERT](https://github.com/MaartenGr/KeyBERT) with
sentence-transformers (MIT, Apache-2.0), [YAKE](https://github.com/LIAAD/yake) (AGPL-3.0) and its own lemma-frequency
method, named after ÚFAL's [KER](http://hdl.handle.net/11234/1-1650) (MIT). It uses the AMČR and TEATER vocabularies
(CC0). The language model of the controlled kind is the deployment's choice, and every run records its id. The
inventory is [para_config.txt](para_config.txt); what a run records is in
[docs/reference/licences.md](docs/reference/licences.md). Cite with [CITATION.cff](CITATION.cff).

Developed by [ÚFAL](https://ufal.mff.cuni.cz/), Charles University. Funded by [ATRIUM](https://atrium-research.eu/)
(GA 101132163), with the support of the LINDAT/CLARIAH-CZ research infrastructure and the AIS CR infrastructure
(LM2023031). Contact: the [issue tracker](https://github.com/ufal/atrium-keyword-extract/issues).

Assembled on 1 October 2026 from the keyword code of atrium-nlp-enrich and atrium-llm-enrich; its history is in
[docs/development.md](docs/development.md#history-of-the-repository).
