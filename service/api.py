"""
service/api.py — FastAPI surface for atrium-keyword-extract.

One service for the stage "keywords", ``POST /extract_keywords`` (atrium-keyword-extract#1): the
record after nlp-enrich (or plain text) in, its keywords out. Two kinds run here, chosen by
``kind``, and stay apart in the response:

* ``statistical`` — KeyBERT (the default), YAKE, or the legacy KER method of nlp-enrich's
  ``keywords.py``: the document's and each page's keywords, every one with its method, score
  and rank.
* ``controlled`` — the LLM over the AMČR and TEATER vocabularies (atrium-keyword-extract#2), the
  successor of llm-enrich's ``/extract_keywords``: per qualifying line, the vocabulary term that
  describes it (``teater_category``, with the ``{source, id}`` records behind it) and the
  keywords found in it, as the record's ``enrichment`` block; and the entity links to AMČR and
  AAT (``entities[].pid``). The prompt is ``prompts/system_prompt.txt`` under the ``PROMPT_*``
  flags of ``llm_config.txt`` — the GPU research path's prompt — and the model is reached
  through an inference service (``LLM_BACKEND``: OpenRouter or a local Ollama), never loaded
  into this image (``llm_client_shared.py``). A deployment without a configured backend answers
  ``kind=controlled`` with 501, and ``kind=both`` reports the controlled kind as ``skipped``.

The typed contract (atrium-project#32 round 2): every route declares its response model and its
error statuses, so the committed ``service/openapi.json`` — attached to every release, and what the
AMČR pipeline generates its clients from — types every field. The models document the responses
(``response_model=None``): the bytes sent are what the handlers build, and
``tests/test_api_contract.py`` validates real responses against the published schema. Every JSON
success carries the run's Process Run Crate ``CreateAction`` as ``paradata`` (atrium-project#71).

The record: ``/extract_keywords`` returns the record sent, as ``document_json``, with
keyword-extract's blocks written and every other block as it came: ``keywords`` when the
statistical kind ran (atrium-project#73: the same document and page lists as the response), and
``enrichment`` (with its ``entities[].pid``) when the controlled kind contributed. The two kinds are
never merged into one list. Regenerate the spec after an API change::

    python atrium_openapi.py export --app service.api:app --out service/openapi.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .atrium_service import (
    AtriumDocument,
    AtriumHTTPError,
    CreateAction,
    InfoBase,
    LimitNote,
    ServiceState,
    add_cors,
    attach_error_handlers,
    attach_health,
    attach_inflight_middleware,
    attach_openapi_contract,
    build_info,
    busy,
    check_body_size,
    error_responses,
    operation_id,
    parse_record_part,
    read_tool_version,
    read_upload_bounded,
    serve_lifecycle,
)

# isort: split
# The repo root is on sys.path from here on (`python -m service.api` runs from it, and
# `python service/api.py` is bootstrapped below), so the repo-root modules are imported after it.
import sys  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import atrium_rocrate  # noqa: E402
import keywords as kw  # noqa: E402
import llm_client_shared as llm  # noqa: E402
import prompt_template  # noqa: E402
import tool_limits  # noqa: E402
from atrium_limits import LimitNotes  # noqa: E402
from atrium_paradata import ParadataLogger  # noqa: E402
from atrium_vocab import UNTRUSTWORTHY_LINE_CATEGORIES  # noqa: E402
from tool_limits import (  # noqa: E402
    LIMITS,
    LLM_MAX_CONSECUTIVE_ERRORS,
    LLM_MAX_NEW_TOKENS,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT,
    MAX_CONCURRENT_REQUESTS,
    MAX_DOCUMENT_WORDS,
    MAX_KEYWORDS,
    MAX_UPLOAD,
)

#: The tool id (/info `service`, the spec's `x-atrium-service`): the repository name.
SERVICE = "atrium-keyword-extract"

#: The id of the service this one grew out of (atrium-project#72, atrium-keyword-extract#1): the
#: statistical keywords were nlp-enrich's. Declared so the release gate accepts the changed id if a
#: baseline of it is ever compared (`atrium_openapi.py compare`).
PREVIOUS_SERVICE = "atrium-nlp-enrich"

#: The program id this tool stamps into records and paradata (`para_config.txt`): the successor of
#: `llm-enrich` in the record contract (`atrium_document.PROGRAM_SUCCESSORS`).
PROGRAM = "keyword-extract"

#: The server's default method. It is applied per request when a client sends none, and reported in
#: /info `methods.default`; it is NOT the spec's default for the `method` parameter, so the spec does
#: not change with this setting.
DEFAULT_KW_METHOD = os.environ.get("DEFAULT_KW_METHOD", "keybert")

Method = Literal["keybert", "yake", "legacy"]
Kind = Literal["statistical", "controlled", "both"]
Lang = Literal["cs"]

_KINDS = ("statistical", "controlled", "both")
_METHODS = ("keybert", "yake", "legacy")

#: What each method is, for /info and the parameter's description.
_METHOD_HELP = {
    "keybert": "embedding-based; best quality, uses a GPU when there is one; score is a cosine in [0, 1]",
    "yake": "unsupervised statistical, CPU only; score is the inverted YAKE score normalised per document to [0, 1]",
    "legacy": "KER: counts the lemmas of nouns, proper nouns and adjectives; needs `lines[].lemma`; score is a count",
}

#: Lines the quality stage labelled so are left out of the text: nothing is read from them (report §5).
#: The untrustworthy ones are the hub registry's (`atrium_vocab.UNTRUSTWORTHY_LINE_CATEGORIES`):
#: ocr-postprocess's `Trash`, and digital-convert's `Garbage` and `Inverted`, the lines of a born-digital
#: text layer that does not decode. `Empty` has nothing to read. Until 2026-10-05 only `Trash` and
#: `Empty` were left out here, so a born-digital record's mojibake was read as text. The controlled
#: kind leaves out the same lines (`llm_client_shared.should_process_line`).
_SKIPPED_CATEGORIES = frozenset(UNTRUSTWORTHY_LINE_CATEGORIES) | {"Empty"}
_KER_POS = frozenset({"NOUN", "PROPN", "ADJ"})

#: Retry-After of a `busy` refusal: one extraction takes seconds to a minute.
_BUSY_RETRY_AFTER_S = 15

#: The controlled kind's backends: the inference service the model runs in.
_BACKENDS = ("openrouter", "ollama")


# ── the typed contract ─────────────────────────────────────────────────────────────────────
# These models document the responses the handlers build; they do not filter them. A field the
# handlers always send has no default (required); one they send only sometimes defaults to None.
# Descriptions are published in service/openapi.json, so they are written for the client.


class Keyword(BaseModel):
    """One statistical keyword, with how it was found."""

    model_config = ConfigDict(extra="allow")

    keyword: str = Field(description="The keyword or phrase.")
    score: float = Field(
        description=(
            "The method's score, higher is more relevant. Scores mean different things per method "
            "(KeyBERT: a cosine; YAKE: normalised per document; KER: an occurrence count), so compare them "
            "only within one method and one list."
        )
    )
    method: str = Field(description="The method that produced it: `keybert`, `yake` or `legacy`.")
    rank: int = Field(description="Its place in its list, from 1.")


class PageKeywords(BaseModel):
    """The keywords of one page of the record."""

    model_config = ConfigDict(extra="allow")

    page: str = Field(description="The page, as the record's `lines[].page` has it.")
    keywords: List[Keyword]


class KindOutcome(BaseModel):
    """What happened to one kind of keywords in this call."""

    model_config = ConfigDict(extra="allow")

    kind: str = Field(description="`statistical` or `controlled`.")
    status: str = Field(
        description="`ok` (it ran), `skipped` (it was asked for with others and is not available) or `failed`."
    )
    detail: Optional[str] = Field(description="Why it did not run, or null.")


class CategoryId(BaseModel):
    """One vocabulary record a controlled label stands for."""

    model_config = ConfigDict(extra="allow")

    source: str = Field(description="`amcr` or `teater`.")
    id: str = Field(description="The record's id in its source (`HES-…` for AMČR).")


class EnrichmentItem(BaseModel):
    """The controlled keywords of one line: the vocabulary term that describes it, and what it says."""

    model_config = ConfigDict(extra="allow")

    page: Optional[str] = Field(
        None, description="The line's page, as the record's `lines[].page` has it."
    )
    line: Optional[int] = Field(
        None, description="The line's number within the page (`lines[].line`)."
    )
    extracted_keywords_cs: List[str] = Field(
        description="The archaeological terms found in the line, in Czech."
    )
    extracted_keywords_en: List[str] = Field(
        description="Their English translations, in the same order."
    )
    teater_category: str = Field(
        description=(
            "The vocabulary term the model chose for the line, by its label, or `Nerelevantní (meta-text)` for a "
            "line that is not archaeology (its keyword lists are then empty)."
        )
    )
    teater_category_ids: Optional[List[CategoryId]] = Field(
        None,
        description=(
            "Every AMČR/TEATER record the label stands for: its own, and those of the same label the vocabulary "
            "build merged into it. Empty for the meta-text label; absent when `EMIT_CATEGORY_IDS` is off."
        ),
    )
    confidence_score: float = Field(
        description="The model's confidence in `teater_category`, from 0 to 1."
    )
    citation: Optional[str] = Field(None, description="`[Source: <doc_id>, Page <page>]`.")


class Enrichment(BaseModel):
    """The controlled kind's result, as the record's `enrichment` block holds it."""

    model_config = ConfigDict(extra="allow")

    items: List[EnrichmentItem] = Field(
        description="One item per line the model labelled, in record order; empty when it found nothing."
    )


class ControlledRun(BaseModel):
    """How the controlled kind ran in this call."""

    model_config = ConfigDict(extra="allow")

    backend: str = Field(description="The inference service: `openrouter` or `ollama`.")
    model: str = Field(description="The model id (`<model>@<host>` for Ollama).")
    outcome: str = Field(
        description=(
            "`contributed` (items found), `empty` (the model was asked and found nothing), `not-asked` (no line "
            "passed the quality filter) or `failed` (every call failed)."
        )
    )
    stats: Dict[str, int] = Field(
        description=(
            "Lines `processed` (with a result), `attempted` (sent), `skipped_filter` (left out by the quality "
            "filter), `skipped_error` (failed), `truncated` (reply cut at LLM_MAX_NEW_TOKENS), `aborted` (1 when "
            "the document was given up, LLM_MAX_CONSECUTIVE_ERRORS) and then `unprocessed`."
        )
    )


class ExtractResponse(BaseModel):
    """The keywords of the document and of its pages, and the run's paradata."""

    model_config = ConfigDict(extra="allow")

    doc_id: str = Field(description="The record's `doc_id`, or the request's.")
    kind: str = Field(description="The kind asked for: `statistical`, `controlled` or `both`.")
    method_requested: str = Field(
        description="The method asked for (the server default when none was)."
    )
    method_used: Optional[str] = Field(
        description="The statistical method that ran, or null when none did."
    )
    keywords: List[Keyword] = Field(description="The document's statistical keywords, best first.")
    pages: List[PageKeywords] = Field(
        description="The same per page, in page order; empty when `per_page` is false or the input has no pages."
    )
    kinds: List[KindOutcome] = Field(description="One entry per kind that was asked for.")
    words: int = Field(description="The words the keywords were extracted from.")
    enrichment: Optional[Enrichment] = Field(
        None,
        description=(
            "The controlled keywords, when the controlled kind ran and the model was asked: the record's "
            "`enrichment` block."
        ),
    )
    controlled: Optional[ControlledRun] = Field(
        None, description="How the controlled kind ran, when it did."
    )
    document_json: Optional[AtriumDocument] = Field(
        None,
        description=(
            "`/extract_keywords`: the record sent, with keyword-extract's blocks written and every other block as "
            "it came — `keywords` when the statistical kind ran (the same document and page lists as above), and "
            "`enrichment` with `entities[].pid` when the controlled kind ran and the model was asked. Absent when "
            "neither kind wrote anything, and for `/extract_keywords_text`."
        ),
    )
    document_json_schema_error: Optional[str] = Field(
        None,
        description="Only when the returned record does not validate: the schema error (the sent record's).",
    )
    paradata: Optional[CreateAction] = Field(
        description="The call's provenance: its Process Run Crate `CreateAction` (atrium-project#71)."
    )
    limits_applied: List[LimitNote] = Field(
        description="Every limit that shaped the result without refusing it."
    )


