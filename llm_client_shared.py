"""
llm_client_shared.py — the torch-free front-end of the controlled kind: the LLM over the AMČR and
TEATER vocabularies, through an inference service rather than local weights.

Shared by the service's controlled kind (``service/api.py``, ``kind=controlled|both``) and the
two batch clients (``openrouter_client.py``, ``ollama_client.py``). Their dependency set is
requirements_remote.txt: no torch, no transformers, no vLLM — the GPU path is ``llm_run.py``.

What it shares with that GPU path, and how:

* **The prompt is not duplicated.** The instruction text is ``prompts/system_prompt.txt``,
  rendered by ``prompt_template`` (standard library only) under the same ``PROMPT_*`` flags of
  ``llm_config.txt``, and the vocabulary is flattened and laid out by
  ``prompt_template.vocabulary_terms`` / ``vocabulary_block`` (``PROMPT_VOCAB_GROUPING``) —
  the functions ``llm_run.build_system_prompt`` calls. The copy of this module that came from
  atrium-llm-enrich (atrium-digital-convert 31534d5) kept the prompt as a string literal: it
  still sent the strict geographic guardrail after the vocabulary had reinstated the
  geographic and cultural branches under the relaxed one (atrium-keyword-extract#2, M11/M12),
  ignored every ``PROMPT_*`` flag, and emitted neither ``teater_category_ids`` nor the bare
  label of a bracketed homonym (C4). :func:`category_maps` and :func:`attach_category_ids`
  are the post-inference half ``llm_run._attach_category_ids`` has.
* **The mechanics are duplicated, by hand**, because ``llm_utils.py`` imports torch and sets
  PYTORCH_CUDA_ALLOC_CONF at import: config loading, row reading, the line-quality filter, the
  context window, lenient JSON validation. Change the filter or the context window there, mirror
  it here.
* Token counts are estimated at 4 characters per token: no tokenizer is loaded here.

Two modes. **Line mode** — one call per qualifying line, the target line marked inside its
context — reads a CSV, a ``*.teitok.xml`` or an ATRIUM record (``*.document.json``: its
``lines[]``, which is how the service and the batch clients read the record after nlp-enrich).
**Document mode** — one call per ``.md``/``.txt`` document — has its own instruction text
(:data:`_DOC_SYSTEM_HEADER`), because the template describes the line task; its vocabulary is
the template's.
"""

import csv
import enum
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from pydantic import BaseModel, Field, ValidationError

import prompt_template
from api_util import teitok_read
from api_util.teitok_read import doc_id_from_path  # noqa: F401  (re-exported for clients)
from atrium_vocab import UNTRUSTWORTHY_LINE_CATEGORIES

#: The repository this module runs from: where a relative path from a config falls back to.
_REPO_ROOT = Path(__file__).resolve().parent

#: The taxonomy the vocabulary was built from (``VocabularyManager``'s ``config_path``): which
#: themes reach the prompt, and the geographic guardrail the prompt must agree with.
TAXONOMY_CONFIG = "data_samples/taxonomy_config.json"


def repo_path(value: Any) -> Path:
    """A configured path: absolute, or found from the working directory, or the repository's.

    ``VOCAB_PATH`` and the taxonomy are written relative to the checkout, and a run from another
    directory used to miss the taxonomy silently: ``VocabularyManager`` fell back to its built-in
    one, which declares no guardrail, and the prompt check then compared against the wrong rules.
    """
    path = Path(value)
    return path if path.is_absolute() or path.exists() else _REPO_ROOT / path


# ---------------------------------------------------------------------------
# 1. Config loader — duplicated from llm_utils.load_config
# ---------------------------------------------------------------------------


def _unquote(value: str) -> str:
    """Strip one matched pair of surrounding quotes from a config value.

    Config files here are shell-flavoured KEY=VALUE, and both quoted and bare
    values occur in the wild — this repo's own llm_config.txt writes them bare,
    while generated configs (the cross-repo e2e workflow, deployment templates)
    quote paths out of shell habit. Without this, a quoted value keeps its quote
    characters and every path built from it is wrong by two bytes.

    That is not hypothetical: `VOCAB_PATH="/workspace/work/…json"` parsed to a
    path that could not exist, VocabularyManager fell through to auto-sync, and
    the run produced a single-term enum that rejected every correct answer the
    model gave. atrium-nlp-enrich's sibling parser (api_util/summarize_nt_udp.py)
    has always stripped quotes; the two repos consume configs written by the same
    hand, so differing on this is a trap rather than a design choice.

    Only a MATCHED outer pair is removed, so a Windows path or a value with an
    apostrophe inside survives untouched.
    """
    for quote in ('"', "'"):
        if len(value) >= 2 and value.startswith(quote) and value.endswith(quote):
            return value[1:-1]
    return value


def load_config(config_path: str = "llm_config.txt") -> Dict[str, str]:
    """Parse a KEY=VALUE config file, ignoring blank lines and # comments."""
    config: Dict[str, str] = {}
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}") from None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                config[key.strip()] = _unquote(value.strip())
    return config


