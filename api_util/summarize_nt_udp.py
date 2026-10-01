import argparse
import csv
import os
import re
import sys
from pathlib import Path

# Inject project root into sys.path so 'api_util' package absolute imports resolve
# correctly when the script is invoked directly from the command line.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import tool_limits  # noqa: E402
from api_util import doc_identity as _doc_identity  # noqa: E402
from api_util import page_rows as _page_rows  # noqa: E402
from api_util.teitok_alto import write_teitok_merged  # noqa: E402
from atrium_document import canonical_doc_id  # noqa: E402
from atrium_paradata import ParadataLogger  # noqa: E402

# Increase CSV field size limit just in case
csv.field_size_limit(sys.maxsize)

# --- CNEC 2.0 Type Hierarchy Mapping ---
CNEC_TYPE_MAP = {
    "a": "Address/Number/Time (General)",
    "A": "Complex Address/Number/Time",
    "ah": "Street address",
    "at": "Phone/Fax number",
    "az": "Zip code",
    "g": "Geographical name (General)",
    "G": "Geographical name (General)",
    "g_": "Geographical name (General)",
    "gu": "Settlement name (City/Town)",
    "gl": "Nature/Landscape name (Mountain/River)",
    "gq": "Urban geographical name (Street/Square)",
    "gr": "Territorial name (State/Region)",
    "gs": "Super-terrestrial name (Star/Planet)",
    "gc": "States/Provinces/Regions",
    "gt": "Continents",
    "gh": "Hydronym (Bodies of water)",
    "i": "Institution name (General)",
    "i_": "Institution name (General)",
    "I": "Institution name (General)",
    "ia": "Conference/Contest",
    "if": "Company/Firm",
    "io": "Organization/Society",
    "ic": "Cult/Educational institution",
    "m": "Media name (General)",
    "mn": "Periodical name (Newspaper/Magazine)",
    "ms": "Radio/TV station",
    "mi": "Internet links",
    "o": "Artifact name (General)",
    "o_": "Artifact name (General)",
    "oa": "Cultural artifact (Book/Painting)",
    "oe": "Measure unit",
    "om": "Currency",
    "or": "Directives, norms",
    "op": "Product (General)",
    "p": "Personal name (General)",
    "p_": "Personal name (General)",
    "P": "Complex personal names",
    "pf": "First name",
    "ps": "Surname",
    "pm": "Second name",
    "ph": "Nickname/Pseudonym",
    "pc": "Inhabitant name",
    "pd": "Academic titles",
    "pp": "Relig./myth persons",
    "me": "Email address",
    "t": "Time expression (General)",
    "T": "Complex time expressions",
    "td": "Day",
    "th": "Hour",
    "tm": "Month",
    "ty": "Year",
    "tf": "Holiday/Feast",
    "tt": "Time block",
    "n": "Number expression (General)",
    "N": "Complex number expressions",
    "n_": "Number expression (General)",
    "na": "Age",
    "nb": "Volu-metric number",
    "nc": "Cardinal number",
    "ni": "Itemizer (1.)",
    "no": "Ordinal number",
    "ns": "Sport score",
    "unk": "Unknown Type",
    "O": "None",
    "C": "Complex bibliographic expression",
    # Archaeo Domain
    "ARTEFACT": "Archaeological Artifact",
    "PERIOD": "Time Period",
    "LOCATION": "Geographical Location",
    "CONTEXT": "Archaeological Context",
    "MATERIAL": "Material",
    "SPECIES": "Biological Species",
}

# --- OntoNotes v5 Type Hierarchy Mapping ---
ONTO_TYPE_MAP = {
    "PERSON": "People, including fictional",
    "NORP": "Nationalities or religious or political groups",
    "FAC": "Buildings, airports, highways, bridges, etc.",
    "ORG": "Companies, agencies, institutions, etc.",
    "GPE": "Countries, cities, states",
    "LOC": "Non-GPE locations, mountain ranges, bodies of water",
    "PRODUCT": "Objects, vehicles, foods, etc. (not services)",
    "EVENT": "Named hurricanes, battles, wars, sports events, etc.",
    "WORK_OF_ART": "Titles of books, songs, etc.",
    "LAW": "Named documents made into laws",
    "LANGUAGE": "Any named language",
    "DATE": "Absolute or relative dates or periods",
    "TIME": "Times smaller than a day",
    "PERCENT": "Percentage, including '%'",
    "MONEY": "Monetary values, including unit",
    "QUANTITY": "Measurements, as of weight or distance",
    "ORDINAL": '"first", "second", etc.',
    "CARDINAL": "Numerals that do not fall under another type",
    "MISC": "Miscellaneous entities",
}

