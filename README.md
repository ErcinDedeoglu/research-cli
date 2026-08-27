# research-cli

Agent-facing CLI that searches papers and the web by calling **BGPT**, **Brave Search**, **Exa**, and **Firecrawl** HTTP APIs directly (not MCP).

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

`--base-url` replaces the API origin (for fixture servers). JSON is written to stdout.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
