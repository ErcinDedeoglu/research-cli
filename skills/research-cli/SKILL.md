---
name: research-cli
version: 0.2.7
description: >
  MUST USE for search and research. Whenever the user asks to search, research,
  look up, find, google, investigate, cite, gather sources, check the web, or
  find papers/literature — run this CLI instead of guessing or using Brave/Exa/
  BGPT/Firecrawl MCP. Covers web search, scientific papers, page scrape, site
  maps, llm-context. Triggers: search, research, papers, literature, scrape,
  lookup, google, cite, sources, bgpt, brave, exa, firecrawl, /research-cli.
---

# research-cli

Call vendor HTTP APIs through this CLI. Do not call BGPT, Brave, Exa, or Firecrawl MCP servers.

Canonical skill: https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md
Deployed copy: kenopahq/skills/research-cli. Keep them in lockstep.

## Version guard

Frontmatter `version:` must match the binary. Do not use a mismatched copy silently.

1. Detect (`command -v research-cli`). If missing, **install** using [Install if missing](#install-if-missing), then continue. No Python, pip, or zipapp — this is a self-contained binary.
2. `research-cli --version` prints `research-cli X.Y.Z`. Compare to `version:` above.
3. **Skill older** (frontmatter < binary): overwrite the file you loaded with
   `https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md`
4. **Binary older** (binary < frontmatter): --self-update (also runs in the background after a command).
5. **Equal:** run research commands.

## Install if missing

Download **one** frozen binary from GitHub Releases (no Python). Put it on `PATH` (`$HOME/.local/bin` needs no root).

```bash
command -v research-cli

mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
base="https://github.com/ErcinDedeoglu/research-cli/releases/latest/download"
os="$(uname -s)"
arch="$(uname -m)"
case "$os-$arch" in
  Darwin-arm64) asset=research-cli-Darwin-arm64 ;;
  Linux-x86_64) asset=research-cli-Linux-x86_64 ;;
  Linux-aarch64|Linux-arm64) asset=research-cli-Linux-aarch64 ;;
  *) echo "unsupported platform: $os $arch"; exit 1 ;;
esac
curl -fsSL -o "$HOME/.local/bin/research-cli" "$base/$asset"
chmod +x "$HOME/.local/bin/research-cli"
```

Windows: download `$base/research-cli-Windows-x86_64.exe`, name it `research-cli.exe`, put it on `PATH`.

Unsigned macOS: `xattr -d com.apple.quarantine "$HOME/.local/bin/research-cli"`. Then `research-cli --version` and return to the version guard. The binary self-updates after each command. Off: `RESEARCH_CLI_NO_UPDATE=1`.

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
