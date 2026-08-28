<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Last updated: 2026-08-28 | Last verified: 2026-08-28 -->

# AGENTS.md

**This repo** is an agent-facing **research CLI**. It calls **BGPT, Brave Search, Exa, Firecrawl, Reddit, Sploitus, Exploit-DB, Malpedia, and X over HTTP REST** (not MCP). Agents use the CLI via the skill; coding agents change code here.

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
| Next SemVer | `python scripts/semver.py next` | <1s |

After install, `research-cli` is the same entry as `python -m research_cli`. Keys: process env, else `~/.config/research-cli/env` (loaded by the CLI). Repo `.env` is gitignored and is **not** auto-loaded; copy `.env.example` into the config file or export it.

## File Map

```
src/research_cli/cli.py              → argparse + dispatch
src/research_cli/update.py           → GitHub Releases self-update (frozen/zipapp)
src/research_cli/http.py             → HttpRequest/Response, urllib transport; frozen SSL uses certifi or OS CA bundle
src/research_cli/keys.py             → env keys / MissingKeyError
src/research_cli/providers/bgpt.py   → POST /api/mcp-search
src/research_cli/providers/brave.py  → GET web/search, GET llm/context
src/research_cli/providers/exa.py    → POST /search, POST /contents
src/research_cli/providers/firecrawl.py → scrape, search, map
src/research_cli/providers/firecrawl_papers.py → papers search/inspect/read/related
src/research_cli/providers/reddit.py     → POST /api/v1/access_token, GET /search, GET /comments/{id}, GET /r/{sub}/{sort}
src/research_cli/providers/sploitus.py   → POST /search; GET /autocomplete; GET /exploit?id=; GET /cve/{id}; GET /product/{slug}[/page/N]; GET /latest[/page/N]; GET /
src/research_cli/providers/exploitdb.py  → GET /search, GET /, GET /papers, GET /shellcodes, GET /google-hacking-database (XHR JSON); GET /exploits/{id}, /docs/{id}, /shellcodes/{id}, /ghdb/{id}, /raw/{id}, /download/{id}; GET /authors-ajax; GET /api/authorid/{id}
src/research_cli/providers/malpedia.py   → guest GET /api/find|get|list (family, actor, yara, bib, misp, references, version); yara tlp/auto/after dumps; family yara zip. Sample zip helpers exist in-module, not CLI-wired.
src/research_cli/providers/x.py          → GraphQL SearchTimeline / TweetDetail (cookie auth + generated x-client-transaction-id)
src/research_cli/providers/x_transaction.py → homepage SVG + ondemand.s.js tid generator (stdlib)
skills/research-cli/SKILL.md         → agent playbook (not under .grok/; copy to kenopahq/skills/research-cli on change)
tests/test_skill.py                  → skill ↔ CLI parser/keys alignment
tests/test_providers.py              → injectable HTTP: method/path/auth/parse
tests/test_cli.py                    → --help, missing keys, fixture-server CLI
tests/test_update.py                 → version compare, assets, replace, background spawn, --self-update
tests/test_semver.py                 → conventional-commit bump rules and git tag next-version
tests/fixtures.py                    → fixture JSON + local HTTP server
.env.example                         → placeholder keys
.github/workflows/ci.yml             → unittest on Python 3.11/3.12
.github/workflows/release.yml        → test, SemVer bump/tag, pip-cached freeze, GitHub Release on every main commit
requirements-freeze.txt              → pinned PyInstaller for the freeze job
scripts/semver.py                    → next/apply MAJOR.MINOR.PATCH from v* tags + conventional commits
scripts/build-zipapp.sh              → stdlib zipapp (`research-cli.pyz`)
```

## Release lifecycle (every push to `main`)

Source of truth: [`.github/workflows/release.yml`](.github/workflows/release.yml) + [`scripts/semver.py`](scripts/semver.py). Do not invent a second process.

| Step | Job | What happens |
|------|-----|----------------|
| 1 | `test` | `PYTHONPATH=src python -m unittest discover -s tests -v` |
| 2 | `version` | `python scripts/semver.py next` then `apply` (writes `__version__` **and** skill frontmatter `version:`); commit `chore: release vX.Y.Z`; `git tag vX.Y.Z`; push tag + commit |
| 3 | `zipapp` + `freeze` (parallel) | Checkout **the tag**, not the triggering SHA. Zipapp + PyInstaller onefile. Pip cache keyed by `requirements-freeze.txt` |
| 4 | `publish` | `gh release create "$TAG" artifacts --verify-tag --latest`. Tag already exists; do **not** pass `--target $TAG` (GitHub 422: `target_commitish` must be a branch or SHA) |

**Version**

| Fact | Value |
|------|--------|
| Single source | `src/research_cli/__init__.py` `__version__` |
| Package metadata | `pyproject.toml` `dynamic = ["version"]` → `attr = research_cli.__version__` |
| Tags | `vMAJOR.MINOR.PATCH` only (`r-*` leftovers are not SemVer) |
| `feat:` | minor |
| `fix:` / `chore:` / `docs:` / other | patch |
| `type!:` or `BREAKING CHANGE:` | major; on 0.x that is still a minor |
| No `v*` tag yet | inspect HEAD only; base is the file version |
| HEAD already at `vX.Y.Z` | no bump |
| Preview | `python scripts/semver.py next` |

**Artifacts** (self-update `asset_name()` must match): `research-cli-Darwin-arm64`, `research-cli-Linux-x86_64`, `research-cli-Linux-aarch64`, `research-cli-Windows-x86_64.exe`, `research-cli.pyz`. No Intel Mac binary (macos-13 retired; zipapp). Frozen/zipapp clients force-update from `/releases/latest` after each command.

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) tests 3.11/3.12 and does **not** bump or publish.