class Methods(BaseModel):
    """The statistical methods: the server default (used when a request names none), and each one."""

    model_config = ConfigDict(extra="allow")

    default: str = Field(description="The server's `DEFAULT_KW_METHOD`.")
    available: Dict[str, str]
    keybert_model: str = Field(description="The sentence-transformers model KeyBERT uses.")


class Kinds(BaseModel):
    """The kinds of keywords: which this deployment runs now, which are still to come."""

    model_config = ConfigDict(extra="allow")

    available: List[str] = Field(
        description="`statistical`, and `controlled` once its LLM backend is configured (see `controlled`)."
    )
    planned: List[str] = Field(description="Kinds still to come; none since the controlled kind.")


class ControlledVocabulary(BaseModel):
    """How much of the vocabulary reaches the model."""

    model_config = ConfigDict(extra="allow")

    terms: int = Field(
        description="Terms in the vocabulary, with the meta-text label (themes withheld left out)."
    )
    prompt_terms: int = Field(description="Terms that fit the prompt (LLM_CONTEXT_WINDOW).")
    tool_version: Optional[str] = Field(
        None, description="The keyword-extract version that built it."
    )


class ControlledPrompt(BaseModel):
    """The prompt in force (`llm_config.txt`)."""

    model_config = ConfigDict(extra="allow")

    geo_guardrail: str = Field(
        description="`PROMPT_GEO_GUARDRAIL`: `strict`, `preference` or `off`."
    )
    vocabulary_grouping: str = Field(
        description="`PROMPT_VOCAB_GROUPING`: `facet_sub`, `facet` or `flat`."
    )


