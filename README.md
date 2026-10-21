<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" title="Python Version"></a>
  <a href="https://opensource.org/license/mit/"><img src="https://img.shields.io/github/license/ufal/atrium-keyword-extract" title="MIT License"></a>
  <a href="https://atrium-research.eu/"><img src="https://img.shields.io/badge/funded%20by-ATRIUM-8A2BE2.svg" title="ATRIUM Project"></a>
</p>

---

# ATRIUM keyword-extract - Agent Skill 🤖🗝️

### Goal: let coding agents extract statistical and vocabulary-guided keywords via a server-client skill

This branch (`agent-skill`) packages the **ATRIUM keyword-extract API service** together with a **Skill for
coding agents** (Claude Code, Codex, Gemini/Antigravity). The design follows a strict server-client split:

- **Server** 🖥️ - the FastAPI service in [`service/`](service/) runs KeyBERT, YAKE and the legacy method, and
  the vocabulary-guided language-model calls of the controlled kind (Docker Compose `api` profile, CPU or GPU, or a
  local venv).
- **Client** 🪶 - [`scripts/atrium_keywords.py`](scripts/atrium_keywords.py), a **zero-dependency** stdlib-only
  script that agents call directly.
- **Skill contract** 📜 - [`SKILL.md`](SKILL.md) tells the agent when and how to use it: the two kinds,
  method choice, what each kind needs, refusals and what to do about each.

For the batch keyword CLI, the vocabulary build, the research GPU path and the full project documentation, see the
[`test`](https://github.com/ufal/atrium-keyword-extract/tree/test) branch; this branch carries only what the
skill needs.

### Table of contents 📑

  * [Quick start 🚀](#quick-start-)
  * [Skill installation 🔧](#skill-installation-)
  * [Server setup 🖥️](#server-setup-️)
  * [Client usage 🪶](#client-usage-)
  * [Maintenance notes 🔍](#maintenance-notes-)
  * [Contacts 📧](#contacts-)

## Quick start 🚀

```bash
git clone -b agent-skill https://github.com/ufal/atrium-keyword-extract.git
cd atrium-keyword-extract
bash scripts/server.sh                                           # start (or reuse) the server
python3 scripts/atrium_keywords.py small_data_samples/report.document.json --kind statistical
```

Expected: the keywords of the document and of its two pages, each with its method, score and rank, such as
"Horní Mezí" and "okres Beroun" on page 1.

## Skill installation 🔧

### Claude Code

```bash
git clone -b agent-skill https://github.com/ufal/atrium-keyword-extract.git \
    ~/.claude/skills/atrium-keyword-extract
```

### Codex

```bash
git clone -b agent-skill https://github.com/ufal/atrium-keyword-extract.git \
    ~/.codex/skills/atrium-keyword-extract
```

### Google Antigravity

Clone anywhere and point `AGENTS.md` at the skill:

```
Use the ATRIUM keyword-extract skill from `atrium-keyword-extract/SKILL.md`.
Start the server with `bash atrium-keyword-extract/scripts/server.sh`, then run
`python3 atrium-keyword-extract/scripts/atrium_keywords.py [FILES...]`.
```

Update with `git pull` in the installed clone.

## Server setup 🖥️

```bash
bash scripts/server.sh          # Docker Compose api profile, or the local fallback
bash scripts/server.sh --gpu    # Docker with the GPU overlay (KeyBERT on the GPU)
bash scripts/server.sh --local  # a local server in venv-kw (no Docker)
```

The script exits at once if `/ready` already answers, and otherwise waits for it. With Docker it runs the
released image of this branch's version (from `para_config.txt`), and builds the image from the checkout when it
cannot pull it. Both carry the AMČR/TEATER vocabulary (`data_samples/vocab/`). The port defaults
to `8000` (`ATRIUM_KW_PORT`). For the controlled kind, set `LLM_BACKEND` and its key or server in `.env` (see
`.env.example`). Every setting, limit and error is in [`service/README.md`](service/README.md).

## Client usage 🪶

```bash
python3 scripts/atrium_keywords.py record.document.json               # both kinds, per document and page
python3 scripts/atrium_keywords.py notes.txt --method yake             # a plain text, YAKE
python3 scripts/atrium_keywords.py record.document.json --out-dir out/  # + the record with its keywords
python3 scripts/atrium_keywords.py record.document.json --format json  # the whole answer
python3 scripts/atrium_keywords.py --info                              # methods, kinds, limits
```

Point the client at another deployment with `--base-url` or `ATRIUM_KW_URL`. The kinds and methods are
explained in [`SKILL.md`](SKILL.md#keyword-kinds-and-methods-).

## Maintenance notes 🔍

Review checklist for every change or sync-merge into this branch:

- [ ] no document names a script that differs from the committed file;
- [ ] no provenance claim the service does not make on this branch;
- [ ] no reference to a file or directory absent from this branch;
- [ ] the documented response fields match what `service/api.py` returns;
- [ ] the client re-run on `small_data_samples/` against a locally started server.

## Contacts 📧

**For support write to:** lutsai.k@gmail.com, responsible for the
[GitHub repository](https://github.com/ufal/atrium-keyword-extract).

### Acknowledgements 🙏

- **Developed by** ÚFAL, Charles University 👥
- **Funded by** [ATRIUM](https://atrium-research.eu/) 💰
- **Vocabularies**: AMČR and TEATER, of the Archaeological Map of the Czech Republic
