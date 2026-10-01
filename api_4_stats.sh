#!/usr/bin/env bash
# api_4_stats.sh – statistics + TEITOK generation + paradata
set -euo pipefail

DOC_JSON_DIR=""
INCLUDE_LINES=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --document-json-dir) DOC_JSON_DIR="$2"; shift ;;
        --include-lines) INCLUDE_LINES="--include-lines" ;;
    esac
    shift
done

# shellcheck disable=SC1090  # config path is dynamic (ATRIUM_CONFIG); not followed at lint time
source "${ATRIUM_CONFIG:-config_api.txt}"

OUTPUT_TYPES=""
[ "${SAVE_CSV:-true}"        = "true" ] && OUTPUT_TYPES="$OUTPUT_TYPES csv"
[ "${SAVE_CONLLU_NE:-true}"  = "true" ] && OUTPUT_TYPES="$OUTPUT_TYPES conllu"
[ "${SAVE_TEITOK:-true}"     = "true" ] && OUTPUT_TYPES="$OUTPUT_TYPES xml"
OUTPUT_TYPES="${OUTPUT_TYPES# }"

# shellcheck disable=SC2086  # OUTPUT_TYPES is intentionally word-split into multiple --output-types args
PARA_STATE=$(python3 atrium_paradata.py start \
    --program nlp-enrich \
    --paradata-dir "${PARADATA_DIR}" \
    --output-types $OUTPUT_TYPES \
    --config \
        "script=api_4_stats" \
        "conllu_input_dir=${CONLLU_INPUT_DIR}" \
        "tsv_input_dir=${TSV_INPUT_DIR}" \
        "output_dir=${SUMMARY_OUTPUT_DIR}" \
        "save_conllu_ne=${SAVE_CONLLU_NE:-true}" \
        "save_csv=${SAVE_CSV:-true}" \
        "save_teitok=${SAVE_TEITOK:-true}" \
        "alto_dir=${INPUT_ALTO_DIR:-}" \
        "pages_dir=${INPUT_PAGES_DIR:-}" \
        "dpi=${IMAGE_DPI:-}" \
        "alto_dpi=${ALTO_DPI:-}" \
        "bbox_origin=${BBOX_ORIGIN:-page}" \
        "regenerate_teitok=${REGENERATE_TEITOK:-false}" \
        "flexiconv_annotate=${FLEXICONV_ANNOTATE:-false}")

# FLEXICONV_ANNOTATE=true: a document without ALTO takes its page layout (bboxes, page
# images, text blocks) from its flexiconv TEITOK file (api_flexiconv.sh).
FLEXICONV_LAYOUT_DIR=""
if [ "${FLEXICONV_ANNOTATE:-false}" = "true" ]; then
    FLEXICONV_LAYOUT_DIR="${TEITOK_FLEXICONV_DIR:-${TEITOK_OUTPUT_DIR}/flexiconv}"
fi

TOTAL=$(find "${CONLLU_INPUT_DIR}" -name '*.conllu' -type f | wc -l)
rm -f "${OUTPUT_DIR}/summary_ne_counts.csv"

DOC_JSON_FLAGS=""
if [ -n "$DOC_JSON_DIR" ]; then
    DOC_JSON_FLAGS="--document-json-dir $DOC_JSON_DIR $INCLUDE_LINES"
fi

