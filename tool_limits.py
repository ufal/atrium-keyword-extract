"""tool_limits.py — every limit atrium-keyword-extract has (atrium-project#53, factor III).

One declaration, read by the service (``service/api.py``), by the extraction code it runs
(``keywords.py`` for the statistical kind; ``llm_client_shared.py`` with ``openrouter_client.py``
or ``ollama_client.py`` for the controlled kind), and reported by ``GET /info`` (``limits`` and
``limits_meta``). Each limit is an environment setting; a malformed value stops the process at
startup, naming the variable (``atrium_limits.LimitConfigError``). ``.env.example`` and
``service/README.md``'s ``## Limits`` table list the same set; ``tests/test_limits_contract.py``
checks that they agree.

**The context window's default depends on the LLM backend** (atrium-project#53, D3): 128000 for
``openrouter``, 32000 for ``ollama`` — the same default each batch client's CLI uses
(:data:`BACKEND_CONTEXT_WINDOW`). The environment wins, then ``CONTEXT_WINDOW`` in the config
file ``LLM_CONFIG`` names (llm_config.txt), then that default. It is read when this module is
imported, so a malformed value fails the start instead of being recorded as a warm-up failure.
The LLM limits came with llm-enrich's engine (atrium-digital-convert 31534d5,
atrium-keyword-extract#1).

What happens over each limit — refused (with the HTTP status), or processed in full with a
``limits_applied`` note (with the effect) — is said beside it.

Standard library only (``atrium_limits`` is the hub's canonical module at the repo root):
the batch CLIs import this too.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

from atrium_limits import LimitConfigError, LimitSet, limit, upload_limit

_REPO_ROOT = Path(__file__).resolve().parent

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
#: Extractions running at once. Each one holds the embedding model, a CPU or a run of LLM
#: calls for its whole run; a request with every slot taken → 429 ``busy`` with Retry-After.
MAX_CONCURRENT_REQUESTS = limit(
    "MAX_CONCURRENT_REQUESTS", 2, unit="requests", key="max_concurrent_requests", minimum=1
)

# ── KeyBERT ─────────────────────────────────────────────────────────────────────────────
#: Words per KeyBERT chunk: a longer document is embedded in overlapping chunks and its
#: keywords merged → ``split`` note.
KEYBERT_CHUNK_WORDS = limit("KEYBERT_CHUNK_WORDS", 400, unit="words", minimum=1)
#: Words two consecutive KeyBERT chunks share.
KEYBERT_CHUNK_OVERLAP = limit("KEYBERT_CHUNK_OVERLAP", 50, unit="words")

# ── the controlled kind: the LLM ────────────────────────────────────────────────────────
#: The context window each backend's client assumes (its CLI's ``--context-window``
#: default, and the service's default for ``LLM_CONTEXT_WINDOW``).
BACKEND_CONTEXT_WINDOW: Dict[str, int] = {"openrouter": 128000, "ollama": 32000}
#: Tokens reserved for formatting on top of the reply (``LLM_MAX_NEW_TOKENS``) when the
#: prompt budget is computed. Not a setting: it is the prompt template's own overhead.
PROMPT_OVERHEAD_TOKENS = 512


def llm_backend() -> str:
    """The backend ``LLM_BACKEND`` selects (``openrouter`` by default)."""
    return (os.environ.get("LLM_BACKEND") or "openrouter").strip().lower()


#: The model's context window, in tokens. It sizes the vocabulary prompt: terms that do not
#: fit are left out → standing ``trimmed`` note. Sent to Ollama as ``num_ctx``.
LLM_CONTEXT_WINDOW = limit(
    "LLM_CONTEXT_WINDOW",
    BACKEND_CONTEXT_WINDOW.get(llm_backend(), 32000),
    unit="tokens",
    minimum=1024,
)
#: Most tokens one reply may have (OpenRouter ``max_tokens``, Ollama ``num_predict``). A
#: reply cut at it is never used: the line gets no result → ``skipped`` note (a batch run's
#: document mode refuses the document).
LLM_MAX_NEW_TOKENS = limit("LLM_MAX_NEW_TOKENS", 2048, unit="tokens", minimum=16, status=422)
#: Per-request timeout of one LLM call, in seconds; a timeout is retried.
LLM_TIMEOUT = limit("LLM_TIMEOUT", 300, unit="s", minimum=1)
#: Attempts of one LLM call; only a timeout, a connection error, HTTP 429 or 5xx is
#: retried. Once they run out the line is an error.
LLM_MAX_RETRIES = limit("LLM_MAX_RETRIES", 3, unit="attempts", minimum=1)
#: Consecutive failed lines after which the document is given up → ``stopped`` note (the
#: lines before it keep their results).
LLM_MAX_CONSECUTIVE_ERRORS = limit("LLM_MAX_CONSECUTIVE_ERRORS", 10, unit="errors", minimum=1)


def keybert_max_seq_tokens() -> Optional[int]:
    """Tokens of one chunk the KeyBERT encoder reads (its ``max_seq_length``); a longer
    chunk is embedded from its start → ``trimmed`` note. ``None`` until the model is loaded
    in this process (the service loads it at startup when ``DEFAULT_KW_METHOD=keybert``)."""
    keywords = sys.modules.get("keywords")
    if keywords is None:
        return None
    return keywords.keybert_window(getattr(keywords, "_keybert_model_instance", None))[1]


def config_path() -> Path:
    """The config file the controlled kind reads (``LLM_CONFIG``, default llm_config.txt)."""
    path = Path(os.environ.get("LLM_CONFIG") or "llm_config.txt")
    return path if path.is_absolute() or path.exists() else _REPO_ROOT / path


def config_values() -> Dict[str, str]:
    """``{LLM_CONTEXT_WINDOW: raw}`` when the config file sets ``CONTEXT_WINDOW``.

    Same KEY=VALUE reading as ``llm_client_shared.load_config`` (blank lines and ``#``
    comments skipped, one matched pair of quotes removed), without its dependencies.
    """
    try:
        lines = config_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "CONTEXT_WINDOW":
            value = value.strip()
            for quote in ('"', "'"):
                if len(value) >= 2 and value[0] == value[-1] == quote:
                    value = value[1:-1]
            return {LLM_CONTEXT_WINDOW.env: value} if value else {}
    return {}


def context_window() -> int:
    """The effective context window: environment, config file, backend default."""
    return LIMITS.get(LLM_CONTEXT_WINDOW.key)


def reserved_tokens() -> int:
    """Tokens kept free for the reply and the prompt's formatting."""
    return LLM_MAX_NEW_TOKENS.get() + PROMPT_OVERHEAD_TOKENS


