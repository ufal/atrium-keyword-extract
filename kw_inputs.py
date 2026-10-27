"""
kw_inputs.py — what a keyword extraction reads, the same on the command line and in the service.

``keywords.py`` read CoNLL-U and TEITOK files; ``POST /extract_keywords`` read the ATRIUM record
and ``/extract_keywords_text`` a plain text; neither read what the other did. Both now turn every
input into a :class:`Document` here (atrium-project#72, the service–CLI alignment):

* the record (``*.document.json``): ``lines[].text`` per page, the untrustworthy and empty lines
  left out, ``content.text`` when there are no lines; KER's lemmas from ``lines[].lemma`` and
  ``lines[].upos``;
* CoNLL-U (nlp-enrich's ``UDP/<doc>.conllu``): the surface text and the lemmas of every noun,
  proper noun and adjective; no pages, since CoNLL-U carries none;
* TEITOK (``*.teitok.xml``, or an ``.xml`` with ``<TEI`` in its first 4 KB): its rows' text, pages
  by ``<pb/>`` (``pb@n`` as the key), the lemmas of its ``<tok>``s;
* a line table (``.csv``, ocr-postprocess's ``DOC_LINE_CATEG`` or nlp-enrich's input): ``text`` per
  ``page_num`` (or ``page``), the lines whose ``categ`` is untrustworthy or ``Empty`` left out;
* plain text (``.txt``): the whole text; a form feed starts a page.

The KER (``legacy``) lemma source differs by input and stays so: CoNLL-U and TEITOK give every
content token's lemma; a record gives ``lines[].lemma``, which no ATRIUM tool writes today, so KER
over a record has nothing to count unless a caller added them. Per-page lemmas come from a record
only.

FastAPI-free and model-free: ``keywords.py`` (the command line) and ``service/api.py`` import it.
"""

from __future__ import annotations

import csv
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from api_util import teitok_read
from atrium_vocab import UNTRUSTWORTHY_LINE_CATEGORIES

#: The parts of speech whose lemmas KER counts.
KER_POS = frozenset({"NOUN", "PROPN", "ADJ"})

#: Lines left out of the text: nothing is read from them (report §5). The untrustworthy ones are
#: the hub registry's (ocr-postprocess's ``Trash``, digital-convert's ``Garbage`` and
#: ``Inverted``); ``Empty`` has nothing to read. The controlled kind leaves out the same lines
#: (``llm_client_shared.should_process_line``).
SKIPPED_CATEGORIES = frozenset(UNTRUSTWORTHY_LINE_CATEGORIES) | {"Empty"}

RECORD_SUFFIX = ".document.json"
TEITOK_SUFFIX = ".teitok.xml"
#: What a ``file`` upload and the command line's input folder may hold, by extension.
ACCEPTED = (RECORD_SUFFIX, ".conllu", TEITOK_SUFFIX, ".xml", ".csv", ".txt")


class NoText(ValueError):
    """The input holds no text to extract keywords from."""


class UnsupportedInput(ValueError):
    """A file of a kind keyword-extract does not read."""

    accepted = ACCEPTED


@dataclass
class Document:
    """The text of one document as the extraction methods read it."""

    doc_id: str
    text: str = ""
    lemmas: List[str] = field(default_factory=list)
    #: ``{"page", "text", "lemmas"}`` in document order; empty for an input without pages.
    pages: List[Dict[str, Any]] = field(default_factory=list)
    #: The controlled kind's rows: every line, the skipped ones too (they are context).
    rows: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def words(self) -> int:
        return len(self.text.split())


# ── what an input is ─────────────────────────────────────────────────────────────────────────


def input_kind(name: str, head: bytes = b"") -> Optional[str]:
    """``record``, ``conllu``, ``teitok``, ``csv`` or ``txt``; None for a file not read here."""
    lowered = str(name or "").lower()
    if lowered.endswith(RECORD_SUFFIX):
        return "record"
    if lowered.endswith(TEITOK_SUFFIX) or (lowered.endswith(".xml") and b"<TEI" in head[:4096]):
        return "teitok"
    for suffix, kind in ((".conllu", "conllu"), (".csv", "csv"), (".txt", "txt")):
        if lowered.endswith(suffix):
            return kind
    return None


