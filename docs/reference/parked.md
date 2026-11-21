# Parked features

One part of keyword-extract is parked during the AMČR pilot: the offline tools that prepare decision models over the
content vocabulary (`dm_run.py`, with the client `decision_client.py`). They are kept, tested and described here, but
they are not part of the pipeline or the service. What the pipeline runs is in the [README](../../README.md) and
[usage](../usage.md).

## Decision models, offline

Parked during the AMČR pilot: not part of the pipeline or the service.

`dm_run.py` prepares decision models for
[atrium-keyword-extract#3](https://github.com/ufal/atrium-keyword-extract/issues/3)
([atrium-project#83](https://github.com/ufal/atrium-project/issues/83)). A decision model reads a state, such as a
text, and questions with fixed options, and returns a probability for every option; it writes no text. The tool is
offline and experimental: the service does not run it, no image's entry point reaches it, and nothing it finds
reaches the record. Run it from the repository root, set up as in [usage](../usage.md#set-it-up).

**Content, never form.** This repository reads text and never an image, so a decision model here decides what a
document is about: a term of the vocabulary, or meta-text. What a document is (a report, a photograph, a plan, a
map: its form) is read from page images, by atrium-digital-convert and atrium-page-classification, and AMČR's form
lists (`dokument_typ` and the other `dokument_*` lists) are not in the vocabulary. The document type this tool
asked from text until 2026-11-09 (`--doc-type`) is therefore gone.

### The descent tree: `--dump-tree`

A decision model cannot take the whole vocabulary at once (4,689 terms in the tree; a choice takes at most 255
options), so the planned line mode walks down it, one choice a step: is the line content at all, which facet, the
geographic gate, which group, then down the terms' own tree. Every step also offers `none_of_these`, so an answer is
always a vocabulary term or unresolved. `--dump-tree OUT` builds that tree and writes it as JSON; the line mode
itself (`--lines`) is not written yet and exits 2.

```bash
python3 dm_run.py --dump-tree /tmp/dm_tree.json
```

The tree is built from files the vocabulary build already writes (`data_samples/vocab/union_nested.json`,
`specificity_pairs.csv`, `amcr_flat.json`, `data_samples/taxonomy_config.json`) and from the prompt's blocks and
settings (`prompts/system_prompt.txt`, `llm_config.txt`). The file records each input's SHA-256, the questions'
wording, every node and the tree's statistics, and a digest of all of it but the time it was made. The command
prints the digest and the statistics. How a term's parent is chosen, and how a node with too many options is
split, is in the module's docstring.

**Form terms are withheld.** A few TEATER terms inside content facets name a kind of record rather than what a
document is about: the documentation (`dokumentace` and its kinds: fotografická and kresebná dokumentace,
archeologická mapa, videozáznam …), the site report (`nálezová správa`), `fotografie`, `kresba`, the kinds of map
(`stará`, `katastrální`, `geologická` … `mapa`) and the remote-sensing products (`ortofotomapa`, `satelitní snímek`,
`digitální model terénu`). A line naming one is mostly a caption or a reference to the archive's own documentation,
so these 22 terms, listed by TEATER id in `dm_run.FORM_TERMS`, are left out of the tree with everything below them;
the tree lists them under `withheld_form`. They stay in the vocabulary and in the generative prompt. Scripts
(`písmo`), written artefacts (`písemnost`) and the aerial methods (`letecké snímkování`) stay: a line names them
as content.
