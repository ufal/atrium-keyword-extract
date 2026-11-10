# How keyword-extract works

Two kinds of keyword, kept apart: every keyword names the method that produced it, with its score and rank.

## The statistical kind

The record is read: its `lines[].text` per page (lines labelled `Trash`, `Garbage`, `Inverted` or `Empty` are left
out). The same reader (`kw_inputs.py`) also takes [nlp-enrich](https://github.com/ufal/atrium-nlp-enrich)'s CoNLL-U and
TEITOK files, a line table and plain text.

The legacy method counts lemmas. It takes those of the nouns, proper nouns and adjectives of a CoNLL-U or TEITOK file,
or a record's `lines[].lemma` and `lines[].upos`, which no ATRIUM tool writes today.

In the pipeline, keyword-extract comes after nlp-enrich (and after digital-convert on the born-digital route).
nlp-enrich's `/project_record` can project the statistical and controlled keywords into the TEITOK header: each
page's lists get an id that its `<pb>` points to, so a TEITOK project can search them as page attributes
(ufal/flexiconv#1).

| Method    | Needs                                   | Score                                     |
|-----------|-----------------------------------------|-------------------------------------------|
| `keybert` | the embedding model, a GPU if available | cosine similarity, [0, 1]                 |
| `yake`    | nothing (CPU)                           | inverted YAKE score, normalised to [0, 1] |
| `legacy`  | lemmas (CoNLL-U, TEITOK, or a record's) | an occurrence count                       |

Scores are compared only within one method.

What the scores mean, method by method: [the outputs reference](reference/outputs.md#score-interpretation-by-backend).

## The controlled kind and the vocabulary

The controlled kind maps each line onto the AMČR keyword lists and the TEATER thesaurus with a language model. The
model's answer is constrained to the vocabulary's terms: a JSON schema whose category is an enum of its 4711 terms and
the meta-text answer `Nerelevantní (meta-text)`. The halves of composite terms that
`data_samples/vocab/composite_halves.csv` accepts are allowed too, and are recorded as their term.

The constraint keeps the answer inside the vocabulary, not on topic. A model can be forced onto an unrelated term that
shares the start of the word it began (see the [service's Known limits](../service/README.md#known-limits)).

One prompt serves every path. It is [`prompts/system_prompt.txt`](../prompts/system_prompt.txt), whose blocks the
`PROMPT_*` flags of `llm_config.txt` select ([`prompts/RUNBOOK.md`](../prompts/RUNBOOK.md) explains each), followed by
the vocabulary and the examples. `python3 prompt_template.py --preview` prints it.

Each answer carries the AMČR/TEATER records behind the chosen term (`teater_category_ids`). A homonym the vocabulary
build qualified (`zámek (sídlo elity)`) comes back as its plain label.

| Path                                               | Model                                    | Reads                                                        | Writes                                                          |
|----------------------------------------------------|------------------------------------------|--------------------------------------------------------------|-----------------------------------------------------------------|
| the service, `kind=controlled\|both`               | an inference service: OpenRouter, Ollama | the record's lines                                           | the record's `enrichment` block, `entities[].pid`               |
| `openrouter_client.py`, `ollama_client.py` (batch) | the same                                 | records, CSV, TEITOK (per line); `.md`/`.txt` (per document) | `<doc_id>_enriched.json`, the record with `--document-json-out` |
| `llm_run.py` (research, GPU)                       | local weights, vLLM or transformers      | CSV, TEITOK                                                  | `<doc_id>_enriched.json`                                        |

The first two share `llm_client_shared.py`, which needs no GPU stack (`requirements_remote.txt`). The third is the
research path, on which language models were compared. It uses `llm_utils.py`, `requirements_llm.txt` and the `llm`
Docker target.

The vocabulary:

* `vocab_sources.py`, `vocab_build.py`, `vocab_review.py` and `vocab_manager.py` harvest the AMČR and TEATER
  vocabularies, build the nested union and review it. The built files are in
  [`data_samples/vocab`](../data_samples/vocab) (see its [RUNBOOK](../data_samples/vocab/RUNBOOK.md)). The
  vocabularies are **CC0**. Every release attaches the build as `atrium-vocabulary-<version>.zip` with its `.sha256`,
  which the translator and the end-to-end test read.
* `corpus_review.py` is the vocabulary-gap review used for the TEATER experiment.
* `score_categories.py` reports the category picks of `llm_run.py` runs, run by run: lines missing, forced labels,
  confidence spread, agreement between runs, and a re-run against its earlier run. It needs no torch.
