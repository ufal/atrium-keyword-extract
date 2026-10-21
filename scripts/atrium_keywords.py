#!/usr/bin/env python3
"""Zero-dependency client for the ATRIUM keyword-extract API (strategy §6 / Appendix B).

Sends documents to a running keyword-extract service and prints their keywords, of two kinds that
are always kept apart:

  - statistical: the keywords of the document and of each page, with their method (KeyBERT,
    YAKE or the legacy method), score and rank;
  - controlled:  per line, the AMČR/TEATER vocabulary term that describes it and the Czech and
    English keywords found in it, chosen by a language model on the server (only when the server
    has an LLM backend; see --info).

Inputs, by suffix:
  - an ATRIUM document record (*.document.json, *.json) -> POST /extract_keywords; the record
    comes back with its `keywords` (and `enrichment`) blocks, written with --out-dir;
  - a plain text (*.txt, *.md), or "-" for stdin -> POST /extract_keywords_text.

Per-document summaries go to stderr; stdout stays clean for table/csv/json.

Exit codes:
    0 - success
    1 - client-side error (bad arguments, unreadable file)
    2 - server unreachable (connection refused / timeout)
    3 - server-side error (HTTP 4xx/5xx)
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DEFAULT_BASE_URL = os.environ.get("ATRIUM_KW_URL", "http://localhost:8000")
RECORD_SUFFIXES = (".document.json", ".json")
TEXT_SUFFIXES = (".txt", ".md")
MAX_UPLOAD_MB = 10  # mirrors the server's MAX_UPLOAD_MB default
RETRY_STATUS = {502, 503, 504}
# A 502 is retried only with one of these reasons (atrium_service.REASON_CODES); without one,
# `detail` names a cause that a retry does not change (atrium-nlp-enrich#41).
RETRY_502_REASONS = {"upstream_unavailable"}
RETRY_ATTEMPTS = 3
RETRY_WAIT_S = 10
TIMEOUT_S = 1800  # the controlled kind makes one language-model call per line

HINTS = {
    429: "every extraction slot is busy: retry after the Retry-After seconds",
    501: "the server has no working LLM backend: use --kind statistical, or see --info (controlled.detail)",
    502: "the LLM backend failed every call: check the backend named in --info, or use --kind statistical",
}


def build_multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    """Encode form fields and {field: path} files as multipart/form-data using only the stdlib."""
    boundary = uuid.uuid4().hex
    lines = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(str(value).encode())

    for field, file_path in files.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{field}"; filename="{file_path.name}"'.encode())
        lines.append(b"Content-Type: application/json")
        lines.append(b"")
        lines.append(file_path.read_bytes())
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")

    body = b"\r\n".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


def is_retryable(status: int, body: str) -> bool:
    """A 503/504 is. A 502 in the service's error body is retried only with a reason in
    RETRY_502_REASONS; a 502 without that body came from a proxy in front of the service and is."""
    if status != 502:
        return True
    try:
        error = json.loads(body)
    except ValueError:
        return True  # not the service's answer: a proxy or gateway page
    if not isinstance(error, dict) or "reason" not in error:
        return True
    return error["reason"] in RETRY_502_REASONS


def http_json(url: str, data: bytes = None, content_type: str = None, timeout: int = TIMEOUT_S) -> dict:
    """POST (or GET when data is None) and decode JSON, with retry on 503/504 and a retryable 502."""
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        if content_type:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if e.code in RETRY_STATUS and attempt < RETRY_ATTEMPTS and is_retryable(e.code, detail):
                print(f"[retry {attempt}/{RETRY_ATTEMPTS}] HTTP {e.code}, waiting {RETRY_WAIT_S}s...", file=sys.stderr)
                time.sleep(RETRY_WAIT_S)
                last_error = f"HTTP {e.code}: {detail}"
                continue
            print(f"Server error - HTTP {e.code}: {detail}", file=sys.stderr)
            # A 502 from a proxy is not the LLM backend failing; only the service's own 502 is.
            if e.code in HINTS and (e.code != 502 or not is_retryable(e.code, detail)):
                print(f"  -> {HINTS[e.code]}", file=sys.stderr)
            sys.exit(3)
        except (urllib.error.URLError, TimeoutError) as e:
            print(
                f"Cannot reach the API at {url} ({e}).\nIs the server running? Start it with: bash scripts/server.sh",
                file=sys.stderr,
            )
            sys.exit(2)
    print(f"Server error after {RETRY_ATTEMPTS} attempts - {last_error}", file=sys.stderr)
    sys.exit(3)


def options(args) -> dict:
    """The options both endpoints take; the server's defaults apply to what is left out."""
    chosen = {"kind": args.kind, "num_keywords": args.num_keywords, "lang": args.lang}
    if args.method:
        chosen["method"] = args.method
    return chosen