## Golden Samples

| For | Reference | Key patterns |
|-----|-----------|--------------|
| New HTTP operation | `src/research_cli/providers/brave.py` | `build_*_request` + `parse_*` + `execute_json` |
| CLI wiring | `src/research_cli/cli.py` | shared `--base-url`/`--timeout`, leaf subparser, `_dispatch` |
| Skill stay-in-sync | `tests/test_skill.py` | examples must `parse_args`; every leaf command has an example |
| Fixture HTTP | `tests/fixtures.py` | path-routed JSON, not live vendors |
| Cut a release | `.github/workflows/release.yml` + `scripts/semver.py` | conventional commit on `main`; workflow owns `__version__`, tag, freeze, `gh release create --verify-tag` |

## Heuristics

| When | Do |
|------|-----|
| Agent needs papers/web/scrape | Point at `skills/research-cli/SKILL.md` and the CLI — do not call vendor MCP servers |
| Agent needs malware family/YARA | `research-cli malpedia search` then `family` / `yara` / `bib --family` / `references --url` (guest; sample zip not on CLI) |
| Agent needs X/Twitter posts | `research-cli x search` then `x thread` (`X_AUTH_TOKEN` + `X_CT0`; never commit cookies) |
| CVE/exploit/PoC also | Run sploitus **and** exploitdb (EDB is the OffSec primary; Sploitus is an index) |
| Add/change a CLI command or flag | Update provider + `cli.py` + skill examples + `tests/test_skill.py` in the same change, then copy `skills/research-cli/SKILL.md` to `/Users/ercin/git/github/kenopahq/skills/research-cli/` |
| Skill `version:` vs `research-cli --version` | Must match. Skill older → replace file from `raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md`. Binary older → `--self-update` |
| Add a provider HTTP path | Injectable `transport`; assert method, host/path, auth header, parsed fields |
| Skill vs `--help` disagree | Code and skill both wrong until `test_skill` is green |
| Need live keys | `.env` locally; never commit it |
| Adding a Python dependency | Ask first — stdlib HTTP only unless asked |
| Change freeze/zipapp artifact names | Keep `asset_name()` in `update.py` in lockstep with `.github/workflows/release.yml` |
| Commit to `main` | Conventional commits: `feat:` minor, `fix:`/`chore:`/`docs:` patch, `feat!:` or `BREAKING CHANGE:` major (0.x major → minor). Do not hand-edit `__version__`; the release workflow owns it |

## Boundaries

### Always
- Keep `skills/research-cli/SKILL.md` aligned with `build_parser()` and `keys.py`
- Run `PYTHONPATH=src python -m unittest discover -s tests -v` after CLI/skill changes
- JSON on stdout, errors on stderr; missing Brave/Exa/Firecrawl/Reddit/X keys exit 2 and name the provider; Sploitus, Exploit-DB, and Malpedia catalog/YARA need no key; never commit `X_AUTH_TOKEN` / `X_CT0`
- Conventional commits on `main`; leave `__version__` to the release workflow
- Publish with `gh release create <tag> --verify-tag` (tag is created in the `version` job)

### Ask first
- New vendor SDKs or wrapping remaining MCP tools (crawl, interact, monitors, Brave images/video, Exa agent)
- Publishing to PyPI

### Never
- Speak MCP protocol or wrap these vendors as an MCP server
- Put the skill under `.grok/`
- Commit `.env`, API keys, or fixture-server base URLs as production defaults
- Re-implement request builders inside tests (drive shipped functions)
- Hand-edit `__version__` on `main`, or `gh release create --target vX.Y.Z` (invalid `target_commitish`)
- Re-add `macos-13` / `Darwin-x86_64` freeze (runner retired)

## Terminology

| Term | Means |
|------|-------|
| Skill | `skills/research-cli/SKILL.md` — how agents **run** the CLI |
| Provider | One HTTP backend: bgpt, brave, exa, firecrawl, reddit, sploitus, exploitdb, malpedia, x |
| `--base-url` | Override API origin (fixture tests), not a vendor path |
| `--live` | Firecrawl scrape `maxAge=0` |
| `--self-update` | Foreground GitHub latest-release replace (always download matching asset) |
| Background update | After each invocation (including `--version`/`--help`/parse errors), frozen/zipapp spawn detached `--self-update` (waits for parent exit; does not block stdout). Spawn sets `PYINSTALLER_RESET_ENVIRONMENT=1` so onefile children unpack independently (PyInstaller ≥ 6.9). `--self-update` itself does not respawn. Failures append to `~/.cache/research-cli/update.log` |
| `RESEARCH_CLI_NO_UPDATE` | Disables the post-command spawn; `--self-update` still runs |
| llm-context | Brave `GET /res/v1/llm/context` — page chunks, not titles-only |
| papers | Firecrawl research index (`/v2/search/research/papers`), not BGPT |
| sploitus | Guest site: SPA `POST /search` + HTML hubs (`/exploit`, `/cve`, `/product`, `/latest`) |
| malpedia | Fraunhofer FKIE malware catalog: guest `GET /api/find|get|list|yara|bib|misp|references`; bulk `yara-dump` / `yara-after`; sample zip not on CLI |
| exploitdb | Guest DataTables: `GET /search` with `X-Requested-With: XMLHttpRequest`; hubs `/exploits/{id}`, `/raw/{id}`, GHDB, papers, shellcodes |
| x | Logged-in X web GraphQL: `GET /i/api/graphql/{queryId}/SearchTimeline` and `TweetDetail`; cookies `auth_token`+`ct0`; generated `x-client-transaction-id` |
| SemVer | `src/research_cli/__init__.py` `__version__`; skill frontmatter `version:` must match; tags `vMAJOR.MINOR.PATCH`; `python scripts/semver.py next` |