# --- CNEC to ONTO Mapping ---
CNEC_TO_ONTO_MAP = {
    "p": "PERSON",
    "p_": "PERSON",
    "P": "PERSON",
    "pf": "PERSON",
    "ps": "PERSON",
    "pm": "PERSON",
    "ph": "PERSON",
    "pd": "PERSON",
    "pp": "PERSON",
    "pc": "NORP",
    "g": "GPE",
    "G": "GPE",
    "g_": "GPE",
    "gu": "GPE",
    "gr": "GPE",
    "gc": "GPE",
    "gl": "LOC",
    "gs": "LOC",
    "gt": "LOC",
    "gh": "LOC",
    "gq": "FAC",
    "i": "ORG",
    "i_": "ORG",
    "I": "ORG",
    "if": "ORG",
    "io": "ORG",
    "ic": "ORG",
    "ia": "EVENT",
    "o": "PRODUCT",
    "o_": "PRODUCT",
    "op": "PRODUCT",
    "oa": "WORK_OF_ART",
    "oe": "QUANTITY",
    "om": "MONEY",
    "or": "LAW",
    "m": "ORG",
    "mn": "WORK_OF_ART",
    "ms": "ORG",
    "mi": "ORG",
    "t": "TIME",
    "T": "TIME",
    "th": "TIME",
    "tt": "TIME",
    "td": "DATE",
    "tm": "DATE",
    "ty": "DATE",
    "tf": "EVENT",
    "n": "CARDINAL",
    "N": "CARDINAL",
    "n_": "CARDINAL",
    "nc": "CARDINAL",
    "ns": "CARDINAL",
    "na": "DATE",
    "nb": "QUANTITY",
    "ni": "ORDINAL",
    "no": "ORDINAL",
    "a": "LOC",
    "A": "LOC",
    "ah": "FAC",
    "at": "CARDINAL",
    "az": "CARDINAL",
    "me": "CARDINAL",
    "C": "WORK_OF_ART",
    "unk": "O",
    "O": "O",
    # Archaeo Domain
    "LOCATION": "LOC",
    "ARTEFACT": "MISC",
    "PERIOD": "MISC",
    "CONTEXT": "MISC",
    "MATERIAL": "MISC",
    "SPECIES": "MISC",
}


def _float_or_none(value):
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def bool_from_str(s, default=False):
    if s is None:
        return default
    if isinstance(s, bool):
        return s
    s = str(s).strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def get_ne_explanation(raw_tag):
    if raw_tag == "O" or not raw_tag or raw_tag == "_":
        return ""
    if raw_tag.startswith("B-") or raw_tag.startswith("I-"):
        primary = raw_tag.split("|")[0]
        short_code = primary[2:]

        if short_code in ONTO_TYPE_MAP:
            return ONTO_TYPE_MAP[short_code]

        if short_code in CNEC_TO_ONTO_MAP:
            onto_mapped = CNEC_TO_ONTO_MAP[short_code]
            return ONTO_TYPE_MAP.get(
                onto_mapped, CNEC_TYPE_MAP.get(short_code, f"Unknown Code ({short_code})")
            )

        return CNEC_TYPE_MAP.get(short_code, f"Unknown Code ({short_code})")

    return ""


def get_sorted_tsv_content(doc_tsv_dir):
    all_data = []
    files = list(Path(doc_tsv_dir).glob("*.tsv"))

    def sort_key(filepath):
        try:
            match = re.search(r"-(\d+)\.tsv$", filepath.name)
            if match:
                return int(match.group(1))
            return 0
        except Exception:
            return 0

    files.sort(key=sort_key)

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            next(f, None)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    all_data.append({"token": parts[0], "tag": parts[1]})
                else:
                    all_data.append({"token": parts[0], "tag": "O"})
    return all_data


