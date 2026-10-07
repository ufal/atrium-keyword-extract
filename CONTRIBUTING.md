# 🤝 Contributing to the Keyword Extraction of the ATRIUM project

Thank you for your interest in contributing!
This document describes the development workflow, conventions, and rules for contributors.
The repository was assembled on 1 October 2026 from the keyword extraction of `atrium-nlp-enrich` and of `atrium-llm-enrich` (atrium-keyword-extract#1); their release histories stay in those repositories.

## 📦 Release History

| Version         | Highlights                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Status      |
|:----------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------|
| **v1.1.0-beta** | The controlled kind joins the service (atrium-keyword-extract#1, #2): `kind=controlled\|both` runs an LLM (OpenRouter or Ollama, `LLM_BACKEND`) per line over the AMČR/TEATER vocabulary and writes the record's `enrichment` block and `entities[].pid`. Adds the batch clients `openrouter_client.py` and `ollama_client.py`, the `controlled-live.yml` lane, and `llm-enrich`'s engine merged in.                                                                                                                                                                                                                                                                                  | Pre-release |
| **v1.0.0-beta** | The first release of `atrium-keyword-extract` (atrium-keyword-extract#1; atrium-project#72). One service, `POST /extract_keywords` and `/extract_keywords_text`: the **statistical** kind (KeyBERT by default, YAKE, KER) per document and per page, every keyword with its method, score and rank, and the run's `CreateAction`; the controlled kind is reported `skipped`. The batch CLI `keywords.py` and the research LLM/vocabulary code (`llm` target) moved here from nlp-enrich and llm-enrich; nlp-enrich keeps only the LINDAT calls. Service id `atrium-keyword-extract` (the spec declares `x-atrium-service-previous: atrium-nlp-enrich`), program id `keyword-extract`. | Pre-release |

---

## 🌿 Branches & Environments

| Branch   | Environment          | Rule                                                                            |
|----------|----------------------|---------------------------------------------------------------------------------|
| `test`   | Staging              | Base for all development. Always branch from `test`.                            |
| `master` | Stable / Integration | Merged exclusively by a human reviewer. Do not open PRs directly into `master`. |

```text
test    ←  feature-<name>
test    ←  bugfix-<name>
master  ←  (humans only, after test stabilises)

```

### 🏷️ Branch Naming

| Type             | Pattern          | Example              |
|------------------|------------------|----------------------|
| New feature      | `feature-<name>` | `feature-methods`    |
| Bug fix          | `bugfix-<name>`  | `bugfix-chunking`    |
| Hotfix on master | `hotfix-<name>`  | `hotfix-api-timeout` |

---

## 🔁 Contributor Workflow

1. **Create an issue** (or find an existing one) describing the problem or feature.
2. **Branch from `test`:**
```bash
git checkout test
git pull origin test
git checkout -b feature-<name>
```
3. **Implement your changes** observing the project's code conventions.
4. **Run the minimum tests** (see the Testing section).
5. **Open a Pull Request** targeting the `test` branch.

---

## 📋 Pull Request Format

Every PR must include:

* **Issue link:** `Closes #<number>` or `Refs #<number>`
* **Motivation:** why the change is needed
* **Description of change:** what was changed and how
* **Testing:** what was run, what passed, what could not be executed

Use a **Draft PR** if the work is not ready for review.

**Do not open PRs into `master` — merging into `master` is exclusively the
maintainers' responsibility.

> **Note on issue tracking:** Issues reference the commits and PRs that resolved
> them — not the other way around. Commit messages describe *what changed*; the issue
> is the place to record *why* and link the resulting commits together.

---

## ✏️ Commit Messages

Format:

```text
[type] concise description of what changed
```

Allowed types:

| Type       | When to use                           |
|------------|---------------------------------------|
| `add`      | Added content (general)               |
| `edit`     | Edited existing content (general)     |
| `remove`   | Removed existing content (general)    |
| `fix`      | Bug fix                               |
| `refactor` | Refactoring without behaviour change  |
| `test`     | Adding or updating tests              |
| `docs`     | Documentation only                    |
| `chore`    | Build, dependencies, CI configuration |
| `style`    | Formatting, no logic change           |
| `perf`     | Performance optimisation              |


---

## 🧪 Code Conventions & Testing

### Code Conventions

* **Comments:** informative but short, may be LLM-generated, added when function name does
not explain its functionality in detail
* **Argument types:** set default type (e.g., `int`, `list`) for function arguments
* **Console flags:** when a new one added, provide help message for it
* **Config files:** when set of variables changes it should be reflected in repository documentation
* **Generated code:** always should be manually launched and checked for mistakes before pushing

### Minimum checks before every commit

Always run basic validation locally before pushing:

```bash
# 1. Python compilation check
python -m compileall -q .

# 2. Lint & format (Ruff — matches CI)
ruff check .
ruff format .
```

> [!NOTE]
>  If specific scripts or extraction modules are updated, please run a smoke-test
> against the `data_samples/` directory to verify extraction integrity.

---

### Running the test suite

The repository ships a `pytest` harness that requires **no ML models or GPU**. The whole
suite runs offline in well under a minute.

```bash
pip install -r requirements-test.txt
```

That file is more than pytest: it also pins `jsonschema` (the `atrium_document` schema
gate), `lxml` (the OAI-PMH parser), and the FastAPI
test stack — each with a comment saying which gate would silently skip without it.

```bash
pytest -q                                    # the whole suite — use before every commit
pytest --cov=. --cov-report=term-missing     # with coverage
```

> There is **no `slow` marker in this repository** — `grep -rc pytest.mark.slow tests/`
> returns zero. `pytest -m "not slow"` and a bare `pytest` are the same run, which is
> what made the old nightly report success having collected nothing (see the v0.19.0
> row above). Heavy deps are separated by *workflow*, not by marker: `torch` lives in
> `gpu-inference.yml`, `transformers` in `scheduled-smoke.yml`.

`tests/test_paradata.py` (`ParadataLogger`, `_sanitise`) is shared across all repos.

<details>
<summary>Test layout, per-repo targets, and fixture conventions</summary>

```text
tests/
├── __init__.py              # empty
├── conftest.py              # shared fixtures (tmp_path wrappers, sample data loaders)
├── fixtures/                # small static test-data files committed to the repo
└── test_<module>.py         # repo-specific unit tests
```

**Per-repo targets:**

| Repository               | Test file              | Primary targets                                                                                                           |
|--------------------------|------------------------|---------------------------------------------------------------------------------------------------------------------------|
| `atrium-keyword-extract` | `test_keywords.py`     | `_extract_surface_text`, `_extract_lemmas`, `_extract_legacy`, `extract_keywords`, `extract_from_texts`, `_sort_csv_file` |
| `atrium-keyword-extract` | `test_api_service.py`  | the service in-process: methods, kinds, pages, limits, `busy`, the `CreateAction`                                         |
| `atrium-keyword-extract` | `test_api_contract.py` | every response held to the schema the published `openapi.json` declares                                                   |
| `atrium-ocr-postprocess` | `test_text_util.py`    | density/ratio helpers, detectors, `categorize_line`, `compute_quality_score`                                              |
| `atrium-translator`      | `test_utils.py`        | `_resolve_namespaces`, `validate_xml_with_xsd`, `process_alto_xml`, `process_amcr_xml`                                    |

**Heavy tests** — a test that loads a model checkpoint, calls an external API, or needs a
GPU does not belong in the default suite. Put it behind the workflow that has the
resource (`gpu-inference.yml`, `scheduled-smoke.yml`, `controlled-live.yml`) rather than behind a marker, and
say in the PR description what it requires. The external-API case is `tests/test_controlled_live.py`:
it skips unless `ATRIUM_LIVE_BACKEND=1`, and `controlled-live.yml` runs it against OpenRouter with the
repository's `OPENROUTER_KEY` secret.

**Fixtures** — small, self-contained files committed under `tests/fixtures/`. Add a
minimal fixture in the same commit as any test that needs new sample data.

**The one deliberate exception: drift gates read `data_samples/` on purpose.** A test
that asserts a *committed artefact* still matches what its config would produce has to
open the committed artefact — a fixture copy would only prove the fixture is
self-consistent. Eleven modules do this, and it is the point of each:
`test_vocab_build.py`, `test_vocab_manager.py`, `test_vocab_review.py`,
`test_corpus_review.py`, `test_prompt_template.py` and friends. Everywhere else, prefer a fixture.

</details>

---

## 📁 Repository Documentation Management

Each documentation file has one target audience and one responsibility. Rules are not repeated — cross-references are used instead.

| File                                     | Audience                | Responsibility                                                                          |
|------------------------------------------|-------------------------|-----------------------------------------------------------------------------------------|
| `README.md`                              | GitHub visitors         | Project overview, the two kinds of keywords, setup, the batch CLI, licences             |
| `CONTRIBUTING.md`                        | Developers              | Code conventions, branches, PRs, testing, generated artefacts                           |
| `service/README.md`                      | API consumers           | REST endpoints, environment variables, limits, errors, the OpenAPI contract             |
| `data_samples/vocab/RUNBOOK.md`          | **Vocabulary curators** | Every vocabulary script and flag, the eight review sheets, where a decision is recorded |
| `prompts/RUNBOOK.md`                     | **Prompt reviewers**    | The prompt blocks and their flags, the guardrail's two halves, the output contract      |
| `data_samples/vocab/6.*.md`              | Domain reviewers        | One open question each, framed with numbers from the sheets beside them                 |
| `agent_dev_logs/DEVLOG.md`               | Maintainers             | Per-issue history: digests, plans, decisions                                            |

* **Do not duplicate rules:** if a rule is defined in `CONTRIBUTING.md`, other files
reference it rather than copying it.
* **When changing a rule:** update the canonical source and verify that referencing files
still point correctly.

---

## ⚙️ Generated Artefacts

Some files are modified automatically by scripts or hooks:

| Script                   | What it generates                                                                                                                 |
|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| `keywords.py`            | `keywords_summary*.csv` and `KW_PER_DOC*/` — the CLI's master table and per-document CSVs (`data_samples/`)                       |
| `atrium_openapi.py`      | `service/openapi.json` — regenerate after every API or setting change (`export --app service.api:app`)                            |
| **`vocab_build.py`**     | the 14 vocabulary artefacts in `data_samples/vocab/` — harvests, nested facets, meta sidecars, placement audits, `vocabulary.csv` |
| **`vocab_review.py`**    | the 8 reviewer sheets in `data_samples/vocab/` (`--all`)                                                                          |
| **`corpus_review.py`**   | the 3 corpus-evidence sheets + `corpus_review.meta.json` (`--all`; needs the document corpus)                                     |
| **`prompt_template.py`** | the 4 committed prompt renders in `prompts/` (`--write`)                                                                          |

Rules:

1. Do not manually edit auto-generated output files.
2. After changing a keyword method or the service's response, re-run the service tests and regenerate
`service/openapi.json`; `tests/test_openapi_contract.py` fails while it is stale.
3. `api_util/teitok_read.py` and `api_util/bbox_scale.py` are **nlp-enrich's** files, pinned by
`tests/test_vendored_teitok_parity.py`: change them in `atrium-nlp-enrich` and re-vendor.
4. **Config and generated artefact move in the same commit.** Editing
`data_samples/taxonomy_*.json`, `llm_config.txt` or `prompts/system_prompt.txt` without
regenerating is the failure this repo has already shipped twice (`a5e3c8a`, `d4c46b2`):
the config said one thing and the artefact the model actually reads said another, with
nothing failing. Three gates now catch it, and all three run on every PR
(`.github/workflows/vocab-drift.yml`):

   ```bash
   python3 vocab_build.py --from-flat && python3 vocab_build.py --from-flat --check
   python3 vocab_review.py --all
   python3 prompt_template.py --write && python3 prompt_template.py --check
   ```

   Full procedure and the decision tables:
   [`data_samples/vocab/RUNBOOK.md`](data_samples/vocab/RUNBOOK.md) and
   [`prompts/RUNBOOK.md`](prompts/RUNBOOK.md).

---

## 📞 Contacts & Acknowledgements

For technical questions contact **lutsai.k@gmail.com**

**Issues:** https://github.com/ufal/atrium-keyword-extract/issues

* **Developed by:** UFAL [^7]
* **Funded by:** ATRIUM [^4]
* **Models:**
  * KeyBERT [^5] with a sentence-transformers model

**©️ 2026 UFAL & ATRIUM**


[^4]: https://atrium-research.eu/
[^5]: https://github.com/MaartenGr/KeyBERT
[^7]: https://ufal.mff.cuni.cz/home-page