#: Config keys that are credentials: never written to paradata, which is published with
#: the record (atrium-project#71). llm_config.txt may hold OPENROUTER_API_KEY (the clients read
#: it there) or HF_TOKEN (llm_run.py does), and every run used to log the whole file.
_SECRET_KEY = re.compile(r"(?:API_KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)


def redact_secrets(config: Dict[str, str]) -> Dict[str, str]:
    """``config`` without its credentials (a key ending in ``API_KEY``, ``TOKEN``, ``SECRET``
    or ``PASSWORD``), for the paradata."""
    return {key: value for key, value in config.items() if not _SECRET_KEY.search(key)}


# ---------------------------------------------------------------------------
# 2. Token-count approximation — no tokenizer/torch dependency
# ---------------------------------------------------------------------------

# Rough, tokenizer-free estimate. Czech/English archival text averages
# roughly 4 characters per token across the model families this repo has
# targeted so far (Qwen/Gemma/Llama tokenizers). Good enough for vocabulary-
# truncation decisions; NOT precise enough for exact context-limit or
# billing arithmetic — callers that need that should use the provider's own
# token-counting endpoint if one exists.
_CHARS_PER_TOKEN_ESTIMATE = 4


def approx_token_count(text: str) -> int:
    """Character-based token estimate. See _CHARS_PER_TOKEN_ESTIMATE."""
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


# Chat callable both clients implement: takes the [system, user] message
# list, returns the raw text of the model's reply (expected to be JSON, but
# validate_llm_output() tolerates near-miss JSON — see there).
ChatFn = Callable[[List[Dict[str, str]]], str]


class ReplyTruncated(RuntimeError):
    """The provider cut the reply at the output-token cap (``LLM_MAX_NEW_TOKENS``):
    OpenRouter ``finish_reason``, Ollama ``done_reason`` == ``"length"``.

    Such a reply is never used: its JSON is incomplete, and a repaired prefix would be a
    silent truncation of the result (atrium-project#53). Not retried — at temperature 0
    the same request is cut at the same place. ``max_new_tokens`` is the cap it hit.
    """

    def __init__(self, message: str, max_new_tokens: int) -> None:
        super().__init__(message)
        self.max_new_tokens = max_new_tokens


class RequestRefused(RuntimeError):
    """The provider answered a client error (HTTP 4xx other than 429). Not retried —
    the same request would be refused again — and the provider's reply is kept in the
    message, so the caller sees why (atrium-project#53)."""


def http_error_detail(resp: Any, limit: int = 500) -> str:
    """``HTTP <code>: <start of the body>`` for an error reply."""
    try:
        body = (resp.text or "")[:limit]
    except Exception:  # noqa: BLE001 - a body that cannot be read is still an error
        body = ""
    return f"HTTP {resp.status_code}: {body}".rstrip(": ")


# ---------------------------------------------------------------------------
# 3. Line-quality filter — duplicated from llm_utils._should_process_line
# ---------------------------------------------------------------------------

#: Lines never sent to the model. The untrustworthy ones are the hub registry's
#: (`atrium_vocab.UNTRUSTWORTHY_LINE_CATEGORIES`): ocr-postprocess's `Trash`, and
#: digital-convert's `Garbage` and `Inverted`, the lines of a born-digital text layer that
#: does not decode — which reach this module in a record, never in llm_utils' CSV/TEITOK
#: inputs, so only this copy names them. `Empty` has nothing to read.
_ALWAYS_SKIP_CATEG = frozenset(UNTRUSTWORTHY_LINE_CATEGORIES) | {"Empty"}
_NOISE_CATEG = _ALWAYS_SKIP_CATEG | {"Non-text"}


def row_quality(row: dict) -> Optional[float]:
    """The row's ``quality_score``, or None when it has none (a TEITOK row, a CSV without the
    column). None means "unknown", not "worst": ``should_process_line`` then skips the
    quality bands and only the length rules apply."""
    value = row.get("quality_score")
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def should_process_line(
    text: str,
    categ: str,
    quality_score: Optional[float],
    include_non_text: bool,
    min_char_count: int,
    min_char_non_text: int,
    min_alpha_ratio_non_text: float,
) -> Tuple[bool, str]:
    # Quality bands only for rows that carry a score. A TEITOK document (or a table without
    # the column) has none; read as 0.0, every such row became "Trash" and a .teitok.xml
    # input enriched nothing (atrium-llm-enrich#13, P5.1).
    if quality_score is not None:
        if quality_score < 0.40:
            categ = "Trash"
        elif quality_score < 0.70 and categ != "Trash":
            categ = "Noisy"

    if not text:
        return False, "empty text"

    if categ in _ALWAYS_SKIP_CATEG:
        return False, f"categ={categ!r} (quality={quality_score})"

    if categ == "Non-text":
        if not include_non_text:
            return False, "Non-text excluded by config"
        char_count = len(text)
        if char_count < min_char_non_text:
            return False, f"Non-text too short ({char_count} < {min_char_non_text} chars)"
        alpha_count = sum(c.isalpha() for c in text)
        alpha_ratio = alpha_count / char_count if char_count else 0.0
        if alpha_ratio < min_alpha_ratio_non_text:
            return False, f"Non-text alpha ratio too low ({alpha_ratio:.2f})"
        return True, ""

    if not categ:
        if len(text) < min_char_count:
            return False, f"text too short ({len(text)} < {min_char_count} chars) [unknown categ]"
        return True, ""

    if len(text) < min_char_count:
        return False, f"text too short ({len(text)} < {min_char_count} chars)"

    return True, ""


# ---------------------------------------------------------------------------
# 4. Row reading — duplicated from llm_utils.read_input_rows, plus the record
# ---------------------------------------------------------------------------

#: The suffix of an ATRIUM record. Matched on the FULL name: the suffix of
#: "CTX1.document.json" is ".json".
RECORD_SUFFIX = ".document.json"


def is_record_input(path: Any) -> bool:
    """Whether ``path`` names an ATRIUM record (``*.document.json``)."""
    return str(path).lower().endswith(RECORD_SUFFIX)


def record_rows(record: Dict[str, Any]) -> List[dict]:
    """The rows line mode reads from an ATRIUM record: one per ``lines[]`` entry, in order.

    The record after nlp-enrich is this stage's input, so its lines are the rows: ``text``,
    ``categ`` and ``quality_score`` as the quality stage wrote them (a line without a score is
    *unknown* quality, see :func:`row_quality`), and the page twice — ``page_num`` for the
    context window, which compares it, and ``page_label`` for the result, which must cite the
    record's own label (``"iv"`` coerced to an int would cite a page that does not exist).
    """
    rows: List[dict] = []
    for line in record.get("lines") or []:
        if not isinstance(line, dict):
            continue
        page = "" if line.get("page") is None else str(line.get("page"))
        rows.append(
            {
                "text": str(line.get("text") or ""),
                "page_num": page,
                "page_label": page,
                "line_num": "" if line.get("line") is None else str(line.get("line")),
                "categ": str(line.get("categ") or ""),
                "quality_score": line.get("quality_score"),
            }
        )
    return rows


def text_rows(text: str) -> List[dict]:
    """The rows of a plain text: each non-empty line, on one page labelled ``"1"``.

    No category and no score, so only the length rules of the quality filter apply.
    """
    lines = [raw.strip() for raw in text.splitlines() if raw.strip()]
    return [
        {
            "text": line,
            "page_num": "1",
            "page_label": "1",
            "line_num": str(number),
            "categ": "",
            "quality_score": None,
        }
        for number, line in enumerate(lines, start=1)
    ]


def read_input_rows(input_path: Path) -> List[dict]:
    """Reads rows from a CSV, a TEITOK XML document or an ATRIUM record."""
    if input_path.name.lower().endswith(".teitok.xml"):
        return [
            {
                "text": r["text"],
                "page_num": str(r.get("page_num", "")),
                "line_num": str(r.get("line_num", "")),
                "categ": "",  # Falls back to plain text handling
                "quality_score": None,  # unknown: TEITOK carries no line quality
            }
            for r in teitok_read.read_teitok_rows(str(input_path))
        ]
    if is_record_input(input_path):
        record = json.loads(Path(input_path).read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError(f"{input_path.name}: an ATRIUM record is a JSON object")
        return record_rows(record)
    with open(input_path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 5. Context-window builder — duplicated from llm_utils.get_context_window
# ---------------------------------------------------------------------------


def get_context_window(rows: List[dict], center_idx: int, window: int = 2) -> str:
    """Build a text snippet around ``rows[center_idx]`` for the LLM user prompt.
    See llm_utils.get_context_window — identical logic, duplicated here."""
    center_row = rows[center_idx]
    center_page = center_row.get("page_num", center_row.get("page", None))
    start = max(0, center_idx - window)
    end = min(len(rows), center_idx + window + 1)

    parts: List[str] = []

    if center_idx > window + 2:
        parts.append("--- GLOBAL DOCUMENT HEADER ---")
        added = 0
        for row in rows:
            if row.get("categ", "").strip() not in _NOISE_CATEG:
                pg = row.get("page_num", row.get("page", 0))
                ln = row.get("line_num", row.get("line", 0))
                parts.append(f"    [P{pg} L{ln}] {row.get('text', '').strip()}")
                added += 1
                if added >= 2:
                    break

    current_section = "Unknown Section"
    for i in range(center_idx - 1, -1, -1):
        if rows[i].get("categ", "").strip() in {"Header", "Heading"}:
            current_section = rows[i].get("text", "").strip()
            break

    parts.append(f"--- CURRENT SECTION: {current_section} ---")
    parts.append("--- LOCAL CONTEXT WINDOW ---")

    for i in range(start, end):
        row = rows[i]
        row_page = row.get("page_num", row.get("page", None))
        categ = row.get("categ", "").strip()

        if row_page != center_page and i != center_idx:
            continue
        if i != center_idx and categ in _NOISE_CATEG:
            continue

        text = row.get("text", "").strip()
        pg = row_page
        ln = row.get("line_num", row.get("line", 0))

        if i == center_idx:
            parts.append(f"<target_line> >>> [P{pg} L{ln}] {text} </target_line>")
        else:
            parts.append(f"    [P{pg} L{ln}] {text}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 6. Lenient JSON validation — duplicated from llm_utils.validate_llm_output
# ---------------------------------------------------------------------------


def validate_llm_output(
    result_json: str, EnrichmentModel: type, file_id: str, page_num: int, line_num: int
) -> dict:
    """Validate and sanitize LLM JSON output against a Pydantic model."""
    try:
        semantic_data = EnrichmentModel.model_validate_json(result_json)
    except ValidationError:
        try:
            raw_dict = json.loads(result_json, strict=False)
            if "confidence_score" in raw_dict:
                try:
                    val = float(raw_dict["confidence_score"])
                    raw_dict["confidence_score"] = min(1.0, max(0.0, val))
                except (ValueError, TypeError):
                    pass
            semantic_data = EnrichmentModel.model_validate(raw_dict)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(
                f"[{file_id}] Persistent validation error P{page_num} L{line_num}: {exc}"
            ) from exc

    dump_data = semantic_data.model_dump()

    if hasattr(semantic_data, "category_name"):
        dump_data["teater_category"] = semantic_data.category_name()
    else:
        dump_data["teater_category"] = dump_data.get("teater_category", "")

    if dump_data.get("teater_category") == META_TERM:
        dump_data["extracted_keywords_cs"] = []
        dump_data["extracted_keywords_en"] = []

    return dump_data


# ---------------------------------------------------------------------------
# 7. Schema + system prompt — the schema duplicated from llm_run.build_schema;
#    the prompt rendered by prompt_template, as llm_run.build_system_prompt does,
#    with approx_token_count() above in place of a tokenizer.
# ---------------------------------------------------------------------------

#: The one administrative label the prompt offers before every vocabulary term
#: (prompt_template.META_TEXT_TERM). It is not part of any vocabulary file, so an enum
#: consisting of it alone proves that zero real terms survived loading + theme filtering.
META_TERM = prompt_template.META_TEXT_TERM["cs"]

#: ``{source, id}`` records behind one label (``teater_category_ids``).
IdList = List[Dict[str, str]]


def _assert_vocabulary_reached_the_model(term_names: List[str]) -> None:
    """Reject a term list that carries no actual vocabulary.

    The empty case was always caught. The meta-only case was not, and it is the
    one that actually happened: a vocabulary that loads but whose every term is
    filtered out yields a one-value enum, and pydantic then rejects each correct
    answer the model returns with a validation error. The run completes, exits 0,
    and reports "records enriched: 0" — a silent quality collapse that reads like
    a model failure. Both cases mean the same thing and neither is a judgement
    call about size: the check is exact, not a threshold.
    """
    if not term_names:
        raise ValueError("term_names is empty — vocabulary failed to load or was fully truncated.")
    if set(term_names) <= {META_TERM}:
        raise ValueError(
            f"Vocabulary contains no terms beyond the fixed {META_TERM!r} category, so "
            "every enrichment would be forced to that one label. Check VOCAB_PATH points "
            "at a built vocabulary (see vocab_build.py) and that taxonomy_config.json "
            "does not set in_prompt=false on every theme."
        )


def build_schema(term_names: List[str]) -> type:
    _assert_vocabulary_reached_the_model(term_names)

    TermEnum = enum.Enum("TermEnum", {f"term_{i}": name for i, name in enumerate(term_names)})

    class ConstrainedEnrichment(BaseModel):
        extracted_keywords_cs: List[str] = Field(
            ...,
            description=(
                "Key Czech archaeological terms, methods, or objects found ONLY in "
                "the text marked with (>>>). "
                "DO NOT copy terms from the THEMATIC VOCABULARY list. "
                "If no relevant archaeological terms appear in the target line, "
                "return []. "
                "If teater_category is 'Nerelevantní (meta-text)', MUST be []. "
                "Do not extract names of researchers or administrative words. "
                "Prefer normalised multi-word phrases over isolated single words."
            ),
        )
        extracted_keywords_en: List[str] = Field(
            ...,
            description=(
                "Accurate English translations of extracted_keywords_cs. "
                "Do not copy Czech words unchanged."
            ),
        )
        teater_category: TermEnum = Field(
            ...,
            description="The single most relevant category from the thematic vocabulary.",
        )
        confidence_score: float = Field(
            ...,
            ge=0.0,
            le=1.0,
            description=(
                "Confidence that the selected teater_category is correct. "
                "1.0 — unambiguous match, no interpretation required. "
                "0.7–0.9 — reasonable but non-obvious match. "
                "0.5–0.7 — multiple categories could apply. "
                "< 0.5 — forced guess. "
                "Do NOT output 1.0 uniformly — this field is used for filtering."
            ),
        )

        def category_name(self) -> str:
            return self.teater_category.value

    return ConstrainedEnrichment


def excluded_prompt_themes(vocab_mgr: Any) -> Set[str]:
    """Themes to withhold from the model, derived from taxonomy_config.json.

    A theme is withheld when its ``in_prompt`` flag is false; absent the flag the
    default is the historical one — everything except "Other" reaches the model.

    The trailing guard is not redundant. VocabularyManager falls back to a
    BUILT-IN taxonomy when data_samples/taxonomy_config.json is missing, and that
    fallback declares no "Other" theme at all — so a bare comprehension would
    produce an empty exclusion set and silently start injecting the ~779-term
    Other bucket into every prompt. A config that is simply silent about Other
    must mean "unchanged", never "enable it"; enabling it takes an explicit
    ``"Other": {"in_prompt": true}``.

    Accepts any object exposing ``themes()`` (i.e. a VocabularyManager); typed
    loosely so this module keeps its no-heavy-imports property.
    """
    try:
        themes = vocab_mgr.themes()
    except AttributeError:  # pragma: no cover — a manager predating themes()
        return {"other"}
    excluded = {
        name.lower()
        for name, cfg in themes.items()
        if isinstance(cfg, dict) and not cfg.get("in_prompt", name.lower() != "other")
    }
    if "other" not in {name.lower() for name in themes}:
        excluded.add("other")
    return excluded


def count_vocab_terms(vocab_data: dict, excluded_themes: Optional[Set[str]] = None) -> int:
    """How many terms the prompt builders would inject before any truncation — what a
    caller compares their surviving term list against to say how many were left out
    (atrium-project#53). The meta-text sentinel counts: it is offered like any term."""
    return len(prompt_template.vocabulary_terms(vocab_data, excluded_themes))


def prompt_contradictions(
    vocab_mgr: Any, prompt_config: Optional[Dict[str, str]] = None
) -> List[str]:
    """Every way the configured prompt and the vocabulary contradict each other.

    ``vocab_build.py`` refuses to BUILD a vocabulary whose geographic guardrail disagrees with
    the wording ``PROMPT_GEO_GUARDRAIL`` selects (issue #6, O4/C1); this is the same check at
    the other end, for a run whose config differs from the one the build read — a strict
    guardrail sent with the reinstated geographic terms forbids what the enum offers. Empty
    when they agree. Accepts any object exposing ``geo_guardrail_problems()``.
    """
    return list(
        vocab_mgr.geo_guardrail_problems(prompt_template.guardrail_text(prompt_config or {}))
    )


def _fit_vocab_prompt(
    header: str,
    terms: List[dict],
    max_tokens: int,
    skip_truncation: bool = False,
    footer: str = "",
    grouping: Optional[str] = None,
    verbose: bool = False,
) -> Tuple[str, List[dict]]:
    """Render ``terms`` between ``header`` and ``footer`` in the ``grouping`` layout,
    binary-searching for the largest prefix that fits ``max_tokens`` if the full vocabulary
    doesn't. Returns the prompt and the surviving term dicts. ``verbose=True`` prints the
    ``[vocab]``/``[WARN]`` progress lines (the line prompt's behaviour); the document prompt
    renders silently."""

    def _render(term_list: List[dict]) -> str:
        return header + prompt_template.vocabulary_block(term_list, grouping) + footer

    full_prompt = _render(terms)
    token_count = approx_token_count(full_prompt)

    if verbose:
        print(f"[vocab] {len(terms)} terms, ~{token_count} tokens total (char-based estimate)")

    if skip_truncation:
        if verbose:
            print(f"[vocab] Injecting full vocabulary (~{token_count} tokens, no truncation).")
        return full_prompt, list(terms)

    if token_count <= max_tokens:
        if verbose:
            print("[vocab] Full vocabulary fits within (approximate) token budget.")
        return full_prompt, list(terms)

    if verbose:
        print(
            f"[WARN] Vocabulary (~{token_count} tokens) exceeds budget "
            f"({max_tokens}). Binary-searching for largest fitting prefix…"
        )

    lo, hi = 0, len(terms)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if approx_token_count(_render(terms[:mid])) <= max_tokens:
            lo = mid
        else:
            hi = mid

    surviving = list(terms[:lo])
    surviving_prompt = _render(surviving)

    if verbose:
        print(
            f"[vocab] Truncated to {len(surviving)} terms "
            f"(~{approx_token_count(surviving_prompt)} tokens)."
        )
    return surviving_prompt, surviving


def build_system_prompt(
    vocab_data: dict,
    max_tokens: int,
    skip_truncation: bool = False,
    excluded_themes: Optional[Set[str]] = None,
    prompt_config: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """The line-mode system prompt and the labels it offers, in that order.

    The prompt ``llm_run.build_system_prompt`` sends, with an estimated token budget: the
    blocks of ``prompts/system_prompt.txt`` that ``prompt_config``'s ``PROMPT_*`` flags select
    (``prompt_template.render``; the template file itself is ``PROMPT_TEMPLATE``), the vocabulary
    laid out per ``PROMPT_VOCAB_GROUPING``, then the examples. Terms that do not fit
    ``max_tokens`` are dropped from the end, the order being the facet priority order, which
    is load-bearing. ``prompt_config=None`` renders the template's defaults — the strict
    guardrail among them — so a caller holding llm_config.txt passes it.

    ``excluded_themes`` names the themes to withhold, lower-cased (see
    :func:`excluded_prompt_themes`); ``None`` withholds only "Other".

    Returns ``(prompt, labels)``; :func:`category_maps` gives what the labels stand for.
    """
    config = prompt_config or {}
    header, footer = prompt_template.render(config)
    terms = prompt_template.vocabulary_terms(vocab_data, excluded_themes)
    prompt, surviving = _fit_vocab_prompt(
        header,
        terms,
        max_tokens,
        skip_truncation,
        footer=footer,
        grouping=prompt_template.resolve_grouping(config),
        verbose=True,
    )
    return prompt, [t["cs"] for t in surviving]


def category_maps(
    vocab_data: dict,
    labels: Sequence[str],
    excluded_themes: Optional[Set[str]] = None,
) -> Tuple[Dict[str, IdList], Dict[str, str]]:
    """What the labels a prompt offered stand for (issue #6, B2/B3/C4).

    ``id_lookup`` maps a label to every ``{source, id}`` record behind it — its own, plus each
    one the dedup discarded onto it (M7) — for ``teater_category_ids``. ``strip_map`` maps a
    label the build qualified to tell homonyms apart (``"zámek (sídlo elity)"``) back to its bare
    form (``"zámek"``), the label a record carries. Only ``labels`` are mapped: a term the
    budget left out of the prompt was never offered, so nothing may claim to back it.
    """
    offered = set(labels)
    terms = [
        t
        for t in prompt_template.vocabulary_terms(vocab_data, excluded_themes)
        if t["cs"] in offered
    ]
    id_lookup = {t["cs"]: t["ids"] for t in terms if t.get("ids")}
    strip_map = {t["cs"]: t["bare_cs"] for t in terms if t.get("bare_cs")}
    return id_lookup, strip_map


def attach_category_ids(
    results: List[dict],
    id_lookup: Dict[str, IdList],
    strip_map: Dict[str, str],
    emit_ids: bool = True,
) -> None:
    """The post-inference pass — ``llm_run._attach_category_ids``, duplicated (that module
    imports torch). Mutates each result's ``enrichment`` in place, in both modes.

    ``teater_category_ids`` is looked up under the label the model selected, which may carry
    a qualifier; the label is then rewritten to its bare form, so a qualifier never leaves
    this stage. A source label that carries brackets of its own (``"GPS (navigační systém)"``)
    is not in ``strip_map`` and stays as it is. ``emit_ids=False`` is ``EMIT_CATEGORY_IDS=false``.
    """
    for record in results:
        enrichment = record.get("enrichment")
        if not isinstance(enrichment, dict):
            continue
        category = enrichment.get("teater_category", "")
        if emit_ids:
            enrichment["teater_category_ids"] = id_lookup.get(category, [])
        bare = strip_map.get(category)
        if bare is not None:
            enrichment["teater_category"] = bare


_DOC_SYSTEM_HEADER = (
    "You are an expert archaeological data extractor. "
    "You will be given a WHOLE DOCUMENT (rendered from a digitized archival "
    "record). Scan it and extract EVERY passage with direct archaeological "
    "significance — sites, finds, methods, periods, materials.\n"
    "For EACH such passage, return one item with:\n"
    "  - locator: a short verbatim snippet (max 8 words) copied EXACTLY from "
    "the document, unique enough to locate the passage (prefer including the "
    "'## Page N' heading text nearest above it if the document has page "
    "headings).\n"
    "  - page: the page number of that passage, read from the nearest "
    "'<!-- PAGE_BREAK: pg_N -->' or '## Page N' marker ABOVE it (just the number/"
    "label, e.g. 3); null if the document has no page markers.\n"
    # Spelled out rather than delegated. This used to read "same meaning as the
    # single-line task" — a task this prompt never shows the model, because the
    # document-level prompt is built from _DOC_SYSTEM_HEADER alone. So the four
    # remaining fields were specified nowhere the model could see, and it invented
    # a shape: `page` as an integer, the keyword lists as one comma-joined string,
    # and a `teater_category` of its own wording. atrium-project run 34123820218 is
    # that, five times over, on a document it had otherwise read correctly.
    "  - extracted_keywords_cs: a JSON ARRAY of Czech terms found in the passage, "
    'e.g. ["sonda", "kulturní vrstva"]. NEVER a single comma-separated string. '
    "Empty array if none.\n"
    "  - extracted_keywords_en: a JSON ARRAY of English translations of "
    "extracted_keywords_cs, same length and order. NEVER a single "
    "comma-separated string.\n"
    # The heading warning is not padding. prompt_template.vocabulary_block() emits the
    # vocabulary (in the shipped `facet_sub` layout) as
    # `--- {theme} / {sub} ---` section headings over `- cs (en)` bullets, and in
    # atrium-project run 34125325468 the model answered 'Artefact / druh předmětu' for
    # every item — a heading this very renderer had printed. Nothing in the prompt had
    # ever said which of the two kinds of line is selectable.
    "  - teater_category: ONE value copied EXACTLY, character for character, from "
    "the THEMATIC VOCABULARY list below — including its diacritics and any "
    "parenthesised qualifier. Do not translate it, do not shorten it, do not "
    "invent a category.\n"
    "    The vocabulary is printed as sections. A line of the form "
    "'--- Something / Something ---' is a SECTION HEADING and is NOT a category: "
    "never return one. Only the entries listed under a heading are categories, and "
    "each is printed as '- <czech term> (<english gloss>)'. Return ONLY the Czech "
    "term, without the English gloss and without its surrounding parentheses: from "
    "'- sonda (trench)' the correct value is exactly 'sonda'.\n"
    "    If no listed term fits the passage, the passage is not an extraction "
    "target: omit the item entirely.\n"
    "  - confidence_score: a number between 0.0 and 1.0.\n"
    "The document may contain HTML-comment layout cues (e.g. "
    "'<!-- BBOX: … -->', '<!-- FONT: … -->'); use them as positional hints but "
    "never extract or quote them as content.\n"
    "Administrative text, tables of contents, headings, author names, and "
    "literature references are NOT extraction targets — skip them entirely "
    "rather than emitting a 'Nerelevantní (meta-text)' item for each. "
    "If the document has no archaeologically relevant passages, return an "
    "empty items list.\n"
    "You MUST respond ONLY with a valid JSON object matching the requested "
    "schema.\n\n"
    "THEMATIC VOCABULARY:\n"
)


#: The document-level counterpart of the template's `examples` block.
#:
#: The line prompt has ended in worked examples since it was written;
#: build_document_system_prompt() passed no footer at all, so the whole-document
#: prompt shipped without a single worked example. A prompt that only DESCRIBES a JSON
#: shape and never shows one is how atrium-project run 34123820218 got five items whose
#: content was right and whose every field was the wrong type. The example is the cheap
#: half of the fix; the tolerant parse in _repair_document_response() is the other half.
#:
#: `page` is quoted here deliberately — it is a STRING in the schema so labels like "iv"
#: or "A-1" survive, and an unquoted 1 is exactly what the model returned instead.
_DOC_EXAMPLES_FOOTER = (
    "\nEXAMPLE OF THE REQUIRED OUTPUT SHAPE:\n\n"
    "For a document containing:\n"
    "  ## Page 2\n"
    "  Sonda II odkryla cast valoveho telesa.\n"
    "  Nalezeny zlomky keramiky z raneho stredoveku.\n\n"
    "Correct output:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "locator": "Sonda II odkryla cast",\n'
    '      "page": "2",\n'
    '      "extracted_keywords_cs": ["sonda", "valové těleso"],\n'
    '      "extracted_keywords_en": ["trench", "rampart body"],\n'
    '      "teater_category": "<an exact term from the vocabulary above>",\n'
    '      "confidence_score": 0.9\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    'Note: "page" is a STRING, both keyword fields are ARRAYS, and '
    '"teater_category" is copied verbatim from the vocabulary. A document with '
    'nothing archaeological in it returns {"items": []}.\n'
)


def build_document_schema(term_names: List[str]) -> type:
    """Whole-document variant of build_schema(): a wrapper model holding a
    list of located enrichment items, instead of one object per target line.
    Used by run_document_level() for BACKEND=openrouter/ollama .md input."""
    _assert_vocabulary_reached_the_model(term_names)

    TermEnum = enum.Enum("TermEnum", {f"term_{i}": name for i, name in enumerate(term_names)})

    class LocatedEnrichment(BaseModel):
        locator: str = Field(
            ...,
            description="Short verbatim snippet (max 8 words) copied exactly from the document.",
        )
        page: Optional[str] = Field(
            None,
            description=(
                "Page number/label of the located passage, taken from the nearest "
                "'<!-- PAGE_BREAK: pg_N -->' or '## Page N' marker above it "
                "(a string so labels like 'iv' or 'A-1' are allowed). Null if unknown."
            ),
        )
        extracted_keywords_cs: List[str] = Field(default_factory=list)
        extracted_keywords_en: List[str] = Field(default_factory=list)
        teater_category: TermEnum = Field(
            ...,
            description="The single most relevant category from the thematic vocabulary.",
        )
        confidence_score: float = Field(..., ge=0.0, le=1.0)

        def category_name(self) -> str:
            return self.teater_category.value

    class DocumentEnrichment(BaseModel):
        items: List[LocatedEnrichment] = Field(default_factory=list)

    #: The enum's values, hung on the class so _repair_document_response() can resolve a
    #: near-miss category without reaching back into pydantic's internals. Assigned after
    #: class creation so pydantic does not mistake it for a field.
    DocumentEnrichment.allowed_terms = tuple(term_names)
    return DocumentEnrichment


def build_document_system_prompt(
    vocab_data: dict,
    max_tokens: int,
    skip_truncation: bool = False,
    excluded_themes: Optional[Set[str]] = None,
    prompt_config: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """The document-mode prompt: the whole-document instruction header, then the same
    vocabulary as :func:`build_system_prompt` (same terms, same ``PROMPT_VOCAB_GROUPING``
    layout, same truncation). The template's line-task blocks do not render here."""
    config = prompt_config or {}
    terms = prompt_template.vocabulary_terms(vocab_data, excluded_themes)
    prompt, surviving = _fit_vocab_prompt(
        _DOC_SYSTEM_HEADER,
        terms,
        max_tokens,
        skip_truncation,
        footer=_DOC_EXAMPLES_FOOTER,
        grouping=prompt_template.resolve_grouping(config),
        verbose=False,
    )
    return prompt, [t["cs"] for t in surviving]


#: Formats each branch of the dispatch reads. Document mode is also spelled
#: `_DOC_INPUT_EXTENSIONS` inside each client, where it selects the branch; the sets here
#: answer a different question — whether ANY branch can read the file at all. Line mode
#: also reads `*.teitok.xml` and records (`*.document.json`), matched on the full name.
#:
#: PDF and DOCX are not read here. llm-enrich converted them to Markdown first, with the
#: born-digital converter that stayed in atrium-digital-convert; in this repository the
#: record is the input — convert with digital-convert, and send its record (after
#: nlp-enrich) instead.
DOC_LEVEL_EXTENSIONS = frozenset({".md", ".txt"})
LINE_LEVEL_EXTENSIONS = frozenset({".csv"})


def is_document_level(path: Any) -> bool:
    """Whether ``path`` is read in document mode (one call for the whole file)."""
    return Path(path).suffix.lower() in DOC_LEVEL_EXTENSIONS


def has_reader(path: Path) -> bool:
    """Whether some branch of the client dispatch can read this file.

    Nothing checked this before, and the dispatch has no else: a file that is neither
    document-level nor line-level simply fell through to the line-level branch, whatever
    it was. csv.DictReader does not object to being handed JSON — it just yields nothing —
    so an unreadable input cost a full CI round trip to diagnose instead of one line of
    output (atrium-project run 34039707673).
    """
    name = str(path).lower()
    return (
        is_document_level(path)
        or Path(path).suffix.lower() in LINE_LEVEL_EXTENSIONS
        or name.endswith(".teitok.xml")
        or is_record_input(path)
    )


#: The four outcomes one controlled-kind pass over one document can have (llm-enrich's
#: contract, carried over with the code).
#:
#: Until atrium-project#49 three of them were indistinguishable in the emitted artifact.
#: `--document-json`/`--document-json-out` copies the caller's BASELINE into a scratch dir
#: and copies whatever is in that dir back out at the end, so a run that contributed
#: nothing shipped the untouched baseline, announced "[document] Record written", and
#: exited 0. A crashed inference did the same. So did a healthy one that located nothing.
#: The consumer — atrium-project's tools/e2e/e2e_assert.py, and every downstream tool —
#: saw one record with no `enrichment` block and could only guess which of the three it
#: was looking at. Run 34090340995 is the guess going wrong: the digital smoke reported
#: "'enrichment' block missing from llm-enrich stage" for what was in fact a correct,
#: successful, empty enrichment of a fixture with no archaeological content in it.
OUTCOME_CONTRIBUTED = "contributed"
OUTCOME_EMPTY = "empty"
OUTCOME_FAILED = "failed"
OUTCOME_NOT_ASKED = "not-asked"

#: The outcomes that mean this stage has something to say about this document, i.e. the
#: ones that MUST write the `enrichment` block. `empty` is in here on purpose: a stage
#: that ran and found nothing is a different fact from a stage that never ran, and
#: `assembled.blocks` is the record's account of which tool contributed what — so the
#: only honest way to record "the model looked and there was nothing" is an enrichment
#: block with an empty `items` list, stamped by keyword-extract.
_CONTRIBUTING_OUTCOMES = frozenset({OUTCOME_CONTRIBUTED, OUTCOME_EMPTY})


def classify_outcome(results: List[dict], stats: Dict[str, int]) -> str:
    """Which of the four outcomes this pass had, from the driver's own stats.

    Order matters. Partial success is still a contribution: run_line_level() can enrich
    nine rows and error on the tenth, and that run has results to write — the error is
    already in `skipped_error` and in the paradata, and refusing the record over it would
    throw away nine good enrichments.

    `attempted` is what makes the empty/not-asked split possible; both have
    ``processed == 0`` and neither raises. See the stats dicts in run_document_level()
    and run_line_level().
    """
    if results:
        return OUTCOME_CONTRIBUTED
    if stats.get("aborted") or stats.get("skipped_error"):
        return OUTCOME_FAILED
    if stats.get("attempted"):
        return OUTCOME_EMPTY
    return OUTCOME_NOT_ASKED


def contributes_document_record(results: List[dict], stats: Dict[str, int]) -> bool:
    """Whether this pass may write its `enrichment` block onto the paired record.

    True for a real enrichment and for a model that was asked and located nothing.
    False when the model was never successfully consulted — there is no verdict to
    record, and writing an empty block would claim one.
    """
    return classify_outcome(results, stats) in _CONTRIBUTING_OUTCOMES


def enrichment_block(doc_id: str, results: List[dict]) -> dict:
    """Project this repo's ``*_enriched.json`` records onto the ``enrichment`` block
    of the paired per-document record (see ``atrium_document.py``).

    Handles both record shapes: the document-level one (``locator``/``page``, from
    ``run_document_level``) and the line-level one (``page``/``line``, from
    ``run_line_level``). Only the fields actually present are emitted, and a
    ``[Source: <doc_id>, Page N]`` citation is added whenever a page is known.

    ``page`` is emitted as a STRING because that is what the schema says it is — the same
    reason ``lines[].page`` is a string, so a label like ``"iv"`` or ``"A-1"`` survives.
    ``run_line_level`` coerces ``page_num`` to an int for its own arithmetic, so every
    line-level run used to write an integer here and the resulting record was
    schema-INVALID — caught the moment the Layer D gate below was actually wired
    (atrium-project#10, D4), having gone unnoticed for as long as nothing validated.
    """
    items: List[dict] = []
    for record in results:
        item: dict = {}
        for key in ("locator", "page", "line"):
            value = record.get(key)
            if value is not None:
                # `line` stays an int: the schema does not constrain it, and
                # BLOCK_KEY_FIELDS keys `lines[]` on it as an integer.
                item[key] = str(value) if key == "page" else value
        item.update(record.get("enrichment") or {})
        if item.get("page") is not None:
            item["citation"] = f"[Source: {doc_id}, Page {item['page']}]"
        items.append(item)
    return {"items": items}


#: One-shot latch so a vocabulary that cannot be consulted is announced once per process,
#: not once per document. See entity_pid_rows().
_pid_lookup_warned = False


def _note_pid(message: str) -> None:
    """Advisory stderr note about pid resolution, at most once per process."""
    global _pid_lookup_warned
    if not _pid_lookup_warned:
        print(f"[document] NOTE - entities[].pid: {message}", file=sys.stderr)
        _pid_lookup_warned = True


def entity_pid_rows(
    entities: List[Dict[str, Any]],
    vocab_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """`entities[]` patch rows carrying nothing but their natural key and a resolved `pid`.

    ``entities`` is a block **nlp-enrich owns and originates**; this stage is a field-level
    co-contributor with exactly one field in it —
    ``BLOCK_FIELD_OWNERS["entities"]["llm-enrich"] == ["pid"]``, which keyword-extract holds
    beside its predecessor (``PROGRAM_SUCCESSORS``) — and nothing in the
    ecosystem has ever written it, so the schema's "ARIADNE/GoTriple hook" has been null on
    every record produced so far. This builds the patch; ``write_document_record()`` merges
    it with ``own_fields=["pid"]`` so nlp-enrich's and translator's fields on the same row
    are left untouched.

    Each row carries the fields of ``BLOCK_KEY_FIELDS["entities"]`` (page, line, char_span)
    that the source row actually has, plus ``pid``. The key list is read from
    ``atrium_document`` rather than re-typed here, and every key value is copied from the
    source row, because that is what makes ``merge_block()`` land the patch ON the existing
    row instead of appending a second, pid-only fork of it.

    Resolution tries ``lemma`` first and falls back to ``surface``: the concept index is
    keyed on the vocabulary's Czech labels, which are lemmas, so an inflected surface form
    ("gotického kostela") misses where the lemma ("kostel") hits. ``resolve_pid()``
    normalises (NFC, casefold, whitespace) internally, so nothing is folded here.

    **A row is emitted only when at least one sub-key actually resolved.** ``resolve_pid()``
    answers with an all-None dict for a label it does not know, and most entities in an
    excavation report are people and places this archaeological vocabulary holds no concept
    for. Writing ``{"wikidata": null, "geonames": null, "aat": null, "amcr": null}`` onto
    every one of them would add a block of nulls the schema already implies and — since
    ``merge_block()`` stamps ``assembled.blocks.entities`` with the most recent writer —
    would re-attribute nlp-enrich's block to this stage on every re-run for no content at
    all. Returning ``[]`` means the caller never merges and the stamp stays where it was.

    Degrades to ``[]``, never raises. The flat artifacts (``amcr_flat.json``,
    ``teater_flat.json``) are legitimately absent in a slim image or in a checkout that has
    not run ``vocab_build.py``, and ``vocab_manager`` imports ``requests`` at module scope,
    which is why the import is deferred to here rather than taken at module import. A run
    without the vocabulary should lose the URIs, not the record.
    """
    try:
        from atrium_document import BLOCK_KEY_FIELDS
        from vocab_manager import resolve_pid
    except ImportError as exc:
        _note_pid(f"not resolved ({exc})")
        return []

    keys = BLOCK_KEY_FIELDS.get("entities") or []
    # resolve_pid carries the repo-wide default directory; passing vocab_dir=None through
    # would override that default with None rather than fall back to it.
    lookup = {} if vocab_dir is None else {"vocab_dir": str(vocab_dir)}

    #: natural key -> (patch row, pid), plus the keys that resolved two different ways.
    resolved: Dict[str, Tuple[Dict[str, Any], Dict[str, Optional[str]]]] = {}
    conflicting: Set[str] = set()

    try:
        for entity in entities or []:
            if not isinstance(entity, dict):
                continue
            pid: Optional[Dict[str, Optional[str]]] = None
            for field in ("lemma", "surface"):
                label = entity.get(field)
                if not isinstance(label, str) or not label.strip():
                    continue
                candidate = resolve_pid(label, **lookup)
                if any(candidate.values()):
                    pid = candidate
                    break
            if pid is None:
                continue

            row = {k: entity[k] for k in keys if k in entity}
            # Rows sharing a natural key share a merge target, so a second pid for the same
            # key would land on the FIRST row and claim an identity resolved from a
            # different entity. Only reachable when upstream rows are keyless (no
            # page/line/char_span at all keys them all to the same tuple), but a
            # cross-entity identity claim is precisely what resolve_pid refuses to guess at,
            # so it is refused here too: agreeing duplicates collapse, disagreeing ones
            # leave every row under that key unresolved.
            ident = json.dumps([row.get(k) for k in keys], sort_keys=True, default=str)
            if ident in resolved:
                if resolved[ident][1] != pid:
                    conflicting.add(ident)
                continue
            resolved[ident] = (row, pid)
    except Exception as exc:  # noqa: BLE001 — an odd vocabulary must not cost us the record
        _note_pid(f"not resolved ({exc})")
        return []

    if conflicting:
        _note_pid(
            f"{len(conflicting)} natural key(s) matched entities with different concepts "
            f"— left unresolved"
        )
    return [
        {**row, "pid": pid} for ident, (row, pid) in resolved.items() if ident not in conflicting
    ]


#: The recipe id ``regenerable.markdown`` names for ``api_util/json_to_md.py``, the record
#: renderer of atrium-digital-convert, whose ``CONVERTER_ID`` must agree (its
#: tests/test_json_to_md.py). This repository writes the recipe without carrying the module.
JSON_TO_MD_CONVERTER = "json_to_md@1.1"


def renders_from_record(record: Dict[str, Any]) -> bool:
    """Whether ``json_to_md`` can render this record: a line it would keep, or ``content.text``.

    A ``json_to_md`` recipe on a record with neither is a promise the converter refuses
    (``ValueError: nothing to render``) — which is what every plain-text upload to the
    service and every standalone run over a ``.md`` used to record.
    """
    try:
        from atrium_vocab import UNTRUSTWORTHY_LINE_CATEGORIES as dropped
    except ImportError:
        dropped = ()
    for line in record.get("lines") or []:
        if not isinstance(line, dict) or line.get("categ") in dropped:
            continue
        if str(line.get("text") or "").strip() and line.get("page") is not None:
            return True
    return bool(str((record.get("content") or {}).get("text") or "").strip())


#: One-shot latch so a DISABLED gate is announced once per process, not once per document.
#: See schema_gate().
_schema_gate_disabled_warned = False


def schema_gate(record: Dict[str, Any], what: str, *, baseline: bool = False) -> Optional[str]:
    """Validate one record against ``atrium_document.schema.json``.

    ``baseline=True`` judges a record this tool was HANDED: an AMČR seed (``doc_id`` and
    ``source`` only, atrium-project#71) is then checked against the seed profile
    (``validate_baseline``), not the full schema it could never pass, so a seed no longer
    counts as an invalid baseline and no longer demotes the gate on this tool's own output.

    Returns None when it validates, or a one-line description of the schema error when it
    does not. This is plan §2's **Layer D** — "no doc.json is emitted if validation fails" —
    adopted here for atrium-project#10 (D4), which found ``validate_document()`` called from
    no production path in any of the five repos: the gate documented as normative in
    ``docs/document_schema.md`` was protecting nothing at all.

    Deliberately only answers *"is it valid"*. The POLICY — who raises and who merely warns —
    lives at the two call sites, because it differs for an inherited baseline and for this
    tool's own output; see ``write_document_record()``.

    A missing ``jsonschema`` (RuntimeError from ``validate_document()``), a module vendored
    without its schema (FileNotFoundError from ``load_schema()``) or an unparseable schema
    (JSONDecodeError) all mean the GATE is absent, not that the record is bad — a
    ``jsonschema.ValidationError`` is none of those three, so nothing real is swallowed here.
    They degrade to ONE loud warning and a pass: a gate that
    silently no-ops is indistinguishable in the output from a gate that passed, which is the
    precise failure mode D4 is about. ``jsonschema`` is declared in ``requirements.txt`` — the
    base install every image and the test job actually build from — so the degraded path
    should never be taken in a supported deployment.
    """
    global _schema_gate_disabled_warned
    try:
        from atrium_document import validate_baseline, validate_document
    except ImportError:
        return None

    try:
        (validate_baseline if baseline else validate_document)(record)
    except (RuntimeError, FileNotFoundError, json.JSONDecodeError) as exc:
        if not _schema_gate_disabled_warned:
            print(
                f"[document] WARNING - schema validation is DISABLED for {what} and every "
                f"record after it: {exc}",
                file=sys.stderr,
            )
            _schema_gate_disabled_warned = True
        return None
    except Exception as exc:
        # jsonschema.ValidationError: `.message` is the human-readable half and `.json_path`
        # points at the offending node. Both are absent on any other validator, hence getattr.
        detail = getattr(exc, "message", None) or str(exc)
        path = getattr(exc, "json_path", "") or ""
        return f"{detail}{f' at {path}' if path else ''}"
    return None


#: The program id this module writes records as (`para_config.txt`): the successor of
#: `llm-enrich` (`atrium_document.PROGRAM_SUCCESSORS`), which owns `enrichment` and
#: `entities[].pid` beside its predecessor.
PROGRAM = "keyword-extract"


def write_document_record(
    doc_id: str,
    results: Optional[List[dict]],
    record_dir: Path,
    run_id: Optional[str] = None,
    paradata_ref: str = "",
    enriched_path: Optional[Path] = None,
    detail: str = "full",
    license_detail: Optional[dict] = None,
    used_markdown_input: bool = False,
    vocab_dir: Optional[str] = None,
    run_uuid: Optional[str] = None,
    keywords: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Write/update this document's paired record, contributing keyword-extract's blocks only.

    Reads ``<record_dir>/<doc_id>.document.json`` as the baseline when it exists and
    writes it back with the ``enrichment`` block replaced — every other tool's block
    passes through untouched. With no baseline present the record is just this tool's
    own part, which is the intended standalone behaviour.

    ``keywords`` is the statistical kind's ``keywords`` block (atrium-project#73,
    ``{"document": [...], "pages": [...]}``), written beside ``enrichment`` and never merged
    into it. ``results=None`` means the controlled kind did not contribute: neither
    ``enrichment`` nor ``entities[].pid`` is written, so a statistical-only call records its
    keywords without claiming a controlled verdict.

    The one exception to "own block only" is this stage's single declared field in
    somebody else's block: ``entities[].pid``, granted by
    ``BLOCK_FIELD_OWNERS["entities"]`` (to llm-enrich, and through it to its successor). It is
    merged FIELD-wise onto the rows nlp-enrich already wrote (``own_fields=["pid"]``), never
    set wholesale, and only for entities the controlled vocabulary can actually identify —
    see ``entity_pid_rows()``. ``vocab_dir`` is where the flat vocabulary artifacts live;
    ``None`` uses ``vocab_manager``'s own default, and a directory without them simply
    yields no pids.

    The ``regenerable.markdown`` recipe records how to rebuild the Markdown this run
    actually fed the LLM (rule: never reference a transient artifact by a stored path),
    at the cue profile ``detail`` (atrium-project#70). It is written only when
    ``used_markdown_input=True`` (a document-mode run over ``.md``/``.txt``) AND the record
    written here can be rendered (``renders_from_record``): the recipe then points at THIS
    SAME document JSON via ``json_to_md``, since it is self-sufficient (issue #13 §5). A
    line-mode run (a record's lines, CSV, TEITOK) fed no Markdown, so no recipe claims one.
    Returns the record path, or None when the optional ``atrium_document`` module is
    unavailable.

    ``run_uuid`` is the run's ``ParadataLogger.run_uuid`` (atrium-project#71): stamped with
    every block and the contributor entry, and the ``@id`` of the run's CreateAction.

    The returned path is the one ``finalize()`` wrote, and it is the baseline's own path
    (atrium-project#68). The record keeps the BASELINE's ``doc_id`` when it differs from
    ``doc_id`` here (an AMČR seed carries the AMČR file id, and the upload has another name),
    and ``finalize()``'s default file name follows the record's id. Left to that default, the
    record was written to ``<seed id>.document.json`` while this function returned the
    ``<doc_id>`` path, i.e. the untouched seed, which a caller then handed back without
    ``enrichment``.

    This is also the repo's **single Layer D chokepoint** for the record (atrium-project#10,
    D4). Every write path — both batch clients and ``service/api.py`` — comes through here,
    so the schema gate is applied once, not once per caller. The ecosystem-wide policy is:

    * an **inherited baseline** that does not validate warns and continues (refusing to run
      because an upstream tool wrote something invalid turns one bad record into a stalled
      pipeline, and rule 6 already commits to passing unknown content through);
    * **this tool's own output** that does not validate raises, so the record is never
      emitted — unless the baseline was already invalid, in which case the defect is
      inherited rather than ours and it warns instead.
    """
    try:
        from atrium_document import FILE_SUFFIX, SCHEMA_FILENAME, DocumentRecord, load_document
    except ImportError:
        print(
            "[document] atrium_document.py not available — skipping paired record",
            file=sys.stderr,
        )
        return None

    record_dir = Path(record_dir)
    record_dir.mkdir(parents=True, exist_ok=True)
    baseline = record_dir / f"{doc_id}{FILE_SUFFIX}"

    # Layer D, first half: judge the baseline as it ARRIVED. Read separately from
    # DocumentRecord.open() below (which re-reads it) so the verdict is about the upstream
    # tool's output and not about anything this run has since applied to it. It also sets the
    # severity of the second half — a schema error we inherited is not ours to fail on.
    baseline_was_invalid = False
    if baseline.exists():
        baseline_error = schema_gate(
            load_document(str(baseline)), f"baseline {baseline.name}", baseline=True
        )
        if baseline_error:
            baseline_was_invalid = True
            print(
                f"[document] WARNING - inherited baseline {baseline.name} does not validate "
                f"against {SCHEMA_FILENAME} ({baseline_error}) - continuing anyway (rule 6), "
                f"and demoting this run's own output check to a warning",
                file=sys.stderr,
            )

    with DocumentRecord.open(
        doc_id,
        PROGRAM,
        baseline=str(baseline) if baseline.exists() else None,
        run_id=run_id,
        run_uuid=run_uuid,
        paradata_ref=paradata_ref,
        out_dir=str(record_dir),
    ) as doc:
        if results is not None:
            # doc.doc_id, not doc_id: the citations name the record's document, which is the
            # baseline's id whenever it differs from the one derived from the input (#68).
            doc.set_block("enrichment", enrichment_block(doc.doc_id, results))

            # The one field this stage has in a block it does not own. merge_block, not
            # set_block: `entities` is nlp-enrich's, and a wholesale write would erase the
            # morphology and spans it holds. Reading the block back through get_block() is what
            # supplies the rows to patch — they are the baseline's, so a standalone run (no
            # baseline, no entities) resolves nothing and merges nothing, and the block is not
            # created.
            pid_rows = entity_pid_rows(doc.get_block("entities") or [], vocab_dir)
            if pid_rows:
                doc.merge_block("entities", pid_rows, own_fields=["pid"])

        if keywords is not None:
            # The statistical kind's own block (atrium-project#73): a whole block, replaced on a
            # re-run, beside `enrichment` and never merged into it.
            doc.set_block("keywords", keywords)

        if enriched_path is not None:
            doc.add_derived_from("enriched", str(enriched_path))
        # The record's own file name follows doc.doc_id, the baseline's id (#68), so the
        # recipe names that file and not one derived from the upload.
        if used_markdown_input and renders_from_record(doc.to_dict()):
            doc.add_regenerable(
                "markdown",
                {
                    "from": f"{doc.doc_id}{FILE_SUFFIX}",
                    "converter": JSON_TO_MD_CONVERTER,
                    "detail": detail,
                },
            )
        if license_detail:
            doc.add_license_detail(license_detail)

        # Layer D, second half: never EMIT an invalid record. Raising here — INSIDE the
        # `with` — is what enforces that: DocumentRecord.__exit__ finalises only when no
        # exception is in flight, so nothing reaches disk and the next tool never loads a
        # record this one knew was broken. Both clients call this from inside their per-file
        # try/except, so one bad document is logged and skipped rather than killing the run.
        own_error = schema_gate(doc.to_dict(), f"{doc_id}{FILE_SUFFIX}")
        if own_error:
            if baseline_was_invalid:
                print(
                    f"[document] WARNING - {doc_id}{FILE_SUFFIX} does not validate against "
                    f"{SCHEMA_FILENAME} ({own_error}) - emitting it anyway because the "
                    f"baseline was already invalid; fix the upstream record first",
                    file=sys.stderr,
                )
            else:
                raise RuntimeError(
                    f"keyword-extract's own document record for {doc_id} does not validate "
                    f"against {SCHEMA_FILENAME}: {own_error} - refusing to emit it (Layer D)"
                )

        # Back to the file it was read from, explicitly (#68, see the docstring).
        # __exit__ then has nothing left to do.
        record_path = Path(doc.finalize(str(baseline)))

    return record_path


# ---------------------------------------------------------------------------
# 7b. Repairing a document-level reply — atrium-project#49 / run 34123820218
# ---------------------------------------------------------------------------
#
# The whole-document request goes out as `response_format: {"type": "json_object"}`
# unless --structured-outputs is passed, and the E2E does not pass it: with a 4712-value
# enum the json_schema variant is far larger than most providers accept, and
# --provider-data-collection deny narrows routing to providers whose structured-output
# support varies. So the shape is enforced by the PROMPT, and the prompt is advice.
#
# gpt-4o-mini's deviations, observed in full in run 34123820218 (five items, four
# validation errors each, on content it had otherwise read correctly):
#
#   page                    -> 1 (int)                      instead of "1"
#   extracted_keywords_cs   -> "hradiste, lokalita, Beroun" instead of [...]
#   extracted_keywords_en   -> "fortress, site, Beroun"     instead of [...]
#   teater_category         -> a term of its own wording, not one from the vocabulary
#
# The first three are unambiguous formatting slips over a correct answer, and throwing
# the answer away for them is the wrong trade. The fourth is not a formatting slip: an
# unlisted category is a claim the vocabulary does not support, and inventing a mapping
# for it would fabricate data. So the first three are coerced and the fourth is resolved
# only against the vocabulary itself — exact, then case- and whitespace-insensitive —
# and the item is DROPPED, loudly and counted, when that fails.

_KEYWORD_SEPARATORS = re.compile(r"[;,]")

#: One trailing "(...)" group, used only as a last resort — see _term_resolver().
_PARENTHETICAL_TAIL = re.compile(r"\s*\([^()]*\)\s*$")

#: A value shaped like one of prompt_template.vocabulary_block()'s own `--- theme / sub ---`
#: headings.
#: Recognised purely so the drop reason can NAME the mistake: a heading coming back as a
#: category means the prompt failed to distinguish its two kinds of line, which is a
#: prompt bug to fix, not a model quirk to absorb. Deliberately never resolved to a term —
#: a heading names a whole section, so picking any member of it would be a guess.
_LOOKS_LIKE_A_HEADING = re.compile(r"^[^/]+ / [^/]+$")


def _as_keyword_list(value: Any) -> List[str]:
    """A keyword field as the list the schema asks for.

    A bare string is split on commas/semicolons — that is the exact form the model
    returns, and it is unambiguous here because a vocabulary keyword never contains one.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in _KEYWORD_SEPARATORS.split(value) if part.strip()]
    return [str(value).strip()]


def _as_page_label(value: Any) -> Optional[str]:
    """A page as the STRING the schema asks for, preserving non-numeric labels.

    `page` is a string so "iv" or "A-1" survive (the same reason lines[].page is one).
    A float that is a whole number renders as "2", not "2.0" — json.loads gives a float
    for `2.0`, and "2.0" would not match any page label a renderer emits.
    """
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def _term_resolver(model: type) -> Callable[[Any], Optional[str]]:
    """Resolve a model-supplied category against the vocabulary the enum was built from.

    Exact match first, then a casefolded/whitespace-collapsed match, which recovers the
    near-misses ("Kostel", "kostel " ) without inventing anything. Anything else is
    unresolvable BY DESIGN: see the module note above.
    """
    allowed = tuple(getattr(model, "allowed_terms", ()) or ())
    loose = {" ".join(term.casefold().split()): term for term in allowed}

    def _loose(value: str) -> Optional[str]:
        return loose.get(" ".join(value.casefold().split()))

    def resolve(value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        if value in allowed:
            return value
        hit = _loose(value)
        if hit is not None:
            return hit
        # The vocabulary is printed as `- <czech> (<english>)`, so a model that copies a
        # whole bullet returns "sonda (trench)". Strip ONE trailing parenthetical and
        # retry — but only here, after the full string has already failed to match, which
        # is what keeps terms that legitimately end in one ("atlantik (paleoklimatologie)",
        # META_TERM itself) from being mangled: those match on the first two attempts.
        trimmed = _PARENTHETICAL_TAIL.sub("", value).strip()
        if trimmed and trimmed != value:
            if trimmed in allowed:
                return trimmed
            return _loose(trimmed)
        return None

    return resolve


def _repair_document_response(result_json: str, model: type, file_id: str) -> Tuple[Any, List[str]]:
    """Coerce a near-miss document-level reply into the schema, or raise.

    Returns the validated model plus one human-readable line per dropped item. Raises
    (to run_document_level's handler, which records an inference error) when the payload
    is not JSON, is not an object with an `items` array, or still fails validation after
    coercion — those are not formatting slips and must stay loud.
    """
    raw = json.loads(result_json, strict=False)
    if isinstance(raw, list):
        # Some replies drop the wrapper and return the array on its own.
        raw = {"items": raw}
    if not isinstance(raw, dict):
        raise ValueError(f"expected a JSON object, got {type(raw).__name__}")

    items = raw.get("items")
    if items is None:
        raise ValueError("reply has no 'items' key")
    if not isinstance(items, list):
        raise ValueError(f"'items' is {type(items).__name__}, expected a list")

    resolve = _term_resolver(model)
    repaired: List[dict] = []
    dropped: List[str] = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            dropped.append(f"item {index}: not an object ({type(item).__name__})")
            continue

        raw_category = item.get("teater_category")
        category = resolve(raw_category)
        if category is None:
            hint = ""
            if isinstance(raw_category, str) and _LOOKS_LIKE_A_HEADING.match(raw_category.strip()):
                hint = (
                    " — that is one of the vocabulary's own '--- theme / sub ---' SECTION "
                    "HEADINGS, not a term under it"
                )
            dropped.append(
                f"item {index}: teater_category {raw_category!r} is not in the vocabulary{hint}"
            )
            continue

        fixed = dict(item)
        fixed["teater_category"] = category
        fixed["page"] = _as_page_label(item.get("page"))
        fixed["extracted_keywords_cs"] = _as_keyword_list(item.get("extracted_keywords_cs"))
        fixed["extracted_keywords_en"] = _as_keyword_list(item.get("extracted_keywords_en"))
        try:
            fixed["confidence_score"] = min(1.0, max(0.0, float(item.get("confidence_score"))))
        except (TypeError, ValueError):
            dropped.append(
                f"item {index}: confidence_score {item.get('confidence_score')!r} is not a number"
            )
            continue
        repaired.append(fixed)

    for reason in dropped:
        print(f"    [dropped] {reason}")

    if items and not repaired:
        # Every single item unusable is a systematic mismatch, and it must NOT become an
        # empty verdict. An `enrichment: {items: []}` block is the record's way of saying
        # "the model looked and there was nothing here" — reporting it when the model in
        # fact found five things we could not read would be a lie in the record and a
        # green digital smoke that enriched nothing. A gate that goes quiet is worse than
        # one that goes red. So this raises, and run_document_level's handler turns it
        # into an inference error, which under atrium-project#49's contract means no
        # document record and a non-zero exit.
        raise ValueError(
            f"the model returned {len(items)} item(s) and none survived repair: "
            + "; ".join(dropped)
        )

    print(
        f"  [{file_id}] repaired a non-conforming document reply: "
        f"{len(repaired)} item(s) recovered, {len(dropped)} dropped"
    )
    return model.model_validate({"items": repaired}), dropped


def run_document_level(
    input_path: Path,
    chat_fn: ChatFn,
    system_prompt: str,
    DocumentEnrichmentModel: type,
    user_content_builder: Optional[Callable[[str], Any]] = None,
    strict: bool = False,
) -> Tuple[List[dict], Dict[str, int]]:
    """
    Run whole-document enrichment over a single Markdown/plain-text file (typically a
    rendering by atrium-digital-convert's json_to_md.py or xml_to_md.py). One chat call per
    document, returning every located passage instead of one record per input row.

    ``user_content_builder``, when supplied, is called with the raw document
    text and its return value becomes the user message's ``content`` as-is
    (e.g. OpenRouter's file-attachment content-part list) — this is how
    --attach-as-file actually reaches the wire. When omitted, the document
    text is inlined as plain message text (``DOCUMENT:\n<text>``), matching
    every caller's original behaviour.

    ``strict=True`` (llm-enrich's service, atrium-project#53) lets a failed call raise instead of
    returning no records with ``aborted`` set: a reply cut at the token cap
    (:class:`ReplyTruncated`) and a call whose retries ran out (``RuntimeError``) then
    reach the caller, which answers 422 or 502 rather than 200 with empty results. A
    reply that does not validate is still repaired, as before.
    """
    file_id = Path(input_path).stem
    stats: Dict[str, int] = {
        "processed": 0,
        "skipped_filter": 0,
        "skipped_error": 0,
        "aborted": 0,
        # `attempted` counts model calls MADE, not records produced, and it is the only
        # thing that separates "we asked and it located nothing" from "we never asked"
        # (atrium-project#49). `processed` cannot: it is 0 for both. See
        # classify_outcome() for why the difference decides whether a document record
        # is written at all.
        "attempted": 0,
    }

    doc_text = Path(input_path).read_text(encoding="utf-8")
    user_content: Any = (
        user_content_builder(doc_text) if user_content_builder else f"DOCUMENT:\n{doc_text}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # Counted BEFORE the call, not after: a call that raises was still an attempt, and
    # the failure branch below needs to be distinguishable from "no input reached the
    # model" rather than from "the model answered".
    stats["attempted"] = 1
    try:
        result_json = chat_fn(messages)
        try:
            semantic_data = DocumentEnrichmentModel.model_validate_json(result_json)
        except ValidationError:
            # The repair pass. This used to re-validate the SAME payload against the
            # SAME strict model, so for a shape error it could only raise again —
            # a retry that cannot succeed. _repair_document_response() coerces the
            # deviations the model actually produces before re-validating.
            semantic_data, dropped = _repair_document_response(
                result_json, DocumentEnrichmentModel, file_id
            )
            stats["repaired"] = 1
            stats["dropped_items"] = len(dropped)
    except Exception as exc:
        if strict and isinstance(exc, RuntimeError):
            raise
        print(f"  [{file_id}] Document-level inference/validation error: {exc}")
        stats["skipped_error"] += 1
        stats["aborted"] = 1
        if isinstance(exc, ReplyTruncated):
            stats["truncated"] = 1
        return [], stats

    enriched: List[dict] = []
    for item in semantic_data.items:
        dump_data = item.model_dump()
        dump_data["teater_category"] = item.category_name()
        if dump_data["teater_category"] == META_TERM:
            dump_data["extracted_keywords_cs"] = []
            dump_data["extracted_keywords_en"] = []
        enriched.append(
            {
                "file_id": file_id,
                "locator": dump_data.pop("locator"),
                "page": dump_data.pop("page", None),
                "enrichment": dump_data,
            }
        )
    stats["processed"] = len(enriched)
    return enriched, stats


# ---------------------------------------------------------------------------
# 8. Line-level driver — the service's controlled kind and both batch clients
# ---------------------------------------------------------------------------


def _coerce_int(value: Any, default: int = 0) -> int:
    """Best-effort int coercion for a row's page_num/line_num field.

    A blank or non-numeric value coerces to `default` instead of raising —
    the line is still processed. Previously run_line_level treated a
    ValueError/TypeError here as a filter-skip and silently dropped the row,
    which mislabelled a data problem as a quality-filter decision."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def enrich_rows(
    rows: List[dict],
    file_id: str,
    chat_fn: ChatFn,
    system_prompt: str,
    EnrichmentModel: type,
    include_non_text: bool = True,
    min_char_count: int = 3,
    min_char_non_text: int = 8,
    min_alpha_ratio_non_text: float = 0.40,
    max_consecutive_errors: int = 10,
    errors: Optional[List[str]] = None,
) -> Tuple[List[dict], Dict[str, int]]:
    """
    Line-level enrichment of every qualifying row, mirroring llm_utils.process_document's
    contract (same stats keys, same output record shape, same consecutive-error abort) so
    results are comparable across BACKEND values.

    ``chat_fn`` does the actual HTTP call; everything else — filtering, context-window
    building, schema validation — is shared here. ``rows`` come from
    :func:`read_input_rows` (a file), :func:`record_rows` (a record the service was sent) or
    :func:`text_rows` (a plain text).

    A result's ``page`` is the row's ``page_label`` when it has one (a record's own label, a
    string) and the page number otherwise, as ``<doc_id>_enriched.json`` has always held it.

    The limits that shaped the result are counted in ``stats`` (atrium-project#53):
    ``truncated`` — lines whose reply was cut at the token cap and therefore got no
    result; ``aborted`` with ``unprocessed`` — the document was given up after
    ``max_consecutive_errors`` failed lines, and how many qualifying lines were left.
    ``errors``, when given, collects one ``P<page> L<line>: <error>`` line per failed row, so a
    caller can say why a document failed (the service's 502) and not only that it did.
    """
    enriched_lines: List[dict] = []
    stats: Dict[str, int] = {
        "processed": 0,
        "skipped_filter": 0,
        "skipped_error": 0,
        "aborted": 0,
        # See run_document_level() for what `attempted` is for. Here it counts the ROWS
        # actually sent to the model — a document whose every row was dropped by
        # should_process_line() never consulted it, and must not be reported as an
        # enrichment that found nothing.
        "attempted": 0,
        "truncated": 0,
    }
    consecutive_errors = 0
    page_num = line_num = 0

    for i, row in enumerate(rows):
        try:
            page_num = _coerce_int(row.get("page_num", row.get("page", 0)))
            line_num = _coerce_int(row.get("line_num", row.get("line", 0)))
            page = row["page_label"] if row.get("page_label") else page_num

            text_chunk = (row.get("text") or "").strip()
            categ = (row.get("categ") or "").strip()
            quality_score = row_quality(row)

            should_process, _ = should_process_line(
                text_chunk,
                categ,
                quality_score,
                include_non_text,
                min_char_count,
                min_char_non_text,
                min_alpha_ratio_non_text,
            )
            if not should_process:
                stats["skipped_filter"] += 1
                continue

            context_chunk = get_context_window(rows, i, window=2)
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"DOCUMENT CONTEXT:\n{context_chunk}\n\n"
                        "Task: Extract keywords and determine the TEATER category "
                        "ONLY for the line marked inside <target_line>."
                    ),
                },
            ]

            stats["attempted"] += 1
            result_json = chat_fn(messages)
            dump_data = validate_llm_output(
                result_json, EnrichmentModel, file_id, page_num, line_num
            )

            enriched_lines.append(
                {
                    "file_id": file_id,
                    "page": page,
                    "line": line_num,
                    "categ": categ,
                    "quality_score": quality_score,
                    "original_text": text_chunk,
                    "enrichment": dump_data,
                }
            )
            stats["processed"] += 1
            consecutive_errors = 0

        except Exception as exc:
            print(f"  [{file_id}] Inference error P{page_num} L{line_num}: {exc}")
            if errors is not None:
                errors.append(f"P{page_num} L{line_num}: {exc}")
            stats["skipped_error"] += 1
            if isinstance(exc, ReplyTruncated):
                stats["truncated"] += 1
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                stats["aborted"] = 1
                stats["unprocessed"] = len(rows) - i - 1
                print(f"  [{file_id}] Aborting after {consecutive_errors} consecutive errors.")
                break

    return enriched_lines, stats


def run_line_level(
    input_path: Path,
    chat_fn: ChatFn,
    system_prompt: str,
    EnrichmentModel: type,
    include_non_text: bool = True,
    min_char_count: int = 3,
    min_char_non_text: int = 8,
    min_alpha_ratio_non_text: float = 0.40,
    max_consecutive_errors: int = 10,
) -> Tuple[List[dict], Dict[str, int]]:
    """:func:`enrich_rows` over a CSV, a ``*.teitok.xml`` or a record (``*.document.json``)."""
    return enrich_rows(
        read_input_rows(Path(input_path)),
        doc_id_from_path(input_path),
        chat_fn,
        system_prompt,
        EnrichmentModel,
        include_non_text=include_non_text,
        min_char_count=min_char_count,
        min_char_non_text=min_char_non_text,
        min_alpha_ratio_non_text=min_alpha_ratio_non_text,
        max_consecutive_errors=max_consecutive_errors,
    )
