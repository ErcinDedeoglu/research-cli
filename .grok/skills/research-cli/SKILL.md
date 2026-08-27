---
name: research-cli
description: >
  Run this repo's research-cli to search scientific papers (BGPT), the web
  (Brave Search, Exa), and page content (Exa contents, Firecrawl scrape/search)
  via direct HTTP APIs. Use when an agent needs literature search, web search,
  or page extraction. Triggers: research, papers, literature, web search,
  scrape, bgpt, brave search, exa, firecrawl. Use when the user runs /research-cli.
---

# research-cli

Call vendor HTTP APIs through this CLI. Do not call BGPT, Brave, Exa, or Firecrawl MCP servers.

Install from the repo root with `pip install -e .`, then run `research-cli`. From a checkout without install: `python -m research_cli`.

## When to use which provider

- **bgpt** — scientific papers (title or DOI, evidence fields). Optional `BGPT_API_KEY` (free tier works without a key).
- **brave search** — general web hits with title and URL. Requires `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`.
- **exa** — semantic web search, or fetch page text/highlights for a known URL (`contents`). Requires `EXA_API_KEY`.
- **firecrawl** — scrape a known URL to markdown, or search the web for URLs/snippets. Requires `FIRECRAWL_API_KEY`.

## Commands

```bash
research-cli bgpt search "CRISPR delivery neurons" --num-results 5
research-cli brave search "rust async runtime" --count 10
research-cli exa search "latest LLM evaluations" --num-results 10
research-cli exa contents https://example.com/paper
research-cli firecrawl scrape https://example.com
research-cli firecrawl search "site:arxiv.org transformers" --limit 10
```

`--base-url` overrides the API origin (local fixture servers). Output is JSON on stdout.

## Env keys

| Provider | Variables | Required |
| --- | --- | --- |
| bgpt | `BGPT_API_KEY` | no (free tier) |
| brave search | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | yes |
| exa | `EXA_API_KEY` | yes |
| firecrawl | `FIRECRAWL_API_KEY` | yes |

Missing Brave, Exa, or Firecrawl keys exit non-zero and name the provider. BGPT HTTP error bodies are printed on failure.
