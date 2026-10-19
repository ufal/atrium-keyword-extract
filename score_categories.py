#!/usr/bin/env python3
"""
score_categories.py — the controlled kind's category picks, run by run (issue #2).

Reads committed or fresh `llm_run.py` outputs (`<dir>/<doc_id>_enriched.json`) and reports,
per run, what a reviewer otherwise counts by hand:

* **coverage** — the lines the run should have answered (the input lines the quality filter
  keeps, with `llm_config.txt`'s filter values) against the lines it did. A failed line is
  absent from the output, so it is counted from the input, never from the output;
* **forced labels** — a category that starts with a capital letter and shares no word with
  the line or its keywords (`Artemísion` for an `artefakt`; the 2026-10-16 table), and the
  named picks of that comment (`zvonice`, `prahory`, `Pentelikon`, `jámová kultura`);
* **no shared word** — any content category that shares no word with the line or its
  keywords. A coarse signal: a correct broader term often shares none (`pohřební areál` for a
  grave), so compare it between runs, never read it as an error count;
* **confidence** — how many distinct values the run used, and the share of its two most
  common ones (91 % on 2026-10-16: the score cannot rank or filter);
* **agreement** — for each pair of runs, how often they pick the same category on the lines
  both call content;
* **gold** — exact accuracy on the lines whose `gold_category` is filled in
  `gold_workbook.csv` (none yet: the report says so);
* **before/after** — a run named `KW_PER_DOC_LLM_R<n>_<model>` against `KW_PER_DOC_LLM_<model>`.

    python3 score_categories.py                         # every data_samples/KW_PER_DOC_LLM_* run
    python3 score_categories.py --runs DIR [DIR ...]    # these runs only
    python3 score_categories.py --input-dir data_samples/DOC_LINE_CATEG   # expected lines from the inputs
    python3 score_categories.py --out TEMP/category_scores               # report.md + four CSVs

The report names documents, pages and lines, labels and counts; it never copies a line's
text, so it can leave the cluster where the document text may not (atrium-project#16).
Torch-free: it needs only the standard library and llm_client_shared.py.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import llm_client_shared as lcs
import prompt_template

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = REPO_ROOT / "data_samples" / "vocab" / "gold_workbook.csv"
DEFAULT_CONFIG = REPO_ROOT / "llm_config.txt"
DEFAULT_RUNS_GLOB = "KW_PER_DOC_LLM_*"
DEFAULT_OUT = REPO_ROOT / "TEMP" / "category_scores"
EXIT_USAGE = 2

#: The forced picks named in the 2026-10-16 comment on issue #2, each counted when it shares no
#: word with its line: the decoder finished a prefix the model began as the one label sharing it.
WATCH_LABELS = ("Artemísion", "zvonice", "prahory", "Pentelikon", "jámová kultura")

#: A word is its first five letters, so `zvonice` and `zvoncový` differ while `hradiště` and
#: `hradišti` agree. Words under three letters (`a`, `u`, `na`) carry nothing.
_STEM = 5
_WORD = re.compile(r"\w+")

#: `KW_PER_DOC_LLM_R3_qwen_38_27b_it` is a re-run of `KW_PER_DOC_LLM_qwen_38_27b_it`.
_RERUN = re.compile(r"^(?P<prefix>.+?)_R\d+_(?P<model>.+)$")

Key = Tuple[str, int, int]


def _stems(text: str) -> set:
    return {word[:_STEM] for word in _WORD.findall(text.casefold()) if len(word) >= 3}


def _key(file_id: Any, page: Any, line: Any) -> Optional[Key]:
    try:
        return str(file_id), int(page), int(line)
    except (TypeError, ValueError):
        return None


# ── expected lines ───────────────────────────────────────────────────────────────


def _filter_settings(config: Dict[str, str]) -> Dict[str, Any]:
    """The four quality-filter values exactly as `llm_run.py` reads them."""
    return {
        "include_non_text": config.get("INCLUDE_NON_TEXT", "true").lower() == "true",
        "min_char_count": int(config.get("MIN_CHAR_COUNT", "3")),
        "min_char_non_text": int(config.get("MIN_CHAR_NON_TEXT", "8")),
        "min_alpha_ratio_non_text": float(config.get("MIN_ALPHA_RATIO_NON_TEXT", "0.40")),
    }


def _keeps(text: str, categ: str, quality: Optional[float], settings: Dict[str, Any]) -> bool:
    keep, _reason = lcs.should_process_line(
        (text or "").strip(),
        (categ or "").strip(),
        quality,
        settings["include_non_text"],
        settings["min_char_count"],
        settings["min_char_non_text"],
        settings["min_alpha_ratio_non_text"],
    )
    return keep


def read_workbook(path: Path) -> List[Dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def expected_from_workbook(rows: Iterable[Dict[str, str]], settings: Dict[str, Any]) -> set:
    """The lines a run must answer, from `gold_workbook.csv` (one row per input line)."""
    expected = set()
    for row in rows:
        key = _key(row.get("file_id"), row.get("page"), row.get("line"))
        if key and _keeps(
            row.get("original_text", ""), row.get("categ", ""), lcs.row_quality(row), settings
        ):
            expected.add(key)
    return expected


def expected_from_inputs(input_dir: Path, settings: Dict[str, Any]) -> set:
    """The lines a run must answer, from the input CSVs `llm_run.py` reads (`INPUT_DIR`)."""
    expected = set()
    for path in sorted(input_dir.glob("*.csv")):
        for row in lcs.read_input_rows(path):
            file_id = row.get("file") or path.stem
            key = _key(
                file_id, row.get("page_num", row.get("page")), row.get("line_num", row.get("line"))
            )
            if key and _keeps(
                row.get("text", ""), row.get("categ", ""), lcs.row_quality(row), settings
            ):
                expected.add(key)
    return expected


def gold_labels(rows: Iterable[Dict[str, str]]) -> Dict[Key, str]:
    gold = {}
    for row in rows:
        key = _key(row.get("file_id"), row.get("page"), row.get("line"))
        label = (row.get("gold_category") or "").strip()
        if key and label:
            gold[key] = label
    return gold


# ── one run ──────────────────────────────────────────────────────────────────────


@dataclass
class Pick:
    category: str
    confidence: Optional[float]
    supported: bool


@dataclass
class Run:
    name: str
    path: Path
    picks: Dict[Key, Pick] = field(default_factory=dict)
    documents: int = 0
    unreadable: List[str] = field(default_factory=list)


def read_run(path: Path) -> Run:
    run = Run(name=path.name, path=path)
    for file in sorted(path.glob("*_enriched.json")):
        try:
            records = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            run.unreadable.append(f"{file.name}: {exc}")
            continue
        if not isinstance(records, list):
            run.unreadable.append(f"{file.name}: not a list of line records")
            continue
        run.documents += 1
        for record in records:
            enrichment = record.get("enrichment") or {}
            key = _key(record.get("file_id"), record.get("page"), record.get("line"))
            category = enrichment.get("teater_category")
            if key is None or not isinstance(category, str):
                continue
            context = " ".join(
                [
                    record.get("original_text") or "",
                    *(enrichment.get("extracted_keywords_cs") or []),
                ]
            )
            confidence = enrichment.get("confidence_score")
            run.picks[key] = Pick(
                category=category,
                confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                supported=bool(_stems(category) & _stems(context)),
            )
    return run


def _content(run: Run) -> Dict[Key, Pick]:
    return {key: pick for key, pick in run.picks.items() if pick.category != lcs.META_TERM}


def forced_capital(run: Run) -> Counter:
    """Capitalised labels on lines that share no word with them: the 2026-10-16 table."""
    return Counter(
        pick.category
        for pick in _content(run).values()
        if pick.category[:1].isupper() and not pick.supported
    )


def watch_hits(run: Run) -> Counter:
    return Counter(
        pick.category
        for pick in _content(run).values()
        if pick.category in WATCH_LABELS and not pick.supported
    )


def _top(counter: Counter, n: int = 3) -> str:
    return "; ".join(f"{label} {count}" for label, count in counter.most_common(n))


def run_row(run: Run, expected: set, gold: Dict[Key, str]) -> Dict[str, Any]:
    produced = set(run.picks)
    content = _content(run)
    confidences = [pick.confidence for pick in content.values() if pick.confidence is not None]
    top_two = sum(count for _value, count in Counter(confidences).most_common(2))
    capital = forced_capital(run)
    watched = watch_hits(run)
    unsupported = Counter(pick.category for pick in content.values() if not pick.supported)
    gold_keys = [key for key in gold if key in run.picks]
    gold_exact = sum(run.picks[key].category == gold[key] for key in gold_keys)
    return {
        "run": run.name,
        "documents": run.documents,
        "expected": len(expected),
        "produced": len(produced),
        "missing": len(expected - produced),
        "unexpected": len(produced - expected),
        "meta": len(produced) - len(content),
        "meta_share": _share(len(produced) - len(content), len(produced)),
        "content": len(content),
        "distinct_categories": len({pick.category for pick in content.values()}),
        "composite_categories": sum("/" in pick.category for pick in content.values()),
        "forced_capital": sum(capital.values()),
        "forced_capital_top": _top(capital),
        "watch_hits": sum(watched.values()),
        "watch_top": _top(watched, len(WATCH_LABELS)),
        "no_shared_word": sum(unsupported.values()),
        "no_shared_word_share": _share(sum(unsupported.values()), len(content)),
        "no_shared_word_top": _top(unsupported),
        "confidence_distinct": len(set(confidences)),
        "confidence_top2_share": _share(top_two, len(confidences)),
        "confidence_mean": round(sum(confidences) / len(confidences), 3) if confidences else "",
        "gold_lines": len(gold_keys),
        "gold_exact": gold_exact if gold_keys else "",
        "gold_accuracy": _share(gold_exact, len(gold_keys)) if gold_keys else "",
    }


def _share(part: int, whole: int) -> Any:
    return round(part / whole, 3) if whole else ""


# ── between runs ─────────────────────────────────────────────────────────────────


def agreement(a: Run, b: Run) -> Tuple[int, int]:
    """(lines both call content, of which the same category)."""
    left, right = _content(a), _content(b)
    both = left.keys() & right.keys()
    return len(both), sum(left[key].category == right[key].category for key in both)


def agreement_rows(runs: Sequence[Run]) -> List[Dict[str, Any]]:
    rows = []
    for a, b in combinations(runs, 2):
        both, same = agreement(a, b)
        rows.append(
            {
                "run_a": a.name,
                "run_b": b.name,
                "both_content": both,
                "same": same,
                "agreement": _share(same, both),
            }
        )
    return rows


def baseline_name(name: str) -> Optional[str]:
    match = _RERUN.match(name)
    return f"{match['prefix']}_{match['model']}" if match else None


def before_after_rows(
    runs: Sequence[Run], rows_by_run: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    by_name = {run.name: run for run in runs}
    out = []
    for run in runs:
        base_name = baseline_name(run.name)
        base = by_name.get(base_name or "")
        if base is None:
            continue
        after, before = rows_by_run[run.name], rows_by_run[base.name]
        both, same = agreement(run, base)
        changed = sum(
            run.picks[key].category != base.picks[key].category
            for key in run.picks.keys() & base.picks.keys()
        )
        row: Dict[str, Any] = {"run": run.name, "baseline": base.name}
        for metric in (
            "missing",
            "meta",
            "forced_capital",
            "watch_hits",
            "no_shared_word",
            "composite_categories",
            "confidence_distinct",
            "confidence_top2_share",
        ):
            row[f"{metric}_before"] = before[metric]
            row[f"{metric}_after"] = after[metric]
        row["lines_changed"] = changed
        row["content_agreement"] = _share(same, both)
        out.append(row)
    return out


def forced_rows(runs: Sequence[Run]) -> List[Dict[str, Any]]:
    """Each forced pick, located but without its text."""
    rows = []
    for run in runs:
        for (file_id, page, line), pick in sorted(_content(run).items()):
            if pick.supported:
                continue
            reason = (
                "capital"
                if pick.category[:1].isupper()
                else "watch"
                if pick.category in WATCH_LABELS
                else ""
            )
            if reason:
                rows.append(
                    {
                        "run": run.name,
                        "file_id": file_id,
                        "page": page,
                        "line": line,
                        "category": pick.category,
                        "confidence": pick.confidence,
                        "reason": reason,
                    }
                )
    return rows


# ── output ───────────────────────────────────────────────────────────────────────

RUN_COLUMNS = [
    "run",
    "documents",
    "expected",
    "produced",
    "missing",
    "unexpected",
    "meta",
    "meta_share",
    "content",
    "distinct_categories",
    "composite_categories",
    "forced_capital",
    "forced_capital_top",
    "watch_hits",
    "watch_top",
    "no_shared_word",
    "no_shared_word_share",
    "no_shared_word_top",
    "confidence_distinct",
    "confidence_top2_share",
    "confidence_mean",
    "gold_lines",
    "gold_exact",
    "gold_accuracy",
]
AGREEMENT_COLUMNS = ["run_a", "run_b", "both_content", "same", "agreement"]
FORCED_COLUMNS = ["run", "file_id", "page", "line", "category", "confidence", "reason"]


def _csv_text(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _md_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return "\n".join(lines)


def report_markdown(
    run_rows: Sequence[Dict[str, Any]],
    agreement: Sequence[Dict[str, Any]],
    before_after: Sequence[Dict[str, Any]],
    expected_source: str,
    gold_count: int,
) -> str:
    parts = [
        "# Category scores (issue #2)",
        "",
        f"Expected lines: from {expected_source}, through `should_process_line` with `llm_config.txt`'s "
        "filter. `missing` lines failed in the run; `forced_capital` and `watch_hits` share no word with "
        "their line or its keywords. `no_shared_word` is coarse: a correct broader term often shares none.",
        "",
        "## Runs",
        "",
        _md_table(
            run_rows,
            [
                "run",
                "expected",
                "missing",
                "meta_share",
                "forced_capital",
                "forced_capital_top",
                "watch_hits",
                "no_shared_word_share",
                "composite_categories",
                "confidence_top2_share",
            ],
        ),
        "",
        "## Gold",
        "",
        (
            f"{gold_count} lines carry a `gold_category`; `gold_accuracy` in `runs.csv` is exact match on them."
            if gold_count
            else "No gold yet: `gold_category` is empty in `gold_workbook.csv`, so no accuracy is reported."
        ),
    ]
    if before_after:
        parts += [
            "",
            "## Before and after",
            "",
            _md_table(
                before_after,
                [
                    "run",
                    "baseline",
                    "missing_before",
                    "missing_after",
                    "forced_capital_before",
                    "forced_capital_after",
                    "watch_hits_before",
                    "watch_hits_after",
                    "no_shared_word_before",
                    "no_shared_word_after",
                    "confidence_top2_share_before",
                    "confidence_top2_share_after",
                    "lines_changed",
                    "content_agreement",
                ],
            ),
        ]
    if agreement:
        parts += [
            "",
            "## Agreement",
            "",
            "Same category on the lines both runs call content. All pairs are in `agreement.csv`; "
            "the ten closest are here.",
            "",
            _md_table(
                sorted(agreement, key=lambda row: -(row["agreement"] or 0))[:10],
                AGREEMENT_COLUMNS,
            ),
        ]
    return "\n".join(parts) + "\n"


def score(
    run_dirs: Sequence[Path],
    workbook: Path,
    config: Dict[str, str],
    input_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Every table, in memory: `runs`, `agreement`, `before_after`, `forced`, `report`."""
    settings = _filter_settings(config)
    workbook_rows = read_workbook(workbook) if workbook.is_file() else []
    if input_dir is not None:
        expected = expected_from_inputs(input_dir, settings)
        source = f"the input CSVs in `{input_dir}`"
    else:
        expected = expected_from_workbook(workbook_rows, settings)
        source = f"`{workbook.name}`"
    gold = gold_labels(workbook_rows)
    runs = [read_run(path) for path in run_dirs]
    rows_by_run = {run.name: run_row(run, expected, gold) for run in runs}
    run_rows = [rows_by_run[run.name] for run in runs]
    agreement = agreement_rows(runs)
    before_after = before_after_rows(runs, rows_by_run)
    return {
        "runs": run_rows,
        "agreement": agreement,
        "before_after": before_after,
        "forced": forced_rows(runs),
        "unreadable": [f"{run.name}/{item}" for run in runs for item in run.unreadable],
        "report": report_markdown(run_rows, agreement, before_after, source, len(gold)),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--runs", nargs="+", type=Path, help="run folders (default: data_samples/KW_PER_DOC_LLM_*)"
    )
    p.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help="gold_workbook.csv: expected lines and gold",
    )
    p.add_argument(
        "--input-dir", type=Path, help="take the expected lines from these input CSVs instead"
    )
    p.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="llm_config.txt: the quality filter"
    )
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where report.md and the CSVs go")
    return p


