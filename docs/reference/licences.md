# Licences

The code is **MIT**. Each run lists the components it used in its paradata `components`, each with its own licence, as
declared in [`para_config.txt`](../../para_config.txt). **None of them is the licence of the keywords**, and no licence
of an output is computed: since paradata schema 3.0 (ARÚP's output contract of 12 November 2026,
[atrium-project#84](https://github.com/ufal/atrium-project/issues/84)) neither the paradata nor the record has a
`license` field. The rights in an output depend first on the source document. They are stated by whoever holds them:
for the AMČR pilot, AMČR, as agreed on 22 October 2026 ([atrium-project#6](https://github.com/ufal/atrium-project/issues/6))
([Licences and paradata](https://ufal.github.io/atrium-project/ecosystem/licences/)).

| Component                                                   | Licence          | When                                                                         |
|-------------------------------------------------------------|------------------|------------------------------------------------------------------------------|
| the legacy method (lemma frequency; this repository's code) | MIT              | `method=legacy`                                                              |
| KeyBERT, sentence-transformers, the embedding model         | MIT / Apache-2.0 | `method=keybert`                                                             |
| **YAKE**                                                    | **AGPL-3.0**     | `method=yake`: a run that uses it lists it                                   |
| AMČR and TEATER vocabularies                                | CC0              | the vocabulary build, the controlled kind                                    |

The language model of the controlled kind has no row. Its terms depend on the model a deployment chooses
(`OPENROUTER_MODEL`, `OLLAMA_MODEL`, `MODEL_KEY`), and every run records that model's id in its paradata. The source
document's own licence applies to its text.

**YAKE.** The package's PyPI metadata says LGPLv3. The `LICENSE` file it ships (yake 0.7.3) is the GNU AGPL-3.0, with a
commercial licence available from INESC TEC. The declaration follows the `LICENSE` file.

**The legacy method and KER.** `method=legacy` counts the noun, proper-noun and adjective lemmas of a text. It is
named after ÚFAL's keyword extractor KER (Libovický, 2016, [LINDAT](http://hdl.handle.net/11234/1-1650)), which
weights lemmas by tf-idf. The method here does not weight by document frequency and uses none of KER's code. The two
IDF tables in `ker_data/` come from KER's LINDAT release. No shipped code reads them, and they are not in the images
(`.dockerignore`).