def vocab_prompt_budget_tokens() -> int:
    """Tokens the vocabulary prompt may take (estimated at 4 characters per token)."""
    return context_window() - reserved_tokens()


LIMITS = LimitSet(
    MAX_UPLOAD,
    MAX_DOCUMENT_WORDS,
    MAX_KEYWORDS,
    MAX_CONCURRENT_REQUESTS,
    KEYBERT_CHUNK_WORDS,
    KEYBERT_CHUNK_OVERLAP,
    LLM_CONTEXT_WINDOW,
    LLM_MAX_NEW_TOKENS,
    LLM_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_MAX_CONSECUTIVE_ERRORS,
    config=config_values,
)
LIMITS.derived(
    "keybert_max_seq_tokens",
    keybert_max_seq_tokens,
    unit="tokens",
    derived_from=["KEYBERT_MODEL (kw_config.txt)"],
)
LIMITS.derived(
    "vocab_prompt_budget_tokens",
    vocab_prompt_budget_tokens,
    unit="tokens",
    derived_from=["LLM_CONTEXT_WINDOW", "LLM_MAX_NEW_TOKENS"],
)

if vocab_prompt_budget_tokens() <= 0:
    raise LimitConfigError(
        f"LLM_CONTEXT_WINDOW is {context_window()} tokens, which leaves no room for the prompt "
        f"after LLM_MAX_NEW_TOKENS ({LLM_MAX_NEW_TOKENS.get()}) and {PROMPT_OVERHEAD_TOKENS} tokens "
        "of formatting; raise the first or lower the second."
    )