while IFS= read -r -d '' conllu; do
    rel_path="${conllu#"${OUTPUT_DIR}"/UDP/}"
    doc="${rel_path%.conllu}"
    doc_name=$(basename "$doc")

    ne_dir="${TSV_INPUT_DIR}/${doc}"
    doc_out_dir="${SUMMARY_OUTPUT_DIR}/${doc}"
    tt_out_dir="${TEITOK_OUTPUT_DIR}/$(dirname "$doc")"

    mkdir -p "$doc_out_dir"
    mkdir -p "$tt_out_dir"

    # REGENERATE_TEITOK=true: rewrite TEITOK that a previous run left behind (e.g. in an
    # older writer format -- see <application ident="atrium-nlp-enrich" version=...>)
    # instead of letting the resume check below keep it.
    if [ "${REGENERATE_TEITOK:-false}" = "true" ] && [ "${SAVE_TEITOK:-true}" = "true" ]; then
        rm -f "${tt_out_dir}/${doc_name}.teitok.xml"
    fi

    csv_done=true;    conllu_done=true;    teitok_done=true
    [ "${SAVE_CSV:-true}"       = "true" ] && [ ! -f "${doc_out_dir}/${doc_name}.csv"         ] && csv_done=false
    [ "${SAVE_CONLLU_NE:-true}" = "true" ] && [ ! -f "${doc_out_dir}/${doc_name}.conllu"      ] && conllu_done=false
    [ "${SAVE_TEITOK:-true}"    = "true" ] && [ ! -f "${tt_out_dir}/${doc_name}.teitok.xml" ] && teitok_done=false

    if $csv_done && $conllu_done && $teitok_done; then
        python3 atrium_paradata.py skip \
            --state "$PARA_STATE" \
            --file  "$doc" \
            --reason "all requested outputs already exist (resumed run)"
        continue
    fi

    # shellcheck disable=SC2086 # Allow word-splitting for DOC_JSON_FLAGS
    if python3 api_util/summarize_nt_udp.py \
            --conllu     "$conllu" \
            --ne-dir     "$ne_dir" \
            --output-dir "$doc_out_dir" \
            --save-conllu-ne "${SAVE_CONLLU_NE:-true}" \
            --save-csv       "${SAVE_CSV:-true}" \
            --save-teitok    "${SAVE_TEITOK:-true}" \
            --tt-dir         "$tt_out_dir" \
            --alto-dir       "${INPUT_ALTO_DIR:-}" \
            --flexiconv-dir  "$FLEXICONV_LAYOUT_DIR" \
            --text-dir       "${TEMP_TXT_DIR:-}" \
            --pages-dir      "${INPUT_PAGES_DIR:-}" \
            --dpi            "${IMAGE_DPI:-}" \
            --alto-dpi       "${ALTO_DPI:-}" \
            --bbox-origin    "${BBOX_ORIGIN:-page}" \
            --model-udpipe   "${MODEL_UDPIPE:-}" \
            --model-nametag  "${MODEL_NAMETAG:-}" \
            --summary-csv    "${OUTPUT_DIR}/summary_ne_counts.csv" \
            --para-state     "$PARA_STATE" \
            $DOC_JSON_FLAGS; then

        if $csv_done && $conllu_done && $teitok_done; then
            python3 atrium_paradata.py skip \
                --state "$PARA_STATE" \
                --file  "$doc" \
                --reason "all requested outputs already exist (resumed run)"
        else
            [ "${SAVE_CSV:-true}"       = "true" ] && \
                python3 atrium_paradata.py success --state "$PARA_STATE" --type csv
            [ "${SAVE_CONLLU_NE:-true}" = "true" ] && \
                python3 atrium_paradata.py success --state "$PARA_STATE" --type conllu
            [ "${SAVE_TEITOK:-true}"    = "true" ] && \
                python3 atrium_paradata.py success --state "$PARA_STATE" --type xml
        fi
    else
        # P1 FIX: Log the failure and exit immediately to halt the pipeline
        python3 atrium_paradata.py skip \
            --state "$PARA_STATE" \
            --file  "$doc" \
            --reason "summarize_nt_udp failed"

        echo "[CRITICAL ERROR] summarize_nt_udp aggregation failed for ${doc}. Halting pipeline." >&2
        exit 1
    fi
done < <(find "${CONLLU_INPUT_DIR}" -name '*.conllu' -type f -print0)

# Output-contract gate (issues #28, #38): TEITOK XML is a formal output contract —
# malformed documents must never reach packaging or the LINDAT release.
# Runs after generation, before atrium_paradata.py finish, and over the
# TEITOK_OUTPUT_DIR as a whole (not just this run's docs) so a resumed run
# still re-checks everything currently on disk. The default profile, "contract",
# is the XSD for every file plus unique ids, resolvable references and the page
# rules (pb-K increasing, lb-P.L on page P) for files this writer stamps teitok-2;
# older files are held to the XSD only.
#
# Exit 5 (not 1): the runner and the service tell "the output failed its contract"
# apart from "the run produced nothing" (exit 1).
#
# --allow-empty: TEITOK_OUTPUT_DIR is only created inside the per-document
# loop above, so a run with zero input documents legitimately has nothing to
# validate. That outcome belongs to the runner's FAIL_ON_EMPTY, not to this
# gate — without the flag an empty run died here on "target directory does
# not exist", masking the real reason.
#
# --exclude: flexiconv's output (api_flexiconv.sh, TEITOK_FLEXICONV_DIR, by default a
# subdirectory of TEITOK_OUTPUT_DIR) is another TEITOK profile. api_flexiconv.sh gates it
# with --profile core; this writer's XSD would reject it.
#
# The failure path mirrors the summarize_nt_udp one above: record the reason
# in paradata and mirror it into $LOG_FILE before halting, so a red run is
# diagnosable from the log and the run record is not left dangling. We use an
# inline tee rather than api_util/api_common.sh's log(): sourcing that file
# would also re-source the config, validate INPUT_TABLES_DIR and mkdir
# OUTPUT_DIR, side effects this script deliberately avoids.
if [ "${SAVE_TEITOK:-true}" = "true" ]; then
    echo "Validating TEITOK XML output contract..."
    if ! python3 api_util/validate_teitok_xml.py "${TEITOK_OUTPUT_DIR}" --allow-empty \
            --exclude "${TEITOK_FLEXICONV_DIR:-${TEITOK_OUTPUT_DIR}/flexiconv}"; then
        python3 atrium_paradata.py skip \
            --state "$PARA_STATE" \
            --file  "${TEITOK_OUTPUT_DIR}" \
            --reason "TEITOK output contract failed"

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [CRITICAL ERROR] TEITOK output contract failed (see the [FAIL] lines above). Halting pipeline before packaging." \
            | tee -a "${LOG_FILE:-/dev/null}" >&2
        exit 5
    fi
fi

python3 atrium_paradata.py finish --state "$PARA_STATE" --input-total "$TOTAL"