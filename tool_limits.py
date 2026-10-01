"""tool_limits.py — every limit atrium-keyword-extract has (atrium-project#53, factor III).

One declaration, read by the service (``service/api.py``) and by the extraction code it
runs (``keywords.py``), and reported by ``GET /info`` (``limits`` and ``limits_meta``). Each
limit is an environment setting; a malformed value stops the process at startup, naming the
variable (``atrium_limits.LimitConfigError``). ``.env.example`` and ``service/README.md``'s
``## Limits`` table list the same set; ``tests/test_limits_contract.py`` checks that they
agree.

What happens over each limit — refused (with the HTTP status), or processed in full with a
``limits_applied`` note (with the effect) — is said beside it.

Standard library only (``atrium_limits`` is the hub's canonical module at the repo root):
the batch CLI imports this too.
"""

from __future__ import annotations

import sys
from typing import Optional

from atrium_limits import LimitSet, limit, upload_limit

# ── the request ─────────────────────────────────────────────────────────────────────────
#: §4.5 upload limit, per uploaded part (the record) and for the whole `/extract_keywords_text`
#: body. Over it → 413 ``limit_exceeded``.
MAX_UPLOAD = upload_limit(10)
#: Words one document may have (the record's lines, or the text). Over it → 413. The statistical
#: methods run on the whole text, so this bounds the work of one request, not the quality of
#: its result.
MAX_DOCUMENT_WORDS = limit(
    "MAX_DOCUMENT_WORDS", 200000, unit="words", key="max_document_words", minimum=1, status=413
)
#: Keywords one request may ask for (`num_keywords`). Over it → 422 ``limit_exceeded``.
MAX_KEYWORDS = limit(
    "MAX_KEYWORDS", 100, unit="keywords", key="max_keywords", minimum=1, status=422
)
#: Extractions running at once. Each one holds the embedding model or a CPU for its whole
#: run; a request with every slot taken → 429 ``busy`` with Retry-After.
MAX_CONCURRENT_REQUESTS = limit(
    "MAX_CONCURRENT_REQUESTS", 2, unit="requests", key="max_concurrent_requests", minimum=1
)

# ── KeyBERT ─────────────────────────────────────────────────────────────────────────────
#: Words per KeyBERT chunk: a longer document is embedded in overlapping chunks and its
#: keywords merged → ``split`` note.
KEYBERT_CHUNK_WORDS = limit("KEYBERT_CHUNK_WORDS", 400, unit="words", minimum=1)
#: Words two consecutive KeyBERT chunks share.
KEYBERT_CHUNK_OVERLAP = limit("KEYBERT_CHUNK_OVERLAP", 50, unit="words")


def keybert_max_seq_tokens() -> Optional[int]:
    """Tokens of one chunk the KeyBERT encoder reads (its ``max_seq_length``); a longer
    chunk is embedded from its start → ``trimmed`` note. ``None`` until the model is loaded
    in this process (the service loads it at startup when ``DEFAULT_KW_METHOD=keybert``)."""
    keywords = sys.modules.get("keywords")
    if keywords is None:
        return None
    return keywords.keybert_window(getattr(keywords, "_keybert_model_instance", None))[1]


LIMITS = LimitSet(
    MAX_UPLOAD,
    MAX_DOCUMENT_WORDS,
    MAX_KEYWORDS,
    MAX_CONCURRENT_REQUESTS,
    KEYBERT_CHUNK_WORDS,
    KEYBERT_CHUNK_OVERLAP,
)
LIMITS.derived(
    "keybert_max_seq_tokens",
    keybert_max_seq_tokens,
    unit="tokens",
    derived_from=["KEYBERT_MODEL (kw_config.txt)"],
)
