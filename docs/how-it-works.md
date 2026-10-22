# How keyword-extract works

Two kinds of keyword, kept apart: every keyword names the method that produced it, with its score and rank.

## The statistical kind

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

What the scores mean, method by method: [the outputs reference](reference/outputs.md#score-interpretation-by-backend).

## The controlled kind and the vocabulary

The controlled kind maps each line onto the AMČR keyword lists and the TEATER thesaurus with a language model whose
answer is constrained to the vocabulary's terms (a JSON schema whose category is an enum of its 4711 terms and the
meta-text answer `Nerelevantní (meta-text)`, plus the halves of composite terms that
`data_samples/vocab/composite_halves.csv` accepts, recorded as their term). The constraint keeps the answer inside
the vocabulary, not on topic: a model can be forced onto an unrelated term that shares the start of the word it began
(the [service's Known limits](../service/README.md#known-limits); #2). One
prompt serves every path: [`prompts/system_prompt.txt`](../prompts/system_prompt.txt), whose blocks the `PROMPT_*` flags
of `llm_config.txt` select — [`prompts/RUNBOOK.md`](../prompts/RUNBOOK.md) explains each — followed by the vocabulary
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

The vocabulary:

* `vocab_sources.py`, `vocab_build.py`, `vocab_review.py`, `vocab_manager.py` — harvest the AMČR and TEATER vocabularies,
  build the nested union, review it; the built files are in [`data_samples/vocab`](../data_samples/vocab) (see its
  [RUNBOOK](../data_samples/vocab/RUNBOOK.md)). The vocabularies are **CC0**; every release attaches the build as
  `atrium-vocabulary-<version>.zip` with its `.sha256`, which the translator and the end-to-end test read.
* `corpus_review.py` — the vocabulary-gap review used for the TEATER experiment.
* `score_categories.py` — the category picks of `llm_run.py` runs, run by run: lines missing, forced labels,
  confidence spread, agreement between runs, a re-run against its earlier run (#2). Torch-free.

The LLM engine and the vocabulary code existed twice, in nlp-enrich and in llm-enrich, and partly diverged. This
repository holds the one copy: nlp-enrich's came with the repository, and llm-enrich's (atrium-digital-convert
`31534d5`) was merged into it on 2026-10-07 — its remote clients, its service path and its later engine fixes.
