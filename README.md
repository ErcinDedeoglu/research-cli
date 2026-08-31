# research-cli

Agent-facing CLI that searches papers and the web by calling **BGPT**, **Brave Search**, **Exa**, **Firecrawl**, **Reddit**, **Sploitus**, **Exploit-DB**, **Malpedia**, **X**, and **TGStat** HTTP APIs directly, plus **Telegram** as a user MTProto client for history/download (Telethon, not Bot API, not MCP).

Agents should follow [`skills/research-cli/SKILL.md`](skills/research-cli/SKILL.md).

## Install

Binaries (no Python on the machine) from [Releases](https://github.com/ErcinDedeoglu/research-cli/releases):

```bash
# macOS Apple Silicon
curl -fsSL -o research-cli \
  https://github.com/ErcinDedeoglu/research-cli/releases/latest/download/research-cli-Darwin-arm64
chmod +x research-cli && ./research-cli --help
```

Other artifacts: `research-cli-Linux-x86_64`, `research-cli-Linux-aarch64`, `research-cli-Windows-x86_64.exe`. Intel Macs should use the zipapp. Unsigned macOS downloads may need `xattr -d com.apple.quarantine research-cli`.

With Python 3.11+ (no pip):

```bash
curl -fsSL -o research-cli.pyz \
  https://github.com/ErcinDedeoglu/research-cli/releases/latest/download/research-cli.pyz
python3 research-cli.pyz --help
```

With pip:

```bash
pip install "git+https://github.com/ErcinDedeoglu/research-cli.git"
research-cli --help
```

From a checkout:

```bash
pip install -e .
# or: PYTHONPATH=src python -m research_cli --help
```

Every push to `main` bumps **SemVer** (`vMAJOR.MINOR.PATCH`) from conventional commits and publishes a GitHub Release. `research-cli --version` is `src/research_cli/__init__.py` (single source; `pyproject.toml` reads it). Bumps: `feat:` minor, `fix:`/`chore:`/`docs:`/other patch, `type!:` or `BREAKING CHANGE:` major (on 0.x, major is a minor). Frozen binaries and `research-cli.pyz` then force a self-update from that latest release **after** each command returns (detached, so search/scrape is not delayed). `research-cli --self-update` runs that updater in the foreground. `RESEARCH_CLI_NO_UPDATE=1` disables the background updater. pip installs are not replaced; `--self-update` prints a `pip install --upgrade` hint instead.

## Providers

| Command | API | Auth |
| --- | --- | --- |
| `research-cli bgpt search QUERY` | `POST https://bgpt.pro/api/mcp-search` | optional `BGPT_API_KEY` |
| `research-cli brave search QUERY` | `GET https://api.search.brave.com/res/v1/web/search` | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` |
| `research-cli brave llm-context QUERY` | `GET https://api.search.brave.com/res/v1/llm/context` | same as Brave search |
| `research-cli exa search QUERY` | `POST https://api.exa.ai/search` | `EXA_API_KEY` |
| `research-cli exa contents URL` | `POST https://api.exa.ai/contents` | `EXA_API_KEY` |
| `research-cli firecrawl scrape URL` | `POST https://api.firecrawl.dev/v2/scrape` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl search QUERY` | `POST https://api.firecrawl.dev/v2/search` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl map URL` | `POST https://api.firecrawl.dev/v2/map` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl papers search QUERY` | `GET https://api.firecrawl.dev/v2/search/research/papers` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl papers inspect ID` | `GET .../papers/{id}` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl papers read ID --question Q` | `GET .../papers/{id}?query=` | `FIRECRAWL_API_KEY` |
| `research-cli firecrawl papers related ID --intent T` | `GET .../papers/{id}/similar` | `FIRECRAWL_API_KEY` |
| `research-cli sploitus search QUERY` | `POST https://sploitus.com/search` | none |
| `research-cli sploitus exploit ID` | `GET https://sploitus.com/exploit?id=` | none |
| `research-cli sploitus cve CVE` | `GET https://sploitus.com/cve/{id}` | none |
| `research-cli sploitus product NAME` | `GET https://sploitus.com/product/{slug}` | none |
| `research-cli sploitus latest` | `GET https://sploitus.com/latest` | none |
| `research-cli sploitus autocomplete Q` | `GET https://sploitus.com/autocomplete` | none |
| `research-cli exploitdb search QUERY` | `GET https://www.exploit-db.com/search` (XHR JSON) | none |
| `research-cli malpedia search QUERY` | `GET https://malpedia.caad.fkie.fraunhofer.de/api/find/{family,actor}` | none |
| `research-cli malpedia family ID` | `GET .../api/get/family/{id}` | none |
| `research-cli malpedia yara ID` | `GET .../api/get/yara/{id}` | none |
| `research-cli malpedia bib --family ID` | `GET .../api/get/bib/family/{id}` | none |
| `research-cli x search QUERY` | X web GraphQL SearchTimeline | `X_AUTH_TOKEN` + `X_CT0` |
| `research-cli tgstat search QUERY` | TGStat Premium-search `GET /search` + `POST /search/list` | `TGSTAT_IDR` + `TGSTAT_SIRK` |
| `research-cli tgstat sources QUERY` | Premium-search mentioning channels | same |
| `research-cli tgstat mentions QUERY` | `POST /search/mentions-chart` | same |
| `research-cli tgstat export QUERY` | `POST /search/export/xls` (xlsx) | same |
| `research-cli tgstat catalogs` | Static country/language/category lists | none |
| `research-cli tgstat download URL` | Telegram `download_media` (website has no file bytes) | Telegram session |
| `research-cli telegram history @user` | MTProto `messages.getHistory` | `TELEGRAM_API_ID` + `TELEGRAM_API_HASH` + `TELEGRAM_SESSION` |
| `research-cli telegram download URL` | MTProto `download_media` | same |

## Tests

```bash
pip install -e .
PYTHONPATH=src python -m unittest discover -s tests -v
```