def merge_and_write(conllu_path, tsv_data, output_path):
    tsv_index = 0
    tsv_len = len(tsv_data)
    try:
        with (
            open(conllu_path, "r", encoding="utf-8") as f_conllu,
            open(output_path, "w", encoding="utf-8") as f_out,
        ):
            for line in f_conllu:
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith("#"):
                    f_out.write(line)
                    continue

                cols = stripped_line.split("\t")
                if len(cols) >= 2 and "-" not in cols[0] and "." not in cols[0]:
                    if tsv_index < tsv_len:
                        tsv_item = tsv_data[tsv_index]
                        new_attr = f"NER={tsv_item['tag']}"
                        if len(cols) > 9:
                            if cols[9] == "_":
                                cols[9] = new_attr
                            else:
                                cols[9] += f"|{new_attr}"
                        else:
                            while len(cols) < 9:
                                cols.append("_")
                            cols.append(new_attr)
                        f_out.write("\t".join(cols) + "\n")
                        tsv_index += 1
                    else:
                        f_out.write(line)
                else:
                    f_out.write(line)
        return True
    except Exception as e:
        print(f"Error merging {conllu_path}: {e}", file=sys.stderr)
        return False


def parse_features(feat_str):
    if feat_str == "_" or not feat_str:
        return {}
    return {k: v for item in feat_str.split("|") if "=" in item for k, v in [item.split("=", 1)]}


def parse_misc(misc_str):
    if misc_str == "_" or not misc_str:
        return {}
    misc = {}
    for item in misc_str.split("|"):
        if "=" in item:
            k, v = item.split("=", 1)
            misc[k] = v
        else:
            misc[item] = "Yes"
    return misc


def write_document_csv(rows, out_path):
    if not rows:
        return
    feature_keys = set()
    misc_keys = set()
    for r in rows:
        for k in r.keys():
            if k.startswith("udpipe.feats."):
                feature_keys.add(k)
            elif k.startswith("udpipe.misc."):
                misc_keys.add(k)

    header = (
        ["page_id", "token", "lemma", "position", "nameTag", "NE"]
        + sorted(list(feature_keys))
        + sorted(list(misc_keys))
    )
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_ALL, quotechar='"')
            writer.writeheader()
            writer.writerows(rows)
    except Exception as e:
        print(f"  [Error] writing {out_path}: {e}", file=sys.stderr)


# ── FIX #8: single-pass reader ───────────────────────────────────────────────


