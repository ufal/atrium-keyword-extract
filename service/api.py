"""
service/api.py — FastAPI surface for atrium-keyword-extract.

One service for the stage "keywords", ``POST /extract_keywords`` (atrium-keyword-extract#1): the
record after nlp-enrich (or plain text) in, the document's and each page's keywords out, every one
with its method, score and rank. Two kinds are meant to run here, chosen by ``kind``:

* ``statistical`` — KeyBERT (the default), YAKE, or the legacy KER method of nlp-enrich's
  ``keywords.py``. Built.
* ``controlled`` — the LLM over the AMČR and TEATER vocabularies and the entity links to AMČR and
  AAT, which came from llm-enrich. Not in this release: a request for it alone is refused (501), and
  ``kind=both`` runs the statistical kind and says in ``kinds`` that the controlled one was skipped.

The typed contract (atrium-project#32 round 2): every route declares its response model and its
error statuses, so the committed ``service/openapi.json`` — attached to every release, and what the
AMČR pipeline generates its clients from — types every field. The models document the responses
(``response_model=None``): the bytes sent are what the handlers build, and
``tests/test_api_contract.py`` validates real responses against the published schema. Every JSON
success carries the run's Process Run Crate ``CreateAction`` as ``paradata`` (atrium-project#71).

The record is read, not written: the ``keywords`` block of the record is atrium-project#73, so this
release answers with the keywords in the response and leaves the record's blocks to the stages that
own them today. Regenerate the spec after an API change::

    python atrium_openapi.py export --app service.api:app --out service/openapi.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from .atrium_service import (
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
from atrium_paradata import ParadataLogger  # noqa: E402
from tool_limits import (  # noqa: E402
    LIMITS,
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
_SKIPPED_CATEGORIES = frozenset({"Trash", "Empty"})
_KER_POS = frozenset({"NOUN", "PROPN", "ADJ"})

#: Retry-After of a `busy` refusal: one extraction takes seconds to a minute.
_BUSY_RETRY_AFTER_S = 15


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
    """The kinds of keywords: which this release runs, which are still to come."""

    model_config = ConfigDict(extra="allow")

    available: List[str]
    planned: List[str]


class KeywordInfo(InfoBase):
    """`/info` of atrium-keyword-extract."""

    methods: Methods
    kinds: Kinds


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

# (12-factor XI) No basicConfig() here -- this module is imported by api's own __main__ and by
# tests; the entry point decides handlers and level. (issue #61)
logger = logging.getLogger(__name__)


def _warmup() -> None:
    """Load the KeyBERT model when it is the default, so the first request does not pay for it.

    Best effort: a service that cannot load it still starts and says so on the first request that
    needs it, which is a 500 with the cause, not a pod that never becomes ready.
    """
    if DEFAULT_KW_METHOD != "keybert":
        return
    try:
        kw._get_keybert_model(kw.DEFAULT_KEYBERT_MODEL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("keyword-extract: the KeyBERT model did not load at startup: %s", exc)


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
    description="The record after nlp-enrich, or a text → keywords of the document and of each page, with the "
    "method, score and rank of every keyword.",
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
    else:
        content = record.get("content")
        text = str((content or {}).get("text") or "").strip() if isinstance(content, dict) else ""
        if not text:
            raise HTTPException(
                422, "The record has no text: no `lines[].text` and no `content.text`."
            )
        doc.text = text
    doc.words = len(doc.text.split())
    return doc


def _doc_from_text(text: str) -> _Doc:
    doc = _Doc()
    doc.text = text.strip()
    doc.words = len(doc.text.split())
    if not doc.text:
        raise HTTPException(422, "The text is empty.")
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


def _paradata(
    logger_: ParadataLogger, sent: List[Dict[str, Any]], doc_id: str, found: Dict[str, Any]
) -> Dict[str, Any]:
    """The call's CreateAction: what it was sent, and the keywords it answered with as its result."""
    logger_.finalize()
    result = [
        atrium_rocrate.file_entity(
            f"{doc_id}.keywords.json",
            json.dumps(found, ensure_ascii=False, sort_keys=True).encode("utf-8"),
            media_type="application/json",
        )
    ]
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
) -> Dict[str, Any]:
    """The extraction of one request: the slot, the work, the response."""
    if kind == "controlled":
        raise HTTPException(
            501,
            "The controlled kind (the LLM over the AMČR and TEATER vocabularies) is not in this release of "
            "keyword-extract; ask for kind=statistical or kind=both.",
        )
    if method == "legacy" and not doc.lemmas:
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
    pd = ParadataLogger(
        PROGRAM, {"kind": kind, "method": method, "num_keywords": num_keywords}, paradata_dir=None
    )
    counts: Dict[str, Any] = {}
    try:
        loop = asyncio.get_event_loop()
        document_keywords, page_keywords = await loop.run_in_executor(
            None, _extract, doc, method, num_keywords, lang, per_page, counts
        )
    except kw.KeywordBackendError as exc:
        raise HTTPException(
            500, f"The {method} method is not available in this image: {exc}"
        ) from exc
    finally:
        _semaphore.release()
    component = {"keybert": "keybert", "yake": "yake", "legacy": "ker"}[method]
    pd.log_component(component)
    if method == "keybert":
        pd.log_component("sentence_transformers")
        pd.log_component("keybert_model")
    pd.log_success("keywords", len(document_keywords))
    pd.log_document_success()
    kw._note_keybert_limits(pd, counts)
    pages = [
        {"page": page["page"], "keywords": _keywords(method, found)}
        for page, found in zip(doc.pages if per_page else [], page_keywords, strict=True)
    ]
    kinds = [{"kind": "statistical", "status": "ok", "detail": None}]
    if kind == "both":
        kinds.append(
            {
                "kind": "controlled",
                "status": "skipped",
                "detail": "not in this release of keyword-extract (atrium-keyword-extract#1)",
            }
        )
    found = {"keywords": _keywords(method, document_keywords), "pages": pages}
    return {
        "doc_id": doc_id,
        "kind": kind,
        "method_requested": method,
        "method_used": method,
        **found,
        "kinds": kinds,
        "words": doc.words,
        "paradata": _paradata(pd, sent, doc_id, found),
        "limits_applied": pd.limits_applied,
    }