def main(argv: Any = None) -> int:
    args = build_parser().parse_args(argv)
    run_dirs = args.runs or sorted(
        p for p in (REPO_ROOT / "data_samples").glob(DEFAULT_RUNS_GLOB) if p.is_dir()
    )
    problems = [f"run folder {p} does not exist" for p in run_dirs if not p.is_dir()]
    if not run_dirs:
        problems.append(
            "no run folders: pass --runs, or run from a checkout with data_samples/KW_PER_DOC_LLM_*"
        )
    if args.input_dir is None and not args.workbook.is_file():
        problems.append(
            f"{args.workbook} is missing: pass --input-dir with the input CSVs, or run "
            "`python3 corpus_review.py --gold-workbook`"
        )
    if args.input_dir is not None and not args.input_dir.is_dir():
        problems.append(f"--input-dir {args.input_dir} is not a folder")
    if not args.config.is_file():
        problems.append(f"{args.config} is missing: pass --config llm_config.txt")
    if problems:
        for problem in problems:
            print(f"[error] {problem}", file=sys.stderr)
        return EXIT_USAGE

    config = prompt_template.load_run_config(args.config)
    result = score(run_dirs, args.workbook, config, input_dir=args.input_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "runs.csv").write_text(_csv_text(result["runs"], RUN_COLUMNS), encoding="utf-8")
    (args.out / "agreement.csv").write_text(
        _csv_text(result["agreement"], AGREEMENT_COLUMNS), encoding="utf-8"
    )
    (args.out / "forced_labels.csv").write_text(
        _csv_text(result["forced"], FORCED_COLUMNS), encoding="utf-8"
    )
    if result["before_after"]:
        columns = list(result["before_after"][0])
        (args.out / "before_after.csv").write_text(
            _csv_text(result["before_after"], columns), encoding="utf-8"
        )
    (args.out / "report.md").write_text(result["report"], encoding="utf-8")
    for item in result["unreadable"]:
        print(f"[warn] unreadable output: {item}", file=sys.stderr)
    print(
        f"[write] {args.out}: report.md, runs.csv, agreement.csv, forced_labels.csv"
        + (", before_after.csv" if result["before_after"] else "")
    )
    for row in result["runs"]:
        print(
            f"  {row['run']}: {row['produced']}/{row['expected']} lines, missing {row['missing']}, "
            f"forced {row['forced_capital']}, watched {row['watch_hits']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
