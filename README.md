# research-cli

Agent-facing CLI that searches papers and the web by calling **BGPT**, **Brave Search**, **Exa**, and **Firecrawl** HTTP APIs directly (not MCP).

Agents should follow [`.grok/skills/research-cli/SKILL.md`](.grok/skills/research-cli/SKILL.md).

## Install

```bash
pip install -e .
research-cli --help
```

Or from a checkout:

```bash
PYTHONPATH=src python -m research_cli --help
```

## Providers

| Command | API | Auth |
| --- | --- | --- |
| `research-cli bgpt search QUERY` | `POST https://bgpt.pro/api/mcp-search` | optional `BGPT_API_KEY` |
| `research-cli brave search QUERY` | `GET https://api.search.brave.com/res/v1/web/search` | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` (`X-Subscription-Token`) |
| `research-cli exa search QUERY` | `POST https://api.exa.ai/search` | `EXA_API_KEY` (`x-api-key`) |
| `research-cli exa contents URL` | `POST https://api.exa.ai/contents` | `EXA_API_KEY` |
| `research-cli firecrawl scrape URL` | `POST https://api.firecrawl.dev/v2/scrape` | `FIRECRAWL_API_KEY` (`Authorization: Bearer`) |
| `research-cli firecrawl search QUERY` | `POST https://api.firecrawl.dev/v2/search` | `FIRECRAWL_API_KEY` |

`--base-url` replaces the API origin (for fixture servers). JSON is written to stdout.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