def _collect_merged_rows(merged_filepath, rows=None, doc_id=""):
    """The per-token rows of ``<doc>.csv`` and the entities of each page.

    A token's ``page_id`` is the page of the line it came from, by the document's rows file
    (``page_rows.word_pages``); an entity counts on the page of its ``B-`` token. Without a
    rows file, only an old per-page CoNLL-U (``# sent_id = 1`` restarting) has more than one
    page. UDPipe chunk starts (``# chunk_start``, formerly ``# page_break = true``) are never
    pages -- they used to be, which made "pages" of ~900-word chunks (issue #38, A)."""
    all_rows = []
    entities_by_page: dict = {}
    word_pages = [
        page for sent in _page_rows.word_pages(merged_filepath, rows, doc_id) for page in sent
    ]
    word_no = 0
    page = 1
    current_entity_toks: list = []
    current_entity_type = None
    current_entity_page = 1

    def _flush_entity():
        nonlocal current_entity_toks, current_entity_type
        if current_entity_toks and current_entity_type:
            text = " ".join(current_entity_toks)
            entities_by_page.setdefault(current_entity_page, []).append((text, current_entity_type))
        current_entity_toks, current_entity_type = [], None

    try:
        with open(merged_filepath, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue

                cols = line.split("\t")
                if len(cols) < 10 or "-" in cols[0]:
                    continue
                if "." not in cols[0]:  # an empty node stays on the page of the word before it
                    if word_no < len(word_pages):
                        page = word_pages[word_no]
                    word_no += 1

                misc = parse_misc(cols[9])
                feats = parse_features(cols[5])
                ner_tag = misc.get("NER", "")

                row = {
                    "page_id": page,
                    "token": cols[1],
                    "lemma": cols[2],
                    "position": cols[0],
                    "nameTag": ner_tag,
                    "NE": get_ne_explanation(ner_tag),
                }
                for k, v in feats.items():
                    row[f"udpipe.feats.{k}"] = v
                for k, v in misc.items():
                    if k != "NER":
                        row[f"udpipe.misc.{k}"] = v
                all_rows.append(row)

                if ner_tag.startswith("B-"):
                    _flush_entity()
                    current_entity_toks = [cols[1]]
                    current_entity_type = get_ne_explanation(ner_tag)
                    current_entity_page = page
                elif ner_tag.startswith("I-") and current_entity_toks:
                    current_entity_toks.append(cols[1])
                else:
                    _flush_entity()

            _flush_entity()

    except Exception as exc:
        print(f"  [Warn] collecting merged rows from {merged_filepath}: {exc}", file=sys.stderr)
        return [], {}

    return all_rows, entities_by_page


def process_merged_file(merged_filepath, output_csv_path, rows=None, doc_id=""):
    csv_rows, _ = _collect_merged_rows(merged_filepath, rows, doc_id)
    if csv_rows:
        write_document_csv(csv_rows, output_csv_path)


def _write_summary_rows_from_data(doc_name, entities_by_page, summary_csv_path):
    """Append one summary row per page: its NE_SUMMARY_TOP_N most frequent entities.

    Returns how many pages had more distinct entities than that, which the caller
    records as a ``trimmed`` note (atrium-project#53; the TEITOK and the document record
    carry every entity). The top N was the literal 20 before it became a setting; a CSV
    written under another N keeps its own header, so write one file per setting.
    """
    from collections import Counter

    if not summary_csv_path or not entities_by_page:
        return 0
    top_n = tool_limits.NE_SUMMARY_TOP_N.get()
    trimmed = 0
    write_header = not os.path.isfile(summary_csv_path)
    try:
        with open(summary_csv_path, "a", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, quoting=csv.QUOTE_ALL, quotechar='"')
            if write_header:
                header = ["file", "page"] + [
                    x for i in range(1, top_n + 1) for x in (f"ne{i}", f"type{i}", f"cnt-{i}")
                ]
                w.writerow(header)
            for page_num, ents in sorted(entities_by_page.items()):
                counts = Counter(ents)
                trimmed += len(counts) > top_n
                c = counts.most_common(top_n)
                row = [doc_name, page_num]
                for (ne_text, ne_type), cnt in c:
                    row.extend([ne_text, ne_type, cnt])
                missing = top_n - len(c)
                if missing > 0:
                    row.extend(["", "", 0] * missing)
                w.writerow(row)
    except Exception as exc:
        print(f"  [Warn] writing summary CSV: {exc}", file=sys.stderr)
    return trimmed


def append_summary_row(doc_name, merged_conllu_path, summary_csv_path, rows=None):
    _, entities_by_page = _collect_merged_rows(merged_conllu_path, rows, doc_name)
    return _write_summary_rows_from_data(doc_name, entities_by_page, summary_csv_path)


def note_summary_trimmed(para_state, pages):
    """Record in the stage's paradata (the ``atrium_paradata.py start`` state file) that
    ``pages`` pages kept only their NE_SUMMARY_TOP_N most frequent entities."""
    if not para_state or not pages:
        return
    import subprocess

    top_n = tool_limits.NE_SUMMARY_TOP_N.get()
    subprocess.run(
        [
            sys.executable,
            str(_project_root / "atrium_paradata.py"),
            "note-limit",
            "--state",
            str(para_state),
            "--limit",
            "ne_summary_top_n",
            "--value",
            str(top_n),
            "--effect",
            "trimmed",
            "--count",
            str(pages),
            "--detail",
            f"page(s) with more than {top_n} distinct entities kept their {top_n} most frequent "
            "in the entity summary (the TEITOK and the document record carry every entity)",
        ],
        check=False,
    )


# ── layout source: ALTO, or a flexiconv TEITOK file (FLEXICONV_ANNOTATE) ──────


def layout_source(doc_name, alto_dir=None, flexiconv_dir=None):
    """The file stage 4 takes a document's page layout from, or None: its ALTO, else its
    converted flexiconv file. The rules live in ``api_util/doc_identity.py`` so stage 1
    (which converted files a table claims) and stage 4 cannot disagree (issue #38, B)."""
    return _doc_identity.layout_source(doc_name, alto_dir, flexiconv_dir)


# ── per-document entry point (called from api_4_stats.sh) ────────────────────


def process_single_document(
    conllu_file,
    ne_dir,
    output_dir,
    save_conllu=True,
    save_csv=True,
    save_teitok=False,
    alto_dir=None,
    teitok_out=None,
    pages_dir=None,
    summary_csv=None,
    model_udpipe=None,
    model_nametag=None,
    dpi=None,
    alto_dpi=None,
    document_json_dir=None,
    document_run_id=None,
    document_paradata_ref="",
    document_run_uuid=None,
    document_license_detail=None,
    include_lines=False,
    bbox_origin="page",
    flexiconv_dir=None,
    text_dir=None,
    para_state=None,
):
    conllu_path = Path(conllu_file)
    # canonical_doc_id(), not Path.stem (issue atrium-project#10, D3): `.conllu` is this
    # repo's working currency and `Path("X.udpipe.conllu").stem` is "X.udpipe", which then
    # travels into teitok_ref, the summary CSV's doc column and the document record's
    # entities[]/pages[] — a second identity for a document every other stage calls "X".
    doc_name = canonical_doc_id(conllu_path)
    doc_out_dir = Path(output_dir)
    doc_out_conllu = doc_out_dir / f"{doc_name}.conllu"
    doc_out_csv = doc_out_dir / f"{doc_name}.csv"

    teitok_out_path = Path(teitok_out) / f"{doc_name}.teitok.xml" if teitok_out else None

    if save_teitok and teitok_out_path:
        teitok_out_path.parent.mkdir(parents=True, exist_ok=True)

    # TEITOK is written below, from the NER-merged CoNLL-U -- never before the merge, when
    # the file it reads may not exist yet (or, on a resumed run, be stale).

    # Merge NER tags into CoNLL-U if not already done
    merged_conllu_ready = doc_out_conllu.exists()
    if not merged_conllu_ready:
        ne_dir_path = Path(ne_dir)
        if not ne_dir_path.exists():
            print(f"  [Skip] NE dir not found: {ne_dir}", file=sys.stderr)
            return False
        tsv_data = get_sorted_tsv_content(ne_dir_path)
        if not tsv_data:
            print(f"  [Warn] No valid TSV data in {ne_dir}", file=sys.stderr)
            return False
        merged_conllu_ready = merge_and_write(conllu_path, tsv_data, doc_out_conllu)
        if not merged_conllu_ready:
            print(f"  [Error] Failed to create merged CoNLL-U for {doc_name}", file=sys.stderr)
            return False

    # The lines the text came from, with their pages (stage 1's rows file, frozen next to the
    # CoNLL-U by stage 2; issue #38, A).
    rows_path = _page_rows.find_rows(conllu_path, text_dir)
    rows = _page_rows.read_rows(rows_path) if rows_path else None
    if not rows:
        print(
            f"  [pages] {doc_name}: no rows file next to {conllu_path.name}; page numbers of "
            f"the CSV and the summary fall back to 1 (re-run from stage 1 to get them)",
            file=sys.stderr,
        )

    need_csv = save_csv and not doc_out_csv.exists()
    need_summary = bool(summary_csv)

    if need_csv or need_summary:
        csv_rows, entities_by_page = _collect_merged_rows(doc_out_conllu, rows, doc_name)
        if need_csv:
            write_document_csv(csv_rows, doc_out_csv)
        if need_summary:
            trimmed = _write_summary_rows_from_data(doc_name, entities_by_page, summary_csv)
            note_summary_trimmed(para_state, trimmed)

    layout = layout_source(doc_name, alto_dir, flexiconv_dir)
    if save_teitok and teitok_out_path and not teitok_out_path.exists():
        write_teitok_merged(
            doc_out_conllu,
            teitok_out_path,
            layout,
            doc_id=doc_name,
            model_udpipe=model_udpipe,
            model_nametag=model_nametag,
            image_dir=pages_dir or None,
            dpi=dpi,
            alto_dpi=alto_dpi,
            bbox_origin=bbox_origin,
            rows=rows,
            source_file=_page_rows.rows_source(rows_path) if rows_path else None,
        )

    if document_json_dir:
        from api_util.document_hook import run_document_hook

        baseline_json = os.path.join(document_json_dir, f"{doc_name}.document.json")
        out_json = baseline_json  # In-place accretion
        if not os.path.exists(baseline_json):
            baseline_json = None  # Graceful fallback to rule 3 (own part only)

        try:
            run_document_hook(
                doc_id=doc_name,
                teitok_path=str(teitok_out_path) if teitok_out_path else "",
                conllu_path=str(doc_out_conllu),
                baseline_json=baseline_json,
                out_json=out_json,
                run_id=document_run_id,
                run_uuid=document_run_uuid,
                paradata_ref=document_paradata_ref,
                license_detail=document_license_detail,
                include_lines=include_lines,
                alto_path=str(layout) if layout else None,
                rows=rows,
            )
        except Exception as exc:
            print(f"  [Warn] document-json hook failed for {doc_name}: {exc}", file=sys.stderr)

    if not save_conllu:
        csv_done = not save_csv or doc_out_csv.exists()
        teitok_done = not save_teitok or (teitok_out_path is not None and teitok_out_path.exists())
        if csv_done and teitok_done:
            try:
                doc_out_conllu.unlink()
            except Exception as e:
                print(f"  [Warn] Could not remove intermediate CoNLL-U: {e}", file=sys.stderr)

    return True


# ── directory-level pipeline (used when running standalone) ──────────────────


def process_pipeline(
    conllu_dir,
    tsv_dir,
    output_dir,
    alto_dir,
    teitok_out,
    save_conllu=True,
    save_csv=True,
    save_teitok=False,
    pages_dir=None,
    model_udpipe=None,
    model_nametag=None,
    summary_csv=None,
    dpi=None,
    alto_dpi=None,
    document_json_dir=None,
    include_lines=False,
    bbox_origin="page",
    flexiconv_dir=None,
    text_dir=None,
):
    conllu_path_obj = Path(conllu_dir)
    if not conllu_path_obj.exists():
        print(f"Error: CoNLL-U dir not found: {conllu_dir}")
        sys.exit(1)

    conllu_files = sorted(list(conllu_path_obj.glob("*.conllu")))
    print(f"Found {len(conllu_files)} documents to process.")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for conllu_file in conllu_files:
        # Same derivation as process_single_document() below — both must agree, or the
        # resume check here looks for outputs under a different name than the one that
        # writes them (issue atrium-project#10, D3).
        doc_name = canonical_doc_id(conllu_file)
        doc_out_dir = Path(output_dir) / doc_name
        doc_out_conllu = doc_out_dir / f"{doc_name}.conllu"
        doc_out_csv = doc_out_dir / f"{doc_name}.csv"
        doc_out_teitok = (Path(teitok_out) / f"{doc_name}.teitok.xml") if teitok_out else None

        need_conllu = save_conllu and not doc_out_conllu.exists()
        need_csv = save_csv and not doc_out_csv.exists()
        need_teitok = save_teitok and doc_out_teitok is not None and not doc_out_teitok.exists()

        if not (need_conllu or need_csv or need_teitok):
            print(f"[Skip] {doc_name}: all requested outputs already exist.")
            continue

        print(f"[Processing] {doc_name}...")
        process_single_document(
            conllu_file=conllu_file,
            ne_dir=Path(tsv_dir) / doc_name,
            output_dir=doc_out_dir,
            save_conllu=save_conllu,
            save_csv=save_csv,
            save_teitok=save_teitok,
            alto_dir=alto_dir,
            teitok_out=teitok_out,
            pages_dir=pages_dir,
            summary_csv=summary_csv,
            model_udpipe=model_udpipe,
            model_nametag=model_nametag,
            dpi=dpi,
            alto_dpi=alto_dpi,
            document_json_dir=document_json_dir,
            include_lines=include_lines,
            bbox_origin=bbox_origin,
            flexiconv_dir=flexiconv_dir,
            text_dir=text_dir,
        )

    print("\nPipeline Complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser()

    # --- Per-document args (used by api_4_stats.sh) ---
    parser.add_argument(
        "--conllu", default=None, help="Single CoNLL-U file to process (per-document mode)."
    )
    parser.add_argument(
        "--ne-dir", default=None, help="Directory of per-page NE TSV files for this document."
    )
    parser.add_argument(
        "--output-dir", default=None, help="Output directory for this document's results."
    )
    parser.add_argument(
        "--summary-csv",
        default=os.getenv("SUMMARY_CSV"),
        help="Path to the global summary CSV to append entity counts to.",
    )

    parser.add_argument(
        "--dpi",
        type=_float_or_none,
        default=os.environ.get("IMAGE_DPI"),
        help="Output image DPI for TEITOK scaling",
    )
    parser.add_argument(
        "--alto-dpi",
        type=_float_or_none,
        default=os.environ.get("ALTO_DPI"),
        help="Source ALTO DPI",
    )
    parser.add_argument(
        "--bbox-origin",
        choices=("page", "printspace"),
        default=os.environ.get("BBOX_ORIGIN") or "page",
        help="TEITOK bbox origin: page (default, the TEITOK norm: ALTO page coordinates) or "
        "printspace (coordinates relative to the ALTO PrintSpace, for cropped page images).",
    )
    # api_4_stats.sh sources config_api.txt without exporting it, so the model names are
    # passed explicitly; the environment is only the fallback for standalone runs.
    parser.add_argument(
        "--model-udpipe",
        default=os.environ.get("MODEL_UDPIPE"),
        help="UDPipe model name, recorded in the TEITOK header.",
    )
    parser.add_argument(
        "--model-nametag",
        default=os.environ.get("MODEL_NAMETAG"),
        help="NameTag model name, recorded in the TEITOK header.",
    )

    # --- Document Hook specific args ---
    parser.add_argument(
        "--para-state",
        default=None,
        help="The stage's paradata state file (atrium_paradata.py start): its run stamps the "
        "document record (atrium-project#71), and limits that shaped the summary are recorded "
        "in it (atrium-project#53).",
    )
    parser.add_argument(
        "--document-json-dir",
        type=str,
        default=None,
        help="Directory containing baseline document JSONs for accretion",
    )
    parser.add_argument(
        "--include-lines", action="store_true", help="DANGER: Opt-in to merge lines[] block."
    )

    # --- Directory-mode args (used when running standalone) ---
    parser.add_argument("--conllu-dir", default=os.getenv("CONLLU_INPUT_DIR"))
    parser.add_argument("--tsv-dir", default=os.getenv("TSV_INPUT_DIR"))
    parser.add_argument("--out-dir", default=os.getenv("SUMMARY_OUTPUT_DIR"))
    parser.add_argument("--tt-dir", default=os.getenv("TEITOK_OUTPUT_DIR"))
    parser.add_argument(
        "--alto-dir",
        default=os.getenv("INPUT_ALTO_DIR") or os.getenv("ALTO_DIR"),
        help="Directory of <doc>.alto.xml page layouts (INPUT_ALTO_DIR).",
    )
    parser.add_argument(
        "--flexiconv-dir",
        default=(
            os.getenv("TEITOK_FLEXICONV_DIR")
            if bool_from_str(os.getenv("FLEXICONV_ANNOTATE"), default=False)
            else None
        ),
        help="FLEXICONV_ANNOTATE: flexiconv TEITOK output (TEITOK_FLEXICONV_DIR). A document "
        "without ALTO takes its page layout from its converted file there.",
    )
    parser.add_argument(
        "--text-dir",
        default=os.getenv("TEMP_TXT_DIR"),
        help="Stage 1's text directory (TEMP_TXT_DIR): where a document's <doc>.rows.tsv is "
        "looked for when there is none next to its CoNLL-U.",
    )
    parser.add_argument(
        "--pages-dir",
        default=os.getenv("INPUT_PAGES_DIR"),
        help="Directory containing per-page images.",
    )

    # --- Format flags ---
    parser.add_argument(
        "--save-conllu-ne",
        default=os.getenv("SAVE_CONLLU_NE", "1"),
        help="1/0 whether to keep the merged CoNLL-U per document.",
    )
    parser.add_argument(
        "--save-csv",
        default=os.getenv("SAVE_CSV", "1"),
        help="1/0 whether to write the summary CSV per document.",
    )
    parser.add_argument(
        "--save-teitok",
        default=os.getenv("SAVE_TEITOK", "0"),
        help="1/0 whether to write TEITOK-XML per document.",
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    save_conllu = bool_from_str(args.save_conllu_ne, default=True)
    save_csv = bool_from_str(args.save_csv, default=True)
    save_teitok = bool_from_str(args.save_teitok, default=False)

    # The record is stamped with the stage's own run: its `atrium_paradata.py start` state,
    # --para-state (atrium-project#71). This used to take the FIRST .state_*.json of a
    # --state-dir (now gone), which in a shared paradata directory may be another stage's,
    # and read keys no state file has (`_run_id`, `paradata_path`, `license_detail`): every
    # record said run "unknown-nlp-enrich-run", with no paradata reference and no licence.
    document_run_id = "unknown-nlp-enrich-run"
    document_run_uuid = None
    document_paradata_ref = ""
    document_license_detail = {}

    if args.document_json_dir and args.para_state and os.path.exists(args.para_state):
        stage_run = ParadataLogger.from_state_file(args.para_state)
        document_run_id = stage_run.run_id
        document_run_uuid = stage_run.run_uuid
        document_paradata_ref = stage_run.paradata_ref
        document_license_detail = stage_run.get_license_block()

    # ── per-document mode (invoked by api_4_stats.sh with --conllu) ──
    if args.conllu:
        if not args.ne_dir or not args.output_dir:
            print(
                "[Error] --ne-dir and --output-dir are required in per-document mode.",
                file=sys.stderr,
            )
            sys.exit(1)
        ok = process_single_document(
            conllu_file=args.conllu,
            ne_dir=args.ne_dir,
            output_dir=args.output_dir,
            save_conllu=save_conllu,
            save_csv=save_csv,
            save_teitok=save_teitok,
            alto_dir=args.alto_dir,
            teitok_out=args.tt_dir,
            pages_dir=args.pages_dir,
            summary_csv=args.summary_csv,
            model_udpipe=args.model_udpipe or None,
            model_nametag=args.model_nametag or None,
            # --dpi/--alto-dpi were parsed but never passed on in this mode, so tier-2
            # (IMAGE_DPI) scaling silently never applied to api_4_stats.sh runs.
            dpi=args.dpi,
            alto_dpi=args.alto_dpi,
            document_json_dir=args.document_json_dir,
            document_run_id=document_run_id,
            document_paradata_ref=document_paradata_ref,
            document_run_uuid=document_run_uuid,
            document_license_detail=document_license_detail,
            include_lines=args.include_lines,
            bbox_origin=args.bbox_origin,
            flexiconv_dir=args.flexiconv_dir or None,
            text_dir=args.text_dir or None,
            para_state=args.para_state,
        )
        sys.exit(0 if ok else 1)

    # ── directory mode (standalone / legacy) ──
    if not all([args.conllu_dir, args.tsv_dir, args.out_dir]):
        print(
            "[Error] Provide either --conllu/--ne-dir/--output-dir (per-document) or --conllu-dir/--tsv-dir/--out-dir (directory mode).",
            file=sys.stderr,
        )
        sys.exit(1)

    if save_teitok:
        if args.alto_dir and not Path(args.alto_dir).exists():
            print(
                f"[Error] A valid --alto-dir is required when save-teitok=true ('{args.alto_dir}' not found).",
                file=sys.stderr,
            )
            sys.exit(1)
        if not args.alto_dir and not args.flexiconv_dir:
            print(
                "[Warn] neither --alto-dir nor --flexiconv-dir set; TEITOK output will have "
                "no bboxes.",
                file=sys.stderr,
            )

        if args.tt_dir:
            Path(args.tt_dir).mkdir(parents=True, exist_ok=True)

    process_pipeline(
        conllu_dir=args.conllu_dir,
        tsv_dir=args.tsv_dir,
        output_dir=args.out_dir,
        alto_dir=args.alto_dir,
        teitok_out=args.tt_dir,
        save_conllu=save_conllu,
        save_csv=save_csv,
        save_teitok=save_teitok,
        pages_dir=args.pages_dir,
        model_udpipe=args.model_udpipe or None,
        model_nametag=args.model_nametag or None,
        summary_csv=args.summary_csv,
        dpi=args.dpi,
        alto_dpi=args.alto_dpi,
        document_json_dir=args.document_json_dir,
        include_lines=args.include_lines,
        bbox_origin=args.bbox_origin,
        flexiconv_dir=args.flexiconv_dir or None,
        text_dir=args.text_dir or None,
    )


if __name__ == "__main__":
    main()