def record_stem(record: Optional[Dict[str, Any]]) -> str:
    """The file stem a record is written under while its block is added: its own ``doc_id``
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


# ── CoNLL-U ──────────────────────────────────────────────────────────────────────────────────


def _conllu_tokens(lines: Iterable[str]) -> Iterable[List[str]]:
    """The columns of each syntactic word (multi-word ranges and empty nodes left out)."""
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 10:
            continue
        if "-" in cols[0] or "." in cols[0]:
            continue
        yield cols


def conllu_text(lines: Iterable[str]) -> str:
    """The surface text of a CoNLL-U document: each form, a space unless ``SpaceAfter=No``."""
    parts = [
        cols[1] + ("" if "SpaceAfter=No" in cols[9] else " ") for cols in _conllu_tokens(lines)
    ]
    return "".join(parts).strip()


def conllu_sentences(lines: Iterable[str]) -> List[str]:
    """The surface text of each sentence: the controlled kind's lines of a CoNLL-U document."""
    sentences, current = [], []
    for line in list(lines) + [""]:
        if line.strip():
            current.append(line)
        elif current:
            text = conllu_text(current)
            if text:
                sentences.append(text)
            current = []
    return sentences


def conllu_lemmas(lines: Iterable[str]) -> List[str]:
    """The lemmas KER counts: nouns, proper nouns and adjectives, alphabetic, longer than one letter."""
    lemmas = []
    for cols in _conllu_tokens(lines):
        lemma, upos = cols[2], cols[3]
        if upos in KER_POS and lemma != "_" and len(lemma) > 1 and lemma.isalpha():
            lemmas.append(lemma.lower())
    return lemmas


# ── the readers ──────────────────────────────────────────────────────────────────────────────


def _ker_lemma(line: Dict[str, Any]) -> Optional[str]:
    """The lemma KER counts for a record line's token, or None."""
    lemma = line.get("lemma")
    if (
        line.get("upos") in KER_POS
        and isinstance(lemma, str)
        and len(lemma) > 1
        and lemma.isalpha()
    ):
        return lemma.lower()
    return None


def _paged(doc: Document, entries: List[Tuple[str, str, Optional[str]]], joiner: str) -> None:
    """Fill ``doc.pages``, ``doc.text`` and ``doc.lemmas`` from ``(page, text, lemma)`` entries."""
    order: List[str] = []
    per_page: Dict[str, Dict[str, Any]] = {}
    for page, text, lemma in entries:
        entry = per_page.get(page)
        if entry is None:
            entry = per_page[page] = {"page": page, "parts": [], "lemmas": []}
            order.append(page)
        entry["parts"].append(text)
        if lemma:
            entry["lemmas"].append(lemma)
    doc.pages = [
        {"page": p, "text": joiner.join(per_page[p]["parts"]), "lemmas": per_page[p]["lemmas"]}
        for p in order
    ]
    doc.text = joiner.join(p["text"] for p in doc.pages)
    doc.lemmas = [lemma for p in doc.pages for lemma in p["lemmas"]]


def from_record(record: Dict[str, Any]) -> Document:
    """The record's text, and its pages', from its lines (or, failing those, its ``content``)."""
    import llm_client_shared as llm

    doc = Document(doc_id=str(record.get("doc_id") or "document"))
    entries = []
    for line in record.get("lines") or []:
        if not isinstance(line, dict):
            continue
        text = str(line.get("text") or "").strip()
        if not text or line.get("categ") in SKIPPED_CATEGORIES:
            continue
        page = str(line.get("page")) if line.get("page") is not None else "1"
        entries.append((page, text, _ker_lemma(line)))
    if entries:
        _paged(doc, entries, " ")
        doc.rows = llm.record_rows(record)
        return doc
    content = record.get("content")
    text = str((content or {}).get("text") or "").strip() if isinstance(content, dict) else ""
    if not text:
        raise NoText("The record has no text: no `lines[].text` and no `content.text`.")
    doc.text = text
    doc.rows = llm.text_rows(text)
    return doc


def from_text(text: str, doc_id: str = "text") -> Document:
    """A plain text, as ``/extract_keywords_text`` reads it: one document, no pages."""
    import llm_client_shared as llm

    doc = Document(doc_id=doc_id, text=text.strip())
    if not doc.text:
        raise NoText("The text is empty.")
    doc.rows = llm.text_rows(doc.text)
    return doc


