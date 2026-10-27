# Licences

The code is **MIT**. Each run lists the components it used, each with its licence, as declared in
[`para_config.txt`](../../para_config.txt). From that list the shared module `para_licenses.py` computes one more
field, `license`, the most restrictive of the component licences. **That field is a calculated summary of the
components, not the licence of the keywords**: the rights in an output depend first on the source document, and they
are stated by whoever holds them (for the AMČR pilot, AMČR; agreed on 22 October 2026,
[atrium-project#6](https://github.com/ufal/atrium-project/issues/6)).

| Component                                                   | Licence          | When                                                                         |
|-------------------------------------------------------------|------------------|------------------------------------------------------------------------------|
| the legacy method (lemma frequency; this repository's code) | MIT              | `method=legacy`                                                              |
| KeyBERT, sentence-transformers, the embedding model         | MIT / Apache-2.0 | `method=keybert`                                                             |
| **YAKE**                                                    | **AGPL-3.0**     | `method=yake`: a run that uses it lists it, and the summary becomes AGPL-3.0 |
| AMČR and TEATER vocabularies                                | CC0              | the vocabulary build, the controlled kind                                    |

The language model of the controlled kind has no row: its terms depend on the model a deployment chooses
(`OPENROUTER_MODEL`, `OLLAMA_MODEL`, `MODEL_KEY`), whose id every run records in its paradata. The source document's
own licence applies to its text.

**YAKE.** The package's PyPI metadata says LGPLv3, but the `LICENSE` file it ships (yake 0.7.3) is the GNU AGPL-3.0,
with a commercial licence available from INESC TEC; the declaration follows the `LICENSE` file.

**The legacy method and KER.** `method=legacy` counts the noun, proper-noun and adjective lemmas of a text. It is
named after ÚFAL's keyword extractor KER (Libovický, 2016, [LINDAT](http://hdl.handle.net/11234/1-1650)), which
weights lemmas by tf-idf; the method here does not weight by document frequency and uses none of KER's code. The two
IDF tables in `ker_data/` come from KER's LINDAT release; no shipped code reads them, and they are not in the images
(`.dockerignore`).