def extract_record(base_url: str, path: Path, args) -> dict:
    """Upload one document record to /extract_keywords."""
    if path.stat().st_size > MAX_UPLOAD_MB * 1024 * 1024:
        print(f"Skipping {path}: exceeds the {MAX_UPLOAD_MB} MB server limit - split the record", file=sys.stderr)
        return {}
    fields = options(args)
    fields["per_page"] = "false" if args.no_per_page else "true"
    body, content_type = build_multipart(fields, {"document_json": path})
    return http_json(f"{base_url}/extract_keywords", data=body, content_type=content_type)


def extract_text(base_url: str, text: str, doc_id: str, args) -> dict:
    """Send one plain text to /extract_keywords_text."""
    payload = dict(options(args), text=text, doc_id=doc_id)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_UPLOAD_MB * 1024 * 1024:
        print(f"Skipping {doc_id}: exceeds the {MAX_UPLOAD_MB} MB server limit - split the text", file=sys.stderr)
        return {}
    return http_json(f"{base_url}/extract_keywords_text", data=body, content_type="application/json")


def text_doc_id(path: Path) -> str:
    """The document id of a text file: its name without the suffix."""
    name = path.name
    for suffix in TEXT_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def result_rows(name: str, result: dict) -> list[tuple]:
    """(FILE, KIND, WHERE, TERM, SCORE, DETAIL) per keyword or per controlled line."""
    rows = []
    for keyword in result.get("keywords") or []:
        detail = f"{keyword.get('method')} #{keyword.get('rank')}"
        rows.append((name, "statistical", "document", keyword.get("keyword"), keyword.get("score"), detail))
    for page in result.get("pages") or []:
        for keyword in page.get("keywords") or []:
            detail = f"{keyword.get('method')} #{keyword.get('rank')}"
            rows.append(
                (name, "statistical", f"page {page.get('page')}", keyword.get("keyword"), keyword.get("score"), detail)
            )
    for item in (result.get("enrichment") or {}).get("items") or []:
        found = "; ".join(item.get("extracted_keywords_cs") or [])
        english = "; ".join(item.get("extracted_keywords_en") or [])
        where = f"page {item.get('page')} line {item.get('line')}"
        detail = f"{found} / {english}" if found or english else ""
        rows.append((name, "controlled", where, item.get("teater_category"), item.get("confidence_score"), detail))
    return rows


def print_table(rows: list[tuple], as_csv: bool) -> None:
    """Aligned table on stdout (the free-text DETAIL column cut to 60 characters), or CSV through
    the csv module, complete."""
    header = ("FILE", "KIND", "WHERE", "TERM", "SCORE", "DETAIL")
    if as_csv:
        writer = csv.writer(sys.stdout)
        writer.writerow(header)
        writer.writerows(rows)
        return

    def cell(value) -> str:
        if isinstance(value, float):
            return f"{value:.3f}"
        return "" if value is None else str(value)

    shown = [
        tuple(cell(v) for v in row[:-1]) + ((cell(row[-1])[:57] + "...") if len(cell(row[-1])) > 60 else cell(row[-1]),)
        for row in rows
    ]
    widths = [max(len(value) for value in column) for column in zip(header, *shown)]
    for row in (header, *shown):
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)).rstrip())