# ── endpoints ──────────────────────────────────────────────────────────────────────────────


@app.get(
    "/info",
    response_model=None,
    responses={200: {"model": KeywordInfo, "description": "Identity, limits, capabilities."}},
)
async def info() -> Dict[str, Any]:
    return build_info(
        app,
        SERVICE,
        limits=LIMITS,
        methods={
            "default": DEFAULT_KW_METHOD,
            "available": dict(_METHOD_HELP),
            "keybert_model": kw.DEFAULT_KEYBERT_MODEL,
        },
        kinds={"available": ["statistical"], "planned": ["controlled"]},
    )


attach_health(app, state=_state)

#: The statuses a call refuses or fails with (§4.4), beyond the app-wide 422/500.
_EXTRACT_ERRORS = (413, 429, 501)

_RECORD_HELP = (
    "The ATRIUM document record, after nlp-enrich: its `lines[].text` are read per page (lines categorised "
    "`Trash` or `Empty` are left out), and for the legacy method its `lines[].lemma` and `lines[].upos`. A "
    "record that cannot be opened is refused (422 `invalid_record`); one with no text, 422."
)
_METHOD_PARAM_HELP = (
    "The statistical method: `keybert`, `yake` or `legacy`. Absent: the server's default (`/info` "
    "`methods.default`, the `DEFAULT_KW_METHOD` setting)."
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
    kind: Kind = Form("both", description="`statistical`, `controlled` or `both`."),  # noqa: B008
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
    """`/extract_keywords` on a plain text (§4.3, the JSON sibling of the upload endpoint)."""
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