class ControlledInfo(BaseModel):
    """The controlled kind in this deployment."""

    model_config = ConfigDict(extra="allow")

    ready: bool = Field(description="Whether `kind=controlled` can run (else it is answered 501).")
    detail: Optional[str] = Field(description="Why it cannot, or null.")
    backend: Optional[str] = Field(description="`LLM_BACKEND`: `openrouter` or `ollama`.")
    model: Optional[str] = Field(description="The model id; null until configured.")
    vocabulary: Optional[ControlledVocabulary] = Field(description="Null until configured.")
    prompt: Optional[ControlledPrompt] = Field(description="Null until configured.")


class KeywordInfo(InfoBase):
    """`/info` of atrium-keyword-extract."""

    methods: Methods
    kinds: Kinds
    controlled: ControlledInfo


class ExtractTextRequest(BaseModel):
    """The body of `/extract_keywords_text`: a text, and the options `/extract_keywords` takes as form fields."""

    model_config = ConfigDict(extra="allow")

    text: str = Field(min_length=1, description="The text to extract keywords from.")
    doc_id: str = Field("document", description="The document's id, echoed in the response.")
    kind: Kind = Field("both", description="`statistical`, `controlled` or `both`.")
    method: Optional[Method] = Field(
        None, description="The statistical method; the server default when absent."
    )
    num_keywords: int = Field(
        20, ge=1, description="How many keywords to return; at most `max_keywords`."
    )
    lang: Lang = "cs"


class _Slots:
    """The MAX_CONCURRENT_REQUESTS extraction slots, read per call like every limit."""

    def __init__(self) -> None:
        self.running = 0

    def take(self) -> bool:
        if self.running >= MAX_CONCURRENT_REQUESTS.get():
            return False
        self.running += 1
        return True

    def release(self) -> None:
        self.running = max(0, self.running - 1)


_semaphore = _Slots()
_SERVICE_DIR = Path(__file__).resolve().parent
_state = ServiceState()

#: The controlled kind's warmed engine, or `{"error": reason, "backend": …}` when it is not available.
_controlled: Dict[str, Any] = {}

# (12-factor XI) No basicConfig() here -- this module is imported by api's own __main__ and by
# tests; the entry point decides handlers and level. (issue #61)
logger = logging.getLogger(__name__)


