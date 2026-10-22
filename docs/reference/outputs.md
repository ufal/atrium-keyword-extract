# The batch command line: outputs and scores

What `keywords.py` writes, and how to read each method's score. The service's response is described in
[service/README.md](../../service/README.md#json-response).

## Inputs and outputs

* **Input:** Directory of per-document CoNLL-U files (nlp-enrich's `UDP/`), or `*.teitok.xml` files.
* **Output 1:** Master table with keywords per document (e.g., `keywords_summary.csv`).
* **Output 2:** Per-document CSV files (e.g., `KW_PER_DOC/`).

```
KW_PER_DOC/
├── <docname1>_keywords.csv
├── <docname2>_keywords.csv
└── ...
```

Each per-document file contains two columns — **keyword** and **score** — sorted
by score in descending order.  The master summary uses the same column structure
as the original pipeline (`document_id`, `kw-1`, `score-1`, `kw-2`, `score-2`, …).

## Score interpretation by backend

**`legacy`** — raw lemma count; higher = more frequent in the document. Examples in directory: [KW_PER_DOC_L](../../data_samples/KW_PER_DOC_L) and summary file
[kw_summary_l.csv](../../data_samples/keywords_summary_l.csv).

| Score range | Interpretation                                           |
|-------------|----------------------------------------------------------|
| 1–5         | Common functional nouns, low informativeness             |
| 5–20        | Topic-representative vocabulary                          |
| > 20        | Dominant terms, likely named entities or domain headings |

**`yake`** — normalised inverse YAKE score, [0, 1] per document. Examples in directory: [KW_PER_DOC_Y](../../data_samples/KW_PER_DOC_Y) and summary file
[kw_summary_y.csv](../../data_samples/keywords_summary_y.csv).

| Score range | Semantic category | Interpretation                               |
|-------------|-------------------|----------------------------------------------|
| 0.0–0.2     | Noise floor       | Common words, low local relevance            |
| 0.2–0.6     | Context layer     | General vocabulary defining the broad topic  |
| 0.6–0.9     | Topic layer       | Specific nouns and verbs central to the text |
| 0.9–1.0     | Entity layer      | Rare terms, neologisms, named entities       |

**`keybert`** — cosine similarity to document centroid, [0, 1]. Examples in directory: [KW_PER_DOC_KB](../../data_samples/KW_PER_DOC_KB) and summary file
[kw_summary_kb.csv](../../data_samples/keywords_summary_kb.csv).

| Score range | Interpretation                   |
|-------------|----------------------------------|
| < 0.3       | Weakly related phrases           |
| 0.3–0.6     | Contextually relevant terms      |
| > 0.6       | Highly representative keyphrases |
