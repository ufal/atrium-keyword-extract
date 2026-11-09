# Developing keyword-extract

How to set up a working copy, run the tests, find your way around the repository, and trace where it came from.
This page is for contributors. To use the tool, start with [Using keyword-extract](usage.md).

## Set up a working copy

Create a virtual environment and install the requirements as described under
[Set it up](usage.md#set-it-up). For the tests, also install `requirements-test.txt`; the commands are under
[Running the test suite](../CONTRIBUTING.md#running-the-test-suite).

## Tests and conventions

[CONTRIBUTING.md](../CONTRIBUTING.md) holds the rules, and this page does not repeat them:

- the branches and their names: [Branches & Environments](../CONTRIBUTING.md#branches--environments);
- how to open a pull request and write a commit message: [Contributor Workflow](../CONTRIBUTING.md#contributor-workflow);
- the code conventions and the checks to run before a commit:
  [Code Conventions & Testing](../CONTRIBUTING.md#code-conventions--testing);
- the files that scripts generate, and which must not be edited by hand:
  [Generated Artefacts](../CONTRIBUTING.md#generated-artefacts);
- the changelog: [Release History](../CONTRIBUTING.md#release-history).

The vocabulary and the prompt have their own runbooks:
[`data_samples/vocab/RUNBOOK.md`](../data_samples/vocab/RUNBOOK.md) for the vocabulary scripts and review sheets, and
[`prompts/RUNBOOK.md`](../prompts/RUNBOOK.md) for the prompt blocks and their flags.

## Layout of the repository

| Path                                                                              | What it holds                                                                                                         |
|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `keywords.py`, `kw_inputs.py`, `kw_config.txt`                                    | the batch command line for the statistical kind, the reader that the command line and the service share, its defaults |
| `service/`                                                                        | the HTTP service (`api.py`), its runbook, the committed `openapi.json`, and its requirements                          |
| `llm_client_shared.py`, `openrouter_client.py`, `ollama_client.py`                | the controlled kind's engine and its two remote clients, which need no GPU                                            |
| `llm_run.py`, `llm_utils.py`, `llm_config.txt`, `requirements_llm.txt`            | the research run on a GPU node (the `llm` Docker target)                                                              |
| `prompt_template.py`, `prompts/`                                                  | the controlled kind's prompt, built from blocks, and its renders                                                      |
| `vocab_sources.py`, `vocab_build.py`, `vocab_review.py`, `vocab_manager.py`       | the AMČR and TEATER vocabulary: harvest, build, review, look-up                                                       |
| `corpus_review.py`, `score_categories.py`                                         | the vocabulary-gap review, and the report on a run's category picks                                                   |
| `dm_run.py`                                                                       | decision models, offline (#3): the descent tree over the content vocabulary, form terms withheld                      |
| `decision_client.py`                                                              | the decision-model client, copied from page-classification, for `dm_run.py`'s line mode                               |
| `data_samples/`                                                                   | sample inputs, sample outputs, and the built vocabulary in `data_samples/vocab/`                                      |
| `atrium_*.py`, `para_licenses.py`, `tool_limits.py`, `check_version.py`           | the modules shared across ATRIUM tools (the record, paradata, limits), and this tool's limits declaration             |
| `api_util/`                                                                       | the TEITOK reader and the coordinate scaling, copied from nlp-enrich                                                  |
| `para_config.txt`, `.env.example`                                                 | the tool's version and the licence inventory; the service's environment                                               |
| `ker_data/`                                                                       | the two IDF tables of KER's LINDAT release; no shipped code reads them, and the images leave them out                 |
| `Dockerfile`, `docker-compose.yaml`, `docker-compose.gpu.yaml`, `.github/`        | the three image targets, their compose files, and the workflows                                                       |
| `tests/`                                                                          | the test suite, which needs no model and no GPU                                                                       |
| `docs/`                                                                           | this documentation                                                                                                    |

## History of the repository

keyword-extract was assembled on 1 October 2026 from two repositories' keyword code, after the meeting of
30 September ([#1](https://github.com/ufal/atrium-keyword-extract/issues/1)):

- the keyword extraction of [atrium-nlp-enrich](https://github.com/ufal/atrium-nlp-enrich) (`keywords.py`), which
  keeps the LINDAT calls (UDPipe and NameTag);
- `atrium-llm-enrich`, which supplied the LLM engine and the vocabulary code. Its `/extract_keywords` became the
  service's controlled kind.

The LLM engine and the vocabulary code had existed twice, in nlp-enrich and in llm-enrich, and had partly
diverged. This repository holds the one copy. nlp-enrich's came with the repository. llm-enrich's
(atrium-digital-convert `31534d5`) was merged into it on 7 October 2026: its remote clients, its service path and its
later engine fixes.

The images of those two repositories that carried these stages stay published, for consumers pinned to them, and get
no new tags: the `-llm` target of nlp-enrich, and the images of llm-enrich. The release histories of both stay in
their own repositories. This repository's release history begins with v1.0.0-beta, in
[CONTRIBUTING.md](../CONTRIBUTING.md#release-history). The service id is `atrium-keyword-extract`, and its OpenAPI
document declares `x-atrium-service-previous: atrium-nlp-enrich`, the id of the service the statistical keywords came
from.

## Working records

[`agent_dev_logs/`](../agent_dev_logs/DEVLOG.md) holds the maintainers' working record: the development log
(`DEVLOG.md`), the per-issue digests and plans, and exports of issues. It is not documentation for users or
operators, and it cites files that have since moved or been deleted. Nothing there is needed to use or run the tool.
This is the only page that points to it; every other page cites the issue instead.