def _load_controlled() -> Dict[str, Any]:
    """Build the controlled kind's engine (blocking; at startup). Raises with the reason.

    The backend's connection settings are checked first, so a deployment that does not configure
    the controlled kind pays nothing for it: the vocabulary is loaded and the prompt rendered only
    for a configured backend. The environment wins over the config file (``LLM_CONFIG``,
    llm_config.txt), which also carries the ``PROMPT_*`` flags, ``VOCAB_PATH``,
    ``EMIT_CATEGORY_IDS`` and the line-filter settings the GPU path reads.
    """
    import requests

    from vocab_manager import VocabularyManager, vocabulary_provenance

    backend = os.getenv("LLM_BACKEND", "openrouter").strip().lower()
    config_file = tool_limits.config_path()
    config = llm.load_config(str(config_file)) if config_file.exists() else {}

    if backend == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY") or config.get("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL") or config.get("OPENROUTER_MODEL")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set (LLM_BACKEND=openrouter)")
        if not model:
            raise RuntimeError("OPENROUTER_MODEL is not set (LLM_BACKEND=openrouter)")
    elif backend == "ollama":
        from ollama_client import DEFAULT_OLLAMA_HOST

        host = (
            os.getenv("OLLAMA_HOST") or config.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST
        ).rstrip("/")
        model = os.getenv("OLLAMA_MODEL") or config.get("OLLAMA_MODEL")
        if not model:
            raise RuntimeError("OLLAMA_MODEL is not set (LLM_BACKEND=ollama)")
    else:
        raise RuntimeError(f"LLM_BACKEND={backend!r} is not one of {', '.join(_BACKENDS)}")

    vocab_path = llm.repo_path(
        os.getenv("VOCAB_PATH") or config.get("VOCAB_PATH", "data_samples/vocab/union_nested.json")
    )
    vocab_mgr = VocabularyManager(
        vocab_path=str(vocab_path),
        config_path=str(llm.repo_path(llm.TAXONOMY_CONFIG)),
    )
    # auto_sync=False: a missing vocabulary is a configuration fault, never a harvest.
    vocab_data = vocab_mgr.load(auto_sync=False)
    contradictions = llm.prompt_contradictions(vocab_mgr, config)
    if contradictions:
        raise RuntimeError("the prompt contradicts the vocabulary: " + "; ".join(contradictions))
    excluded = llm.excluded_prompt_themes(vocab_mgr)
    budget = tool_limits.vocab_prompt_budget_tokens()
    prompt, labels = llm.build_system_prompt(
        vocab_data, max_tokens=budget, excluded_themes=excluded, prompt_config=config
    )
    model_cls = llm.build_schema(labels)
    id_lookup, strip_map = llm.category_maps(vocab_data, labels, excluded)

    # The vocabulary cut (atrium-project#53): terms that do not fit the prompt budget are out of
    # the model's reach. A warning, /info `controlled.vocabulary`, and a standing note per call.
    total = llm.count_vocab_terms(vocab_data, excluded)
    notes = LimitNotes()
    cut = total - len(labels)
    if cut > 0:
        logger.warning(
            "controlled kind: %d of %d vocabulary terms left out of the prompt -- they do not fit its "
            "%d-token budget (LLM_CONTEXT_WINDOW %d - LLM_MAX_NEW_TOKENS - %d).",
            cut,
            total,
            budget,
            tool_limits.context_window(),
            tool_limits.PROMPT_OVERHEAD_TOKENS,
        )
        notes.note(
            "vocab_prompt_budget_tokens",
            "trimmed",
            cut,
            f"{cut} of {total} vocabulary terms were left out of the prompt: they do not fit its "
            f"{budget}-token budget; raise LLM_CONTEXT_WINDOW to include them",
            value=budget,
        )

    session = requests.Session()
    schema = model_cls.model_json_schema()
    if backend == "openrouter":
        from openrouter_client import _build_headers, make_chat_fn

        headers = _build_headers(
            api_key,
            os.getenv("OPENROUTER_SITE_URL"),
            os.getenv("OPENROUTER_APP_NAME", "atrium-keyword-extract"),
        )
        chat_fn = make_chat_fn(
            session, headers, model, schema, LLM_MAX_RETRIES.get(), LLM_TIMEOUT.get(), None
        )
        model_id = model
    else:
        from ollama_client import make_chat_fn

        chat_fn = make_chat_fn(
            session,
            host,
            model,
            schema,
            LLM_MAX_RETRIES.get(),
            LLM_TIMEOUT.get(),
            num_ctx=tool_limits.context_window(),
        )
        model_id = f"{model}@{host}"

    provenance = vocabulary_provenance(str(vocab_path))
    return {
        "backend": backend,
        "model": model_id,
        "prompt": prompt,
        "model_cls": model_cls,
        "chat_fn": chat_fn,
        "id_lookup": id_lookup,
        "strip_map": strip_map,
        "emit_ids": config.get("EMIT_CATEGORY_IDS", "true").lower() == "true",
        "filter_params": {
            "include_non_text": config.get("INCLUDE_NON_TEXT", "true").lower() == "true",
            "min_char_count": int(config.get("MIN_CHAR_COUNT", "3")),
            "min_char_non_text": int(config.get("MIN_CHAR_NON_TEXT", "8")),
            "min_alpha_ratio_non_text": float(config.get("MIN_ALPHA_RATIO_NON_TEXT", "0.40")),
        },
        "vocab_notes": notes,
        "vocab_components": list(provenance.get("components") or []),
        "vocabulary": {
            "terms": total,
            "prompt_terms": len(labels),
            "tool_version": (provenance.get("vocab") or {}).get("tool_version"),
        },
        "prompt_info": {
            "geo_guardrail": prompt_template.resolve_geo_guardrail(config),
            "vocabulary_grouping": prompt_template.resolve_grouping(config),
        },
        # Where the flat vocabulary artifacts sit, for entities[].pid: beside the vocabulary the
        # prompt was built from, so the two can never come from different builds.
        "vocab_dir": str(vocab_path.parent),
    }


def _controlled_ready() -> bool:
    return bool(_controlled.get("chat_fn")) and not _controlled.get("error")


def _controlled_unavailable() -> str:
    return str(_controlled.get("error") or "the LLM backend is not initialised")


