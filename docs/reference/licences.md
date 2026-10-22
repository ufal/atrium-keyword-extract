# Licences

The code is **MIT**. The licence of a run's output is computed from the components it used, as declared in
[`para_config.txt`](../../para_config.txt), and the most restrictive one wins:

| Component                                           | Licence          | When                                                    |
|-----------------------------------------------------|------------------|---------------------------------------------------------|
| KER (legacy)                                        | MIT              | `method=legacy`                                         |
| KeyBERT, sentence-transformers, the embedding model | MIT / Apache-2.0 | `method=keybert`                                        |
| **YAKE**                                            | **AGPL-3.0**     | `method=yake` — a run that uses it is declared AGPL-3.0 |
| AMČR and TEATER vocabularies                        | CC0              | the vocabulary build, the controlled kind               |

The language model of the controlled kind has no row: its terms depend on the model a deployment chooses
(`OPENROUTER_MODEL`, `OLLAMA_MODEL`, `MODEL_KEY`), whose id every run records in its paradata. The source document's
own licence applies to its text.
