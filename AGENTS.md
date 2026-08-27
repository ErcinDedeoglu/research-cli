<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Last updated: 2026-08-28 | Last verified: 2026-08-28 -->

# AGENTS.md

**This repo** is an agent-facing **research CLI**. It calls **BGPT, Brave Search, Exa, and Firecrawl over HTTP REST** (not MCP). Agents use the CLI via the skill; coding agents change code here.

**Playbook for running research:** [`skills/research-cli/SKILL.md`](skills/research-cli/SKILL.md) — commands, env keys, when-to-use. Do not copy that into this file.

**Precedence:** nearest `AGENTS.md` wins. Explicit user prompts override files.

## Commands (verified)

| Task | Command | ~Time |
|------|---------|-------|
| Install | `pip install -e .` | ~5s |
| Help | `python -m research_cli --help` | <1s |
| Tests | `PYTHONPATH=src python -m unittest discover -s tests -v` | ~2s |
| Skill alignment | `PYTHONPATH=src python -m unittest tests.test_skill -v` | <1s |
| Zipapp | `bash scripts/build-zipapp.sh dist` | ~1s |
| Self-update (source/pip) | `python -m research_cli --self-update` | <1s |

After install, `research-cli` is the same entry as `python -m research_cli`. Load keys from `.env` (gitignored); copy `.env.example`.

## File Map

```
src/research_cli/cli.py              → argparse + dispatch
src/research_cli/update.py           → GitHub Releases self-update (frozen/zipapp)
src/research_cli/http.py             → HttpRequest/Response, urllib transport
src/research_cli/keys.py             → env keys / MissingKeyError
src/research_cli/providers/bgpt.py   → POST /api/mcp-search
src/research_cli/providers/brave.py  → GET web/search, GET llm/context
src/research_cli/providers/exa.py    → POST /search, POST /contents
src/research_cli/providers/firecrawl.py → scrape, search, map
src/research_cli/providers/firecrawl_papers.py → papers search/inspect/read/related
skills/research-cli/SKILL.md         → agent playbook (not under .grok/)
tests/test_skill.py                  → skill ↔ CLI parser/keys alignment
tests/test_providers.py              → injectable HTTP: method/path/auth/parse
tests/test_cli.py                    → --help, missing keys, fixture-server CLI
tests/test_update.py                 → version compare, assets, replace, background spawn, --self-update
tests/fixtures.py                    → fixture JSON + local HTTP server
.env.example                         → placeholder keys
.github/workflows/ci.yml             → unittest on Python 3.11/3.12
.github/workflows/release.yml        → test + pip-cached freeze + GitHub Release on every main commit
requirements-freeze.txt              → pinned PyInstaller for the freeze job
scripts/build-zipapp.sh              → stdlib zipapp (`research-cli.pyz`)
```

## Golden Samples

| For | Reference | Key patterns |
|-----|-----------|--------------|
| New HTTP operation | `src/research_cli/providers/brave.py` | `build_*_request` + `parse_*` + `execute_json` |
| CLI wiring | `src/research_cli/cli.py` | shared `--base-url`/`--timeout`, leaf subparser, `_dispatch` |
| Skill stay-in-sync | `tests/test_skill.py` | examples must `parse_args`; every leaf command has an example |
| Fixture HTTP | `tests/fixtures.py` | path-routed JSON, not live vendors |

## Heuristics

| When | Do |
|------|-----|
| Agent needs papers/web/scrape | Point at `skills/research-cli/SKILL.md` and the CLI — do not call vendor MCP servers |
| Add/change a CLI command or flag | Update provider + `cli.py` + skill examples + `tests/test_skill.py` in the same change |
| Add a provider HTTP path | Injectable `transport`; assert method, host/path, auth header, parsed fields |
| Skill vs `--help` disagree | Code and skill both wrong until `test_skill` is green |
| Need live keys | `.env` locally; never commit it |
| Adding a Python dependency | Ask first — stdlib HTTP only unless asked |
| Change freeze/zipapp artifact names | Keep `asset_name()` in `update.py` in lockstep with `.github/workflows/release.yml` |

## Boundaries

### Always
- Keep `skills/research-cli/SKILL.md` aligned with `build_parser()` and `keys.py`
- Run `PYTHONPATH=src python -m unittest discover -s tests -v` after CLI/skill changes
- JSON on stdout, errors on stderr; missing Brave/Exa/Firecrawl keys exit 2 and name the provider

### Ask first
- New vendor SDKs or wrapping remaining MCP tools (crawl, interact, monitors, Brave images/video, Exa agent)
- Publishing to PyPI

### Never
- Speak MCP protocol or wrap these vendors as an MCP server
- Put the skill under `.grok/`
- Commit `.env`, API keys, or fixture-server base URLs as production defaults
- Re-implement request builders inside tests (drive shipped functions)

## Terminology

| Term | Means |
|------|-------|
| Skill | `skills/research-cli/SKILL.md` — how agents **run** the CLI |
| Provider | One HTTP backend: bgpt, brave, exa, firecrawl |
| `--base-url` | Override API origin (fixture tests), not a vendor path |
| `--live` | Firecrawl scrape `maxAge=0` |
| `--self-update` | Foreground GitHub latest-release replace (always download matching asset) |
| Background update | After each dispatched command, frozen/zipapp spawn detached `--self-update` (waits for parent exit; does not block stdout) |
| `RESEARCH_CLI_NO_UPDATE` | Disables the post-command spawn; `--self-update` still runs |
| llm-context | Brave `GET /res/v1/llm/context` — page chunks, not titles-only |
| papers | Firecrawl research index (`/v2/search/research/papers`), not BGPT |
