---
name: research-cli
description: >
  Run this repo's research-cli to search scientific papers (BGPT, Firecrawl
  research index), the web (Brave Search, Exa), page chunks (Brave llm-context),
  and page/site content (Exa contents, Firecrawl scrape/search/map) via direct
  HTTP APIs. Use when an agent needs literature search, web search, site maps,
  or page extraction. Triggers: research, papers, literature, web search,
  scrape, map, llm-context, bgpt, brave search, exa, firecrawl. Use when the
  user runs /research-cli.
---

# research-cli

Call vendor HTTP APIs through this CLI. Do not call BGPT, Brave, Exa, or Firecrawl MCP servers.

Install from the repo root with `pip install -e .`, then run `research-cli`. From a checkout without install: `python -m research_cli`.

## When to use which provider

- **bgpt** — full-text experimental evidence (title/DOI). Optional `BGPT_API_KEY`.
- **brave search** — general web hits. `llm-context` returns ranked page chunks in one call (prefer this when you need content, not just URLs). Requires `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`.
- **exa** — semantic search (`--include-domains`, `--category`, `--start-published`, `--highlights`; stacking domain+category+date often returns no hits), or `contents` for a known URL. Requires `EXA_API_KEY`.
- **firecrawl** — scrape a URL (`--live` for a fresh fetch), search the web (`--categories research`, `--scrape` for markdown), `map` a site's URLs, or the paper index (`papers search/inspect/read/related`: PubMed/bioRxiv/arXiv abstracts and passages). Requires `FIRECRAWL_API_KEY`.

## Commands

```bash
research-cli bgpt search "CRISPR delivery neurons" --num-results 5
research-cli brave search "rust async runtime" --count 10 --freshness pw
research-cli brave llm-context "best practices for RAG" --count 20
research-cli exa search "LLM evaluations" --include-domains arxiv.org --highlights
research-cli exa contents https://example.com
research-cli firecrawl scrape https://example.com --live
research-cli firecrawl search "transformers" --categories research --limit 10
research-cli firecrawl map https://docs.firecrawl.dev --search webhook --limit 50
research-cli firecrawl papers search "CRISPR off-target T cells" --k 10
research-cli firecrawl papers inspect arxiv:1706.03762
research-cli firecrawl papers read arxiv:1706.03762 --question "what is the architecture?"
research-cli firecrawl papers related arxiv:1706.03762 --intent "efficient attention" --mode similar
```

`--base-url` overrides the API origin (local fixture servers). Output is JSON on stdout.

Frozen binaries and `research-cli.pyz` force-update from GitHub Releases after the command finishes (background, does not block JSON output). Foreground: --self-update. Disable with `RESEARCH_CLI_NO_UPDATE=1`. pip installs are not replaced.

## Env keys

| Provider | Variables | Required |
| --- | --- | --- |
| bgpt | `BGPT_API_KEY` | no (free tier) |
| brave search | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | yes |
| exa | `EXA_API_KEY` | yes |
| firecrawl | `FIRECRAWL_API_KEY` | yes |

Missing Brave, Exa, or Firecrawl keys exit non-zero and name the provider. BGPT HTTP error bodies are printed on failure.