def summarize(name: str, result: dict) -> None:
    """One stderr line per document: what ran and what shaped the result."""
    kinds = ", ".join(f"{k.get('kind')} {k.get('status')}" for k in result.get("kinds") or [])
    line = f"{name}: doc_id {result.get('doc_id')}, {result.get('words')} words; {kinds}"
    if result.get("method_used"):
        line += f"; method {result.get('method_used')}"
    controlled = result.get("controlled") or {}
    if controlled:
        line += f"; controlled {controlled.get('outcome')} ({controlled.get('backend')}, {controlled.get('model')})"
    if result.get("limits_applied"):
        line += f"; limits applied: {len(result['limits_applied'])} (see --format json)"
    print(line, file=sys.stderr)
    for kind in result.get("kinds") or []:
        if kind.get("status") != "ok" and kind.get("detail"):
            print(f"  {kind.get('kind')}: {kind.get('detail')}", file=sys.stderr)


def write_record(out_dir: Path, result: dict) -> None:
    """DIR/<doc_id>.document.json, when the server returned the record."""
    if not result.get("document_json"):
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.get('doc_id') or 'document'}.document.json"
    path.write_text(json.dumps(result["document_json"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path}", file=sys.stderr)


class UsageParser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; the client contract keeps 2 for "server unreachable"."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = UsageParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "files", nargs="*", help="records (*.document.json, *.json), texts (*.txt, *.md), or - for stdin"
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help=f"API base URL (default: {DEFAULT_BASE_URL}, env: ATRIUM_KW_URL)"
    )
    parser.add_argument(
        "--kind",
        choices=["statistical", "controlled", "both"],
        default="both",
        help="which keywords (default: both; controlled needs the server's LLM backend)",
    )
    parser.add_argument(
        "--method", choices=["keybert", "yake", "legacy"], help="statistical method (default: the server's, see --info)"
    )
    parser.add_argument("--num-keywords", type=int, default=20, help="keywords per statistical list (default: 20)")
    parser.add_argument("--no-per-page", action="store_true", help="records: document keywords only, not per page")
    parser.add_argument("--lang", choices=["cs"], default="cs", help="text language (Czech only in v1)")
    parser.add_argument("--doc-id", help="the document id of a text read from stdin (default: stdin)")
    parser.add_argument("--out-dir", type=Path, help="write each returned record as <doc_id>.document.json here")
    parser.add_argument("--format", choices=["table", "csv", "json"], default="table", help="output format")
    parser.add_argument("--info", action="store_true", help="print service capabilities and limits, then exit")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    if args.info:
        print(json.dumps(http_json(f"{base_url}/info", timeout=60), indent=2, ensure_ascii=False))
        return

    if not args.files:
        parser.error("no input given: name records or texts, use - for stdin, or --info")
    if args.num_keywords < 1:
        parser.error("--num-keywords must be at least 1")

    raw_results = {}
    rows = []
    for name in args.files:
        if name == "-":
            text = sys.stdin.read()
            if not text.strip():
                print("Nothing to read on stdin.", file=sys.stderr)
                sys.exit(1)
            label = args.doc_id or "stdin"
            result = extract_text(base_url, text, label, args)
        else:
            path = Path(name)
            if not path.is_file():
                print(f"File not found: {path}", file=sys.stderr)
                sys.exit(1)
            label = path.name
            lower = path.name.lower()
            if lower.endswith(RECORD_SUFFIXES):
                result = extract_record(base_url, path, args)
            elif lower.endswith(TEXT_SUFFIXES):
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    print(f"Skipping {path}: not UTF-8 text", file=sys.stderr)
                    continue
                result = extract_text(base_url, text, text_doc_id(path), args)
            else:
                print(f"Skipping {path}: expected a record (.json) or a text (.txt, .md)", file=sys.stderr)
                continue

        if not result:
            continue
        raw_results[result.get("doc_id") or label] = result
        summarize(label, result)
        if args.out_dir is not None:
            write_record(args.out_dir, result)
        rows.extend(result_rows(label, result))

    if not raw_results:
        print("No results produced.", file=sys.stderr)
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(raw_results, indent=2, ensure_ascii=False))
    else:
        print_table(rows, as_csv=(args.format == "csv"))


if __name__ == "__main__":
    main()
