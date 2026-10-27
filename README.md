# ATRIUM keyword-extract: keywords of archival documents, statistical and vocabulary-controlled

keyword-extract gives an archival document two kinds of keyword, kept apart. Statistical keywords (KeyBERT by
default, YAKE, or the legacy KER) describe the document and each of its pages. Controlled keywords assign each line
a term of the AMČR keyword lists and the TEATER thesaurus, chosen by a language model, with the records behind the
term. Every keyword names the method that produced it, with its score and rank. Use it on the ATRIUM document record
after nlp-enrich; the controlled kind needs a language-model service and is research output.

[Releases](https://github.com/ufal/atrium-keyword-extract/releases) · [MIT licence](LICENSE) ·
[ATRIUM documentation](https://ufal.github.io/atrium-project/workflows/keyword-extract/)

This repository was assembled on 1 October 2026 from the keyword extraction of
[atrium-nlp-enrich](https://github.com/ufal/atrium-nlp-enrich) (`keywords.py`) and of `atrium-llm-enrich` (the LLM
engine and the vocabulary code), after the meeting of 30 September
([#1](https://github.com/ufal/atrium-keyword-extract/issues/1)); nlp-enrich keeps the LINDAT calls (UDPipe,
NameTag). The images of those two repositories that carried these stages stay published and get no new tags.

## Inputs and outputs

| Input                                                                            | Output                                                                                                                       |
|----------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| the ATRIUM document record after nlp-enrich: its `lines[].text`, `lemma`, `upos` | statistical keywords of the document and of each page; the record with its `keywords` block                                  |
| the same record, with a language-model service configured                        | per line, an AMČR/TEATER term with its ids, the Czech and English keywords of the line, entity links; the `enrichment` block |
| a plain text (`/extract_keywords_text`)                                          | its statistical keywords                                                                                                     |
| nlp-enrich's CoNLL-U or TEITOK file, a line table (CSV), a `.txt`                | the same statistical keywords, from the service (`file`) or the command line                                                 |
| for the batch command line: a folder of any of the above                         | a summary CSV, one CSV per document and per page, the records ([outputs](docs/reference/outputs.md))                         |

The record follows the hub's [document contract](https://ufal.github.io/atrium-project/ecosystem/document-contract/);
lines labelled `Trash`, `Garbage`, `Inverted` or `Empty` are left out. `keywords.py` and the service read every input
with the same code (`kw_inputs.py`); what only one of them does, and why:
[the command line and the service](docs/usage.md#the-command-line-and-the-service).

## Quick start

The service from the published image, on a sentence, with YAKE (no model to download):

```bash
docker run --rm -p 8000:8000 ghcr.io/ufal/atrium-keyword-extract-api:<version>   # the release without its v
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
Ollama, set by `LLM_BACKEND`; without one it answers 501, or reports itself `skipped` under `kind=both`. Every
option: [service/README.md](service/README.md).

## How it works

The statistical kind runs one of three methods over the record's text, for the whole document and page by page;
scores compare only within a method. The controlled kind sends each line, with a prompt that carries the whole
vocabulary (about 58k tokens), to a language model whose answer is constrained to the vocabulary's 4,711 terms, and
writes the chosen term with its AMČR and TEATER ids. The details, and the batch and research paths:
[docs/how-it-works.md](docs/how-it-works.md).

## Where it fits in ATRIUM

keyword-extract comes after nlp-enrich, which gives the record its lemmas and parts of speech, and on the
born-digital route after digital-convert. It writes the record's `keywords` and `enrichment` blocks, which
nlp-enrich's `/project_record` can carry into the TEITOK header. The vocabulary build is also released as
`atrium-vocabulary-<version>.zip`, which the translator and the end-to-end tests read. The whole chain: the
[hub's workflow page](https://ufal.github.io/atrium-project/workflows/keyword-extract/). Its SSH Open Marketplace
record: [Keyword extraction from archival documents (statistical and vocabulary-controlled) -
ATRIUM](https://marketplace.sshopencloud.eu/tool-or-service/j9fqxo).

## Limits and maturity

- **The controlled kind is not evaluated.** The rubric is decided, but the annotated gold set does not exist yet,
  so treat its output as research output ([#2](https://github.com/ufal/atrium-keyword-extract/issues/2)).
- **A constrained answer stays in the vocabulary, not on topic:** a model can be forced onto an unrelated term that
  shares the start of the word it began ([Known limits](service/README.md#known-limits)).
- **The prompt is about 58k tokens.** A model served with a smaller window sees only part of the vocabulary; the
  paradata records how many terms were cut.
- **YAKE is AGPL-3.0:** a run that uses it is declared AGPL-3.0 ([licences](docs/reference/licences.md)).
- **The research path (`llm_run.py`) needs a GPU** and local weights; the service needs neither.

## Documentation

| To                                                          | Read                                                           |
|-------------------------------------------------------------|----------------------------------------------------------------|
| set it up, run the service, the batch CLI, the images       | [docs/usage.md](docs/usage.md)                                 |
| deploy and operate the service, its options, limits, errors | [service/README.md](service/README.md)                         |
| see the API contract                                        | [service/openapi.json](service/openapi.json)                   |
| understand the two kinds and the vocabulary                 | [docs/how-it-works.md](docs/how-it-works.md)                   |
| read the batch CLI's outputs and scores                     | [docs/reference/outputs.md](docs/reference/outputs.md)         |
| see the licences of a run                                   | [docs/reference/licences.md](docs/reference/licences.md)       |
| build or review the vocabulary                              | [data_samples/vocab/RUNBOOK.md](data_samples/vocab/RUNBOOK.md) |
| change the controlled kind's prompt                         | [prompts/RUNBOOK.md](prompts/RUNBOOK.md)                       |
| contribute, test, release                                   | [CONTRIBUTING.md](CONTRIBUTING.md)                             |

The documentation follows the ATRIUM
[documentation style](https://github.com/ufal/atrium-project/blob/main/docs/documentation-style.md).

## Licence, citation and acknowledgements

The code is MIT ([LICENSE](LICENSE)). It uses [KeyBERT](https://github.com/MaartenGr/KeyBERT) with
sentence-transformers (MIT, Apache-2.0), [YAKE](https://github.com/LIAAD/yake) (AGPL-3.0) and
[KER](https://github.com/ufal/ker) (MIT), and the AMČR and TEATER vocabularies (CC0); the language model of the
controlled kind is the deployment's choice, and every run records its id. The inventory is
[para_config.txt](para_config.txt); what a run records is in [docs/reference/licences.md](docs/reference/licences.md).
Cite with [CITATION.cff](CITATION.cff).

Developed by [ÚFAL](https://ufal.mff.cuni.cz/), Charles University. Funded by [ATRIUM](https://atrium-research.eu/)
(GA 101132163), with the support of the LINDAT/CLARIAH-CZ research infrastructure and the AIS CR infrastructure
(LM2023031). Contact: the [issue tracker](https://github.com/ufal/atrium-keyword-extract/issues).
