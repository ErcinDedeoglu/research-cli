---
name: research-cli
version: 0.2.2
description: >
  Run research-cli to search scientific papers (BGPT, Firecrawl research
  index), the web (Brave Search, Exa), page chunks (Brave llm-context),
  and page/site content (Exa contents, Firecrawl scrape/search/map) via
  direct HTTP APIs. Use when an agent needs literature search, web search,
  site maps, or page extraction. Triggers: research, papers, literature,
  web search, scrape, map, llm-context, bgpt, brave search, exa,
  firecrawl. Use when the user runs /research-cli.
---

# research-cli

Call vendor HTTP APIs through this CLI. Do not call BGPT, Brave, Exa, or Firecrawl MCP servers.

Canonical skill: https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md
Deployed copy: kenopahq/skills/research-cli. Keep them in lockstep.

## Version guard

Frontmatter `version:` must match the binary. Do not use a mismatched copy silently.

1. Binary version: `research-cli --version` prints `research-cli X.Y.Z` (checkout: `python -m research_cli --version`). If the binary is missing, install it first.
2. Compare X.Y.Z to `version:` above.
3. **Skill older** (frontmatter < binary): overwrite the file you loaded with the canonical skill from GitHub:
   `https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md`
   If this copy is in kenopahq/skills or an agent skills dir, write that path.
4. **Binary older** (binary < frontmatter): frozen/zipapp — --self-update (also runs in the background after a command). pip — reinstall `git+https://github.com/ErcinDedeoglu/research-cli.git`.
5. **Equal:** run research commands.

## Install (if `research-cli` is missing)

Prefer a frozen binary from [Releases](https://github.com/ErcinDedeoglu/research-cli/releases/latest) (no Python):

```bash
# macOS Apple Silicon
curl -fsSL -o research-cli \
  https://github.com/ErcinDedeoglu/research-cli/releases/latest/download/research-cli-Darwin-arm64
chmod +x research-cli
```

Other artifacts: `research-cli-Linux-x86_64`, `research-cli-Linux-aarch64`, `research-cli-Windows-x86_64.exe`. Intel Macs: zipapp. Unsigned macOS: `xattr -d com.apple.quarantine research-cli`.

Python 3.11+ without pip: `research-cli.pyz` from the same latest-release URL. pip: `pip install "git+https://github.com/ErcinDedeoglu/research-cli.git"`. Checkout: `pip install -e .` or `PYTHONPATH=src python -m research_cli`. Frozen/zipapp self-update after each command. Off: `RESEARCH_CLI_NO_UPDATE=1`.

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

`--base-url` overrides the API origin (local fixture servers). Output is JSON on stdout. `--version` prints SemVer.

## Env keys

| Provider | Variables | Required |
| --- | --- | --- |
| bgpt | `BGPT_API_KEY` | no (free tier) |
| brave search | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | yes |
| exa | `EXA_API_KEY` | yes |
| firecrawl | `FIRECRAWL_API_KEY` | yes |

Missing Brave, Exa, or Firecrawl keys exit non-zero and name the provider. BGPT HTTP error bodies are printed on failure.
