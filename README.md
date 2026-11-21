# ATRIUM keyword-extract: keywords of archival documents, statistical and vocabulary-controlled

keyword-extract suggests keywords for an archival document and each of its pages, in two kinds kept apart.
Statistical keywords are the words and phrases that best describe the text. Controlled keywords are terms from the
keyword lists of the Czech archaeological database AMČR and from TEATER, a thesaurus of archaeological terms
published by AIS CR, chosen for each line by a language model. Use it on documents whose text is already
recognised. The controlled kind needs a language-model service and is research output.

[Releases](https://github.com/ufal/atrium-keyword-extract/releases) · [MIT licence](LICENSE) ·
[ATRIUM documentation](https://ufal.github.io/atrium-project/workflows/keyword-extract/)

## Inputs and outputs

| Input                                                                                                       | Output                                                                                                                       |
|-------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| the ATRIUM document record: its `lines[].text`, and each line's `lemma` and `upos`, which nlp-enrich writes | statistical keywords of the document and of each page; the record with its `keywords` block                                  |
| the same record, with a language-model service configured                                                   | per line, an AMČR/TEATER term with its ids, the Czech and English keywords of the line, entity links; the `enrichment` block |
| a plain text (`/extract_keywords_text`)                                                                     | its statistical keywords                                                                                                     |
| nlp-enrich's CoNLL-U or TEITOK file, a line table (CSV), a `.txt`                                           | the same statistical keywords, from the service (`file`) or the command line                                                 |
| for the batch command line: a folder of any of the above                                                    | a summary CSV, one CSV per document and per page, the records ([outputs](docs/reference/outputs.md))                         |

The record follows the hub's [document contract](https://ufal.github.io/atrium-project/ecosystem/document-contract/).
Lines labelled `Trash` or `Empty` are left out. `keywords.py` and the service read every input
with the same code (`kw_inputs.py`). What only one of them does, and why:
[the command line and the service](docs/usage.md#the-command-line-and-the-service).

## Quick start

**What you need:** Python 3.11 and a checkout, or Docker. For the KeyBERT method, network access to the Hugging Face
Hub on the first start, to fetch its embedding model; YAKE needs none. For the controlled kind only, access to
OpenRouter or to an Ollama server. No GPU.

Extract the keywords of one sentence with YAKE, which needs no model. From a checkout, start the service in a second
terminal; `DEFAULT_KW_METHOD=yake` keeps it from fetching KeyBERT's embedding model when it starts:

```bash
git clone https://github.com/ufal/atrium-keyword-extract.git && cd atrium-keyword-extract
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r service/requirements.txt
DEFAULT_KW_METHOD=yake python -m service.api      # serves on port 8000; leave it running
```

Then call it from the first one:

```bash
curl --fail-with-body -sS -X POST localhost:8000/extract_keywords_text -H 'Content-Type: application/json' \
  -d '{"text": "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou.", "method": "yake", "kind": "statistical", "num_keywords": 5}'
```

The same from the published image, started in the background and stopped at the end:

```bash
docker run -d --name atrium-keyword-extract -p 8000:8000 -e DEFAULT_KW_METHOD=yake \
  ghcr.io/ufal/atrium-keyword-extract-api:<version>   # 2.0.0-beta or later, without its v
until curl -fsS localhost:8000/ready >/dev/null 2>&1; do sleep 2; done
curl --fail-with-body -sS -X POST localhost:8000/extract_keywords_text -H 'Content-Type: application/json' \
  -d '{"text": "Archeologický výzkum odkryl zahloubený objekt se sídlištní keramikou.", "method": "yake", "kind": "statistical", "num_keywords": 5}'
docker rm -f atrium-keyword-extract
```

Expected result (abridged):

```json
{"kind": "statistical", "method_used": "yake", "words": 8,
 "keywords": [{"keyword": "Archeologický výzkum odkryl", "score": 1.0, "method": "yake", "rank": 1}, "…"],
 "kinds": [{"kind": "statistical", "status": "ok", "detail": null}], "paradata": {"@type": "CreateAction", "…": "…"}}
```

The service answers nothing until it has started: with KeyBERT, the default method, it first loads the embedding
model, from the Hugging Face Hub the first time. `POST /extract_keywords` takes a record
(`-F "document_json=@<doc>.document.json;type=application/json"`) and also returns per-page keywords and the record
with its blocks. The controlled kind (`kind=controlled` or `both`) calls OpenRouter or a local Ollama, set by
`LLM_BACKEND`. Without a backend it answers 501, or reports itself `skipped` under `kind=both`. Every option:
[service/README.md](service/README.md). Releases before 2.0.0-beta are described by the README at their tag.

The batch command line, `keywords.py`, extracts the statistical keywords of a whole folder
([usage](docs/usage.md#extract-keywords-from-a-folder)).

## How it works

The statistical kind runs one of three methods over the record's text, for the whole document and page by page:
KeyBERT (the default), YAKE, or KER, the legacy method, which counts lemmas. Every keyword carries its method, score
and rank, and scores compare only within a method. The controlled kind sends each line to a language model, with a
prompt that carries the whole vocabulary. The model's answer is constrained to the vocabulary's 4,711 terms. The
chosen term is written with its AMČR and TEATER ids. The details, and the batch and research paths:
[docs/how-it-works.md](docs/how-it-works.md).

## Where it fits in ATRIUM

In the AMČR pipeline keyword-extract follows nlp-enrich and reads the record it leaves: the text of the record's
lines and, for KER, each line's lemma. nlp-enrich gives a line one lemma, that of its head word, so KER counts fewer
lemmas in a record than in nlp-enrich's CoNLL-U or TEITOK file. keyword-extract writes the record's `keywords` and
`enrichment` blocks, which nlp-enrich's `/project_record` can carry into the TEITOK header. The vocabulary build is
also released as `atrium-vocabulary-<version>.zip`, which the translator and the end-to-end tests read. The whole
route: the hub's [Pipelines](https://ufal.github.io/atrium-project/pipelines/#the-route-through-the-pipeline) page and
this tool's [workflow page](https://ufal.github.io/atrium-project/workflows/keyword-extract/). Its SSH Open
Marketplace record: [Keyword extraction from archival documents (statistical and vocabulary-controlled) -
ATRIUM](https://marketplace.sshopencloud.eu/tool-or-service/j9fqxo).

## Limits and maturity

- **The controlled kind is not evaluated.** The rubric is decided, but the annotated gold set does not exist yet, so
  its categories are suggestions and its output is research output
  ([atrium-keyword-extract#2](https://github.com/ufal/atrium-keyword-extract/issues/2)).
- **A constrained answer stays in the vocabulary, not on topic.** A model can be forced onto an unrelated term that
  shares the start of the word it began. A valid category can still be wrong
  ([Known limits](service/README.md#known-limits)).
- **The prompt is large:** about 40,000 tokens by the service's estimate (4 characters a token), about 58,000 by the
  research path's (3.35). A model served with a smaller window sees only part of the vocabulary, and the paradata
  record it as `sampled`, with how many terms were left out
  ([Limits](service/README.md#limits)).
- **No partial result from the service.** A line the model could not answer, a reply cut at `LLM_MAX_NEW_TOKENS` or
  a document given up fails the call, so no record is written ([Errors](service/README.md#errors)). The batch command
  line, outside the pipeline, reports a document it cannot read and goes on with the others
  ([the command line and the service](docs/usage.md#the-command-line-and-the-service)).
- **YAKE is AGPL-3.0.** A run that uses it lists YAKE among its components, with YAKE's own licence
  ([licences](docs/reference/licences.md)).
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
|                                        | find the parked decision-model tools              | [docs/reference/parked.md](docs/reference/parked.md)           |
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
[docs/reference/licences.md](docs/reference/licences.md). Each run lists the components it used, each with its own
licence or terms. No licence of an output is computed: the rights in an output follow the source document (the hub's
[Licences and paradata](https://ufal.github.io/atrium-project/ecosystem/licences/)). Cite with
[CITATION.cff](CITATION.cff).

Developed by [ÚFAL](https://ufal.mff.cuni.cz/), Charles University. Funded by the European Union under Horizon Europe
([ATRIUM](https://atrium-research.eu/), GA 101132163), with the support of the LINDAT/CLARIAH-CZ (LM2023062) and AIS
CR (LM2023031) research infrastructures, funded by the Ministry of Education, Youth and Sports of the Czech Republic.
Contact: the [issue tracker](https://github.com/ufal/atrium-keyword-extract/issues), or lutsai@ufal.mff.cuni.cz.

The keyword code came from atrium-nlp-enrich and atrium-llm-enrich in October 2026; see
[History of the repository](docs/development.md#history-of-the-repository).