def _warmup() -> None:
    """Load the KeyBERT model when it is the default, so the first request does not pay for it,
    and build the controlled kind's engine when its backend is configured.

    Best effort, both: a service that cannot load KeyBERT still starts and says so on the first
    request that needs it, which is a 500 with the cause; one whose controlled kind cannot be
    built still serves the statistical kind, and /info `controlled` says why.
    """
    if DEFAULT_KW_METHOD == "keybert":
        try:
            kw._get_keybert_model(kw.DEFAULT_KEYBERT_MODEL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("keyword-extract: the KeyBERT model did not load at startup: %s", exc)
    _controlled.clear()
    try:
        _controlled.update(_load_controlled())
        logger.info(
            "keyword-extract: the controlled kind is ready (%s, %s)",
            _controlled["backend"],
            _controlled["model"],
        )
    except Exception as exc:  # noqa: BLE001
        _controlled.update(
            {"error": str(exc), "backend": os.getenv("LLM_BACKEND", "openrouter").strip().lower()}
        )
        logger.info("keyword-extract: the controlled kind is not available: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _warmup)
    _state.warm = True
    # issue #55: installs the SIGTERM/SIGINT handling that flips /ready to 503 and, on shutdown,
    # waits for in-flight requests.
    async with serve_lifecycle(_state):
        yield


# DEFINITION OF THE APP
app = FastAPI(
    title="ATRIUM keyword-extract API",
    version=read_tool_version(_SERVICE_DIR.parent),
    description="The record after nlp-enrich, or a text → its statistical keywords (per document and page, with "
    "the method, score and rank of every keyword) and its controlled keywords (the AMČR/TEATER vocabulary term "
    "of each line, chosen by an LLM).",
    lifespan=lifespan,
    responses=error_responses(422, 500),
    generate_unique_id_function=operation_id,
    root_path_in_servers=False,
)
attach_inflight_middleware(app, _state)
# §4.4 error body {status, reason, detail} for every error (atrium-project#32 item 2, #53).
attach_error_handlers(app)
# The published spec: reason registry, record schema, service id and the id it replaces.
attach_openapi_contract(app, SERVICE, previous=PREVIOUS_SERVICE)
add_cors(app)

# ── helpers ────────────────────────────────────────────────────────────────────────────────


class _Doc:
    """The text of one document as the extraction methods read it."""

    def __init__(self) -> None:
        self.text = ""
        self.lemmas: List[str] = []
        self.pages: List[Dict[str, Any]] = []  # {"page", "text", "lemmas"}
        self.words = 0
        #: The controlled kind's rows: every line, the skipped ones too (they are context).
        self.rows: List[Dict[str, Any]] = []


def _lemma(line: Dict[str, Any]) -> Optional[str]:
    """The lemma KER counts for a line's token, or None (the line has no analysis for it)."""
    lemma = line.get("lemma")
    if (
        line.get("upos") in _KER_POS
        and isinstance(lemma, str)
        and len(lemma) > 1
        and lemma.isalpha()
    ):
        return lemma.lower()
    return None


def _doc_from_record(record: Dict[str, Any]) -> _Doc:
    """The document's text, and its pages', from the record's lines (or, failing those, its `content`)."""
    doc = _Doc()
    order: List[str] = []
    per_page: Dict[str, Dict[str, Any]] = {}
    for line in record.get("lines") or []:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "").strip()
        if not text or line.get("categ") in _SKIPPED_CATEGORIES:
            continue
        label = str(line.get("page")) if line.get("page") is not None else "1"
        entry = per_page.get(label)
        if entry is None:
            entry = per_page[label] = {"page": label, "parts": [], "lemmas": []}
            order.append(label)
        entry["parts"].append(text)
        lemma = _lemma(line)
        if lemma:
            entry["lemmas"].append(lemma)
    if order:
        doc.pages = [
            {"page": p, "text": " ".join(per_page[p]["parts"]), "lemmas": per_page[p]["lemmas"]}
            for p in order
        ]
        doc.text = " ".join(p["text"] for p in doc.pages)
        doc.lemmas = [lemma for p in doc.pages for lemma in p["lemmas"]]
        doc.rows = llm.record_rows(record)
    else:
        content = record.get("content")
        text = str((content or {}).get("text") or "").strip() if isinstance(content, dict) else ""
        if not text:
            raise HTTPException(
                422, "The record has no text: no `lines[].text` and no `content.text`."
            )
        doc.text = text
        doc.rows = llm.text_rows(text)
    doc.words = len(doc.text.split())
    return doc


def _doc_from_text(text: str) -> _Doc:
    doc = _Doc()
    doc.text = text.strip()
    doc.words = len(doc.text.split())
    if not doc.text:
        raise HTTPException(422, "The text is empty.")
    doc.rows = llm.text_rows(doc.text)
    return doc


def _keywords(method: str, pairs: Any) -> List[Dict[str, Any]]:
    return [
        {"keyword": phrase, "score": float(score), "method": method, "rank": rank}
        for rank, (phrase, score) in enumerate(pairs, start=1)
    ]


def _extract(doc: _Doc, method: str, num_keywords: int, lang: str, per_page: bool, counts: dict):
    """Run the method over the document and, when asked, over each page (a blocking call)."""
    texts = [doc.text]
    lemmas: Optional[List[List[str]]] = [doc.lemmas]
    if per_page and doc.pages:
        texts += [p["text"] for p in doc.pages]
        lemmas += [p["lemmas"] for p in doc.pages]
    results = kw.extract_from_texts(
        texts,
        method,
        num_keywords,
        lemmas=lemmas if method == "legacy" else None,
        lang=lang,
        limit_counts=counts,
    )
    return results[0], results[1:]


def _validate(kind: str, method: str, num_keywords: int) -> None:
    if kind not in _KINDS:
        raise HTTPException(422, f"kind must be one of {_KINDS}")
    if method not in _METHODS:
        raise HTTPException(422, f"method must be one of {_METHODS}")
    MAX_KEYWORDS.check(num_keywords)
    if num_keywords < 1:
        raise HTTPException(422, "num_keywords must be at least 1")


def _check_size(doc: _Doc) -> None:
    MAX_DOCUMENT_WORDS.check(doc.words)


def _record_stem(record: Optional[Dict[str, Any]]) -> str:
    """The file stem the sent record is written under while its block is added: its own `doc_id`
    when that is a plain file name, else ``record`` (the record keeps its id either way)."""
    doc_id = (record or {}).get("doc_id")
    if (
        isinstance(doc_id, str)
        and doc_id not in ("", ".", "..")
        and doc_id.isprintable()
        and "/" not in doc_id
        and "\\" not in doc_id
        and len(doc_id.encode("utf-8")) <= 200
    ):
        return doc_id
    return "record"


def _note_line_limits(stats: Dict[str, int], notes: LimitNotes) -> None:
    """The limits that shaped a controlled result, from ``enrich_rows``' counts."""
    if stats.get("truncated"):
        notes.note(
            LLM_MAX_NEW_TOKENS,
            "skipped",
            stats["truncated"],
            "line(s) whose reply was cut at LLM_MAX_NEW_TOKENS got no result",
        )
    if stats.get("aborted"):
        notes.note(
            LLM_MAX_CONSECUTIVE_ERRORS,
            "stopped",
            1,
            "the document was given up after LLM_MAX_CONSECUTIVE_ERRORS failed lines in a row; "
            f"{stats.get('unprocessed', 0)} line(s) after them were not sent",
        )


def _run_controlled(doc: _Doc, doc_id: str, engine: Dict[str, Any]):
    """The controlled kind over the document's rows (a blocking call): results, stats, errors."""
    errors: List[str] = []
    results, stats = llm.enrich_rows(
        doc.rows,
        doc_id,
        engine["chat_fn"],
        engine["prompt"],
        engine["model_cls"],
        **engine["filter_params"],
        max_consecutive_errors=LLM_MAX_CONSECUTIVE_ERRORS.get(),
        errors=errors,
    )
    llm.attach_category_ids(results, engine["id_lookup"], engine["strip_map"], engine["emit_ids"])
    return results, stats, errors


def _write_record(
    data: bytes,
    record: Dict[str, Any],
    pd: ParadataLogger,
    results: Optional[List[dict]] = None,
    engine: Optional[Dict[str, Any]] = None,
    keywords: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The sent record with keyword-extract's blocks written: ``keywords`` (the statistical kind,
    atrium-project#73) and ``enrichment`` with ``entities[].pid`` (the controlled kind's ``results``),
    whichever this call produced.

    Through ``llm_client_shared.write_document_record``, the repository's one record writer and
    its Layer D gate (atrium-project#10, D4): the record's own invalidity refuses it, an inherited
    one is passed through and said in ``document_json_schema_error``.
    """
    from atrium_document import FILE_SUFFIX, load_document

    stem = _record_stem(record)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / f"{stem}{FILE_SUFFIX}").write_bytes(data)
        try:
            path = llm.write_document_record(
                stem,
                results,
                Path(tmp),
                run_id=pd.run_id,
                run_uuid=pd.run_uuid,
                paradata_ref=pd.paradata_ref,  # the run_uuid: the service writes no file
                license_detail=pd.get_license_block(),
                vocab_dir=(engine or {}).get("vocab_dir"),
                keywords=keywords,
            )
        except RuntimeError as exc:
            # A record this service built wrong is a defect on this side: 500, never a 502.
            raise HTTPException(500, f"Document record rejected by its own schema: {exc}") from exc
        out: Dict[str, Any] = {"document_json": load_document(str(path))}
    error = llm.schema_gate(out["document_json"], f"{stem}{FILE_SUFFIX}")
    if error:
        logger.warning("the returned record %s does not validate: %s", stem, error)
        out["document_json_schema_error"] = error
    return out


def _paradata(
    logger_: ParadataLogger,
    sent: List[Dict[str, Any]],
    doc_id: str,
    found: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]],
    record: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """The call's CreateAction: what it was sent, and what it answered with as its result — the
    statistical keywords, the controlled ones, and the record blocks it wrote."""
    logger_.finalize()
    result: List[Dict[str, Any]] = []
    if found is not None:
        result.append(
            atrium_rocrate.file_entity(
                f"{doc_id}.keywords.json",
                json.dumps(found, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                media_type="application/json",
            )
        )
    if enrichment is not None:
        result.append(
            atrium_rocrate.file_entity(
                f"{doc_id}.enrichment.json",
                json.dumps(enrichment, ensure_ascii=False, sort_keys=True).encode("utf-8"),
                media_type="application/json",
            )
        )
    if record is not None:
        result.extend(
            atrium_rocrate.block_entities(atrium_rocrate.blocks_written(record, logger_.run_uuid))
        )
    return atrium_rocrate.create_action(logger_.record, inputs=sent, outputs=result)


async def _run(
    doc: _Doc,
    doc_id: str,
    kind: str,
    method: str,
    num_keywords: int,
    lang: str,
    per_page: bool,
    sent: List[Dict[str, Any]],
    record: Optional[Dict[str, Any]] = None,
    record_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """The extraction of one request: the slot, the work, the response.

    ``record``/``record_bytes``: the record sent to ``/extract_keywords``, which the controlled kind
    returns with its block; ``None`` for a text.
    """
    statistical = kind in ("statistical", "both")
    controlled = kind in ("controlled", "both")
    ready = _controlled_ready()
    if kind == "controlled" and not ready:
        raise HTTPException(
            501,
            "The controlled kind (the LLM over the AMČR and TEATER vocabularies) is not available in this "
            f"deployment: {_controlled_unavailable()}. Configure LLM_BACKEND and its model (service/README.md), "
            "or ask for kind=statistical.",
        )
    if statistical and method == "legacy" and not doc.lemmas:
        raise HTTPException(
            422,
            "The legacy (KER) method counts lemmas, and the input has none: send a record that nlp-enrich "
            "has annotated (`lines[].lemma`, `lines[].upos`), or another method.",
        )
    if not _semaphore.take():
        raise busy(
            f"Server busy: all {MAX_CONCURRENT_REQUESTS.get()} extraction slots are taken "
            "(MAX_CONCURRENT_REQUESTS).",
            retry_after_s=_BUSY_RETRY_AFTER_S,
        )
    engine = _controlled if (controlled and ready) else None
    config: Dict[str, Any] = {"kind": kind, "method": method, "num_keywords": num_keywords}
    if engine is not None:
        config.update({"backend": engine["backend"], "model": engine["model"]})
    pd = ParadataLogger(PROGRAM, config, paradata_dir=None)
    counts: Dict[str, Any] = {}
    document_keywords: List[Any] = []
    page_keywords: List[Any] = []
    controlled_out: Optional[tuple] = None
    try:
        loop = asyncio.get_event_loop()
        if statistical:
            try:
                document_keywords, page_keywords = await loop.run_in_executor(
                    None, _extract, doc, method, num_keywords, lang, per_page, counts
                )
            except kw.KeywordBackendError as exc:
                raise HTTPException(
                    500, f"The {method} method is not available in this image: {exc}"
                ) from exc
        if engine is not None:
            controlled_out = await loop.run_in_executor(None, _run_controlled, doc, doc_id, engine)
    finally:
        _semaphore.release()

    kinds: List[Dict[str, Any]] = []
    found: Optional[Dict[str, Any]] = None
    response: Dict[str, Any] = {}
    if statistical:
        component = {"keybert": "keybert", "yake": "yake", "legacy": "ker"}[method]
        pd.log_component(component)
        if method == "keybert":
            pd.log_component("sentence_transformers")
            pd.log_component("keybert_model")
        pd.log_success("keywords", len(document_keywords))
        kw._note_keybert_limits(pd, counts)
        pages = [
            {"page": page["page"], "keywords": _keywords(method, found_)}
            for page, found_ in zip(doc.pages if per_page else [], page_keywords, strict=True)
        ]
        found = {"keywords": _keywords(method, document_keywords), "pages": pages}
        kinds.append({"kind": "statistical", "status": "ok", "detail": None})

    enrichment: Optional[Dict[str, Any]] = None
    written: Optional[Dict[str, Any]] = None
    #: The controlled kind's results when they go into the record (None: it contributed nothing).
    contributed: Optional[List[dict]] = None
    if controlled and engine is None:
        kinds.append(
            {
                "kind": "controlled",
                "status": "skipped",
                "detail": f"not available in this deployment: {_controlled_unavailable()}",
            }
        )
    elif controlled_out is not None:
        results, stats, errors = controlled_out
        outcome = llm.classify_outcome(results, stats)
        notes = LimitNotes(engine["vocab_notes"].as_list())
        _note_line_limits(stats, notes)
        pd.note_limits(notes)
        if outcome == llm.OUTCOME_FAILED:
            failed = stats.get("skipped_error", 0)
            # A reply cut at the cap is a limit's doing, not the backend's: when every failure
            # was one, the controlled kind alone is refused as llm-enrich refused a cut document.
            cut = stats.get("truncated", 0) == failed
            if cut:
                detail = (
                    f"every reply ({failed} line(s)) was cut at {LLM_MAX_NEW_TOKENS.get()} tokens "
                    "(LLM_MAX_NEW_TOKENS) and none is used"
                )
            else:
                detail = f"every call to the LLM backend failed ({failed} line(s)): " + (
                    errors[0] if errors else "no reply"
                )
            if kind == "controlled":
                if cut:
                    raise LLM_MAX_NEW_TOKENS.exceeded(
                        None, detail=f"The model's {detail}; raise LLM_MAX_NEW_TOKENS."
                    )
                raise HTTPException(502, f"LLM backend error: {detail}")
            kinds.append({"kind": "controlled", "status": "failed", "detail": detail})
        else:
            if llm.contributes_document_record(results, stats):
                # The vocabularies are components of a run whose answers came from them.
                for component in engine["vocab_components"]:
                    pd.log_component(component)
                enrichment = llm.enrichment_block(doc_id, results)
                pd.log_success("enrichment", len(enrichment["items"]))
                contributed = results
            detail = None
            if outcome == llm.OUTCOME_NOT_ASKED:
                detail = "no line passed the quality filter; the model was not asked"
            kinds.append({"kind": "controlled", "status": "ok", "detail": detail})
        response["controlled"] = {
            "backend": engine["backend"],
            "model": engine["model"],
            "outcome": outcome,
            "stats": {k: int(v) for k, v in stats.items()},
        }

    # One record write for both kinds, each into its own block (atrium-project#73): the
    # statistical lists exactly as answered above, and the controlled results when they count.
    keywords_block = (
        {"document": found["keywords"], "pages": found["pages"]} if found is not None else None
    )
    if (
        record is not None
        and record_bytes is not None
        and (keywords_block or contributed is not None)
    ):
        written = await asyncio.get_event_loop().run_in_executor(
            None, _write_record, record_bytes, record, pd, contributed, engine, keywords_block
        )
    pd.log_document_success()
    if enrichment is not None:
        response["enrichment"] = enrichment
    if written is not None:
        response.update(written)
    record_out = (written or {}).get("document_json")
    return {
        "doc_id": doc_id,
        "kind": kind,
        "method_requested": method,
        "method_used": method if statistical else None,
        "keywords": (found or {}).get("keywords", []),
        "pages": (found or {}).get("pages", []),
        "kinds": kinds,
        "words": doc.words,
        **response,
        "paradata": _paradata(pd, sent, doc_id, found, enrichment, record_out),
        "limits_applied": pd.limits_applied,
    }


# ── endpoints ──────────────────────────────────────────────────────────────────────────────


@app.get(
    "/info",
    response_model=None,
    responses={200: {"model": KeywordInfo, "description": "Identity, limits, capabilities."}},
)
async def info() -> Dict[str, Any]:
    ready = _controlled_ready()
    return build_info(
        app,
        SERVICE,
        limits=LIMITS,
        methods={
            "default": DEFAULT_KW_METHOD,
            "available": dict(_METHOD_HELP),
            "keybert_model": kw.DEFAULT_KEYBERT_MODEL,
        },
        kinds={
            "available": ["statistical", "controlled"] if ready else ["statistical"],
            "planned": [],
        },
        controlled={
            "ready": ready,
            "detail": None if ready else _controlled_unavailable(),
            "backend": _controlled.get("backend"),
            "model": _controlled.get("model"),
            "vocabulary": _controlled.get("vocabulary"),
            "prompt": _controlled.get("prompt_info"),
        },
    )


attach_health(app, state=_state)

#: The statuses a call refuses or fails with (§4.4), beyond the app-wide 422/500. 501: the controlled
#: kind alone, in a deployment without an LLM backend; 502: that backend failed every call.
_EXTRACT_ERRORS = (413, 429, 501, 502)

_RECORD_HELP = (
    "The ATRIUM document record, after nlp-enrich: its `lines[].text` are read per page (lines categorised "
    "`Trash`, `Garbage`, `Inverted` or `Empty` are left out), and for the legacy method its `lines[].lemma` and "
    "`lines[].upos`. The controlled kind reads the same lines one by one, each with its neighbours as context, and "
    "returns the record with its `enrichment` block. A record that cannot be opened is refused (422 "
    "`invalid_record`); one with no text, 422."
)
_METHOD_PARAM_HELP = (
    "The statistical method: `keybert`, `yake` or `legacy`. Absent: the server's default (`/info` "
    "`methods.default`, the `DEFAULT_KW_METHOD` setting)."
)
_KIND_HELP = (
    "`statistical`, `controlled` or `both`. `controlled` needs the deployment's LLM backend (`/info` "
    "`controlled.ready`); with `both`, a controlled kind that cannot run is reported in `kinds`."
)


@app.post(
    "/extract_keywords",
    response_model=None,
    responses={
        200: {"model": ExtractResponse, "description": "The keywords, per document and per page."},
        **error_responses(*_EXTRACT_ERRORS),
    },
)
async def extract_keywords(
    document_json: UploadFile = File(  # noqa: B008
        ..., description=_RECORD_HELP, json_schema_extra={"contentMediaType": "application/json"}
    ),
    kind: Kind = Form("both", description=_KIND_HELP),  # noqa: B008
    method: Optional[Method] = Form(None, description=_METHOD_PARAM_HELP),  # noqa: B008
    num_keywords: int = Form(
        20, ge=1, description="How many keywords per list; at most `max_keywords`."
    ),
    lang: Lang = Form("cs"),  # noqa: B008
    per_page: bool = Form(
        True, description="Also extract per page, from the record's `lines[].page`."
    ),
):
    data = await read_upload_bounded(document_json, MAX_UPLOAD.get(), "document_json")
    record = parse_record_part(data, "document_json")
    if record is None:
        raise AtriumHTTPError(422, "The document_json part is empty.", reason="invalid_record")
    chosen = method or DEFAULT_KW_METHOD
    _validate(kind, chosen, num_keywords)
    doc = _doc_from_record(record)
    _check_size(doc)
    sent = [
        atrium_rocrate.file_entity(
            document_json.filename or "record.document.json", data, media_type="application/json"
        )
    ]
    return await _run(
        doc,
        str(record.get("doc_id") or "document"),
        kind,
        chosen,
        num_keywords,
        lang,
        per_page,
        sent,
        record=record,
        record_bytes=data,
    )


@app.post(
    "/extract_keywords_text",
    response_model=None,
    responses={
        200: {"model": ExtractResponse, "description": "The document's keywords."},
        **error_responses(*_EXTRACT_ERRORS),
    },
)
async def extract_keywords_text(payload: ExtractTextRequest, request: Request):
    """`/extract_keywords` on a plain text (§4.3, the JSON sibling of the upload endpoint).

    The controlled kind reads the text's non-empty lines as the lines of one page.
    """
    # The body is bounded like an upload (atrium-project#53).
    await check_body_size(request, MAX_UPLOAD.get(), "Request body")
    chosen = payload.method or DEFAULT_KW_METHOD
    _validate(payload.kind, chosen, payload.num_keywords)
    doc = _doc_from_text(payload.text)
    _check_size(doc)
    sent = [
        atrium_rocrate.file_entity(
            "text.txt", payload.text.encode("utf-8"), media_type="text/plain"
        )
    ]
    return await _run(
        doc, payload.doc_id, payload.kind, chosen, payload.num_keywords, payload.lang, False, sent
    )


if __name__ == "__main__":
    import logging
    import os
    import sys

    import uvicorn

    # (12-factor XI) Logs are an event stream: emit to stdout and let the supervisor route them. The
    # library modules only getLogger(); this is the one place allowed to configure handlers. The
    # format string is the same in every ATRIUM service. (issue #61)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    # (12-factor VII) The service exports itself by binding a port, and which port is configuration:
    # PORT and HOST are read here, and service/healthcheck.py probes the same PORT. (issue #58)
    reload = os.getenv("RELOAD", "false").strip().lower() in ("true", "1", "yes", "on")

    # uvicorn needs an IMPORT STRING to respawn workers on reload; everywhere else the app OBJECT is
    # correct and strictly better (a string under `python -m service.api` would run this module twice).
    _app_ref = f"{__spec__.name}:app" if reload and __spec__ is not None else app

    uvicorn.run(
        _app_ref,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=reload,
        # (12-factor IX) Disposability: bounds uvicorn's wait for in-flight requests;
        # serve_lifecycle() adds its own drain on top. (issue #55)
        timeout_graceful_shutdown=int(os.getenv("GRACEFUL_SHUTDOWN_S", "20")),
    )