def from_txt(data: bytes, doc_id: str) -> Document:
    """A ``.txt`` file: its text, and its pages when a form feed separates them."""
    text = data.decode("utf-8-sig", errors="replace")
    doc = from_text(text.replace("\f", "\n"), doc_id)
    parts = [part.strip() for part in text.split("\f")]
    if len([p for p in parts if p]) > 1:
        doc.pages = [
            {"page": str(n), "text": part, "lemmas": []}
            for n, part in enumerate(parts, start=1)
            if part
        ]
    return doc


def from_conllu(data: bytes, doc_id: str) -> Document:
    lines = data.decode("utf-8", errors="ignore").splitlines()
    doc = Document(doc_id=doc_id, text=conllu_text(lines), lemmas=conllu_lemmas(lines))
    if not doc.text:
        raise NoText("The CoNLL-U file has no tokens.")
    import llm_client_shared as llm

    doc.rows = llm.text_rows("\n".join(conllu_sentences(lines)))
    return doc


def from_teitok(path: Path, doc_id: str) -> Document:
    """A TEITOK file: the text ``keywords.py`` always read (its rows, one per line), pages by
    ``<pb/>``, and the lemmas of its tokens."""
    rows = teitok_read.read_teitok_rows(path)
    doc = Document(doc_id=doc_id)
    entries = [
        (str(r.get("page_label") or r.get("page_idx", r.get("page_num", 1))), r["text"], None)
        for r in rows
        if str(r.get("text") or "").strip()
    ]
    if not entries:
        raise NoText("The TEITOK file has no text.")
    _paged(doc, entries, "\n")
    doc.text = teitok_read.read_teitok_text(path)
    doc.lemmas = [
        t["lemma"].lower()
        for t in teitok_read.read_teitok_tokens(path)
        if t.get("upos") in KER_POS and (t.get("lemma") or "").isalpha()
    ]
    doc.rows = [
        {
            "text": r["text"],
            "page_num": str(r.get("page_num", "")),
            "line_num": str(r.get("line_num", "")),
            "categ": "",
            "quality_score": None,
        }
        for r in rows
    ]
    return doc


def from_csv(data: bytes, doc_id: str) -> Document:
    """A line table: ``text`` per page, the lines the quality stage did not trust left out."""
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig", errors="replace")))
    if "text" not in [str(n or "").strip() for n in (reader.fieldnames or [])]:
        raise ValueError("A CSV input needs a 'text' column.")
    rows = [{str(k).strip(): v for k, v in raw.items() if k is not None} for raw in reader]
    doc = Document(doc_id=doc_id)
    entries = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text or str(row.get("categ") or "").strip() in SKIPPED_CATEGORIES:
            continue
        page = str(row.get("page_num") or row.get("page") or "1").strip()
        entries.append((page, text, None))
    if not entries:
        raise NoText("The CSV file has no text lines to read.")
    _paged(doc, entries, " ")
    doc.rows = rows
    return doc


def read_document(name: str, data: Optional[bytes] = None) -> Document:
    """Any accepted input as a :class:`Document`. ``name`` is the file's name, or its path when
    ``data`` is None (then the file is read). Raises :class:`UnsupportedInput` for a file of
    another kind, :class:`NoText` for one without text, ``ValueError`` for one that cannot be read."""
    on_disk = data is None
    if data is None:
        data = Path(name).read_bytes()
    kind = input_kind(name, data[:4096])
    doc_id = teitok_read.doc_id_from_path(Path(str(name)).name)
    if kind == "record":
        import json

        try:
            record = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{name}: not a record ({exc})") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{name}: an ATRIUM record is a JSON object")
        return from_record(record)
    if kind == "conllu":
        return from_conllu(data, doc_id)
    if kind == "teitok":
        if on_disk:
            return from_teitok(Path(name), doc_id)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"upload{TEITOK_SUFFIX}"
            path.write_bytes(data)
            return from_teitok(path, doc_id)
    if kind == "csv":
        return from_csv(data, doc_id)
    if kind == "txt":
        return from_txt(data, doc_id)
    raise UnsupportedInput(
        f"{Path(str(name)).name}: not an input keyword-extract reads "
        "(a record *.document.json, .conllu, *.teitok.xml, .csv or .txt)."
    )


# ── the answer ───────────────────────────────────────────────────────────────────────────────


def keyword_entries(method: str, pairs: Iterable[Tuple[str, float]]) -> List[Dict[str, Any]]:
    """The keywords as the service answers them and the record's ``keywords`` block stores them."""
    return [
        {"keyword": phrase, "score": float(score), "method": method, "rank": rank}
        for rank, (phrase, score) in enumerate(pairs, start=1)
    ]
