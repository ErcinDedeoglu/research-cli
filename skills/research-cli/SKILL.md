---
name: research-cli
version: 0.3.1
description: >
  MUST USE for search and research. Whenever the user asks to search, research,
  look up, find, google, investigate, cite, gather sources, check the web, or
  find papers/literature — run this CLI and call EVERY provider in parallel
  (bgpt, brave, exa, firecrawl). Do not pick one. Do not guess or use vendor
  MCP. Triggers: search, research, papers, literature, scrape, lookup, google,
  cite, sources, bgpt, brave, exa, firecrawl, /research-cli.
---

# research-cli

Do not call BGPT, Brave, Exa, or Firecrawl MCP servers. Run this CLI.

## Version guard

`version:` above must match `research-cli --version`.

1. Missing binary → [Install if missing](#install-if-missing).
2. Skill older → replace this file with https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md
3. Binary older → --self-update
4. Match → run commands

## Install if missing

```bash
command -v research-cli
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
base="https://github.com/ErcinDedeoglu/research-cli/releases/latest/download"
os="$(uname -s)"; arch="$(uname -m)"
case "$os-$arch" in
  Darwin-arm64) asset=research-cli-Darwin-arm64 ;;
  Linux-x86_64) asset=research-cli-Linux-x86_64 ;;
  Linux-aarch64|Linux-arm64) asset=research-cli-Linux-aarch64 ;;
  *) echo "unsupported: $os $arch"; exit 1 ;;
esac
curl -fsSL -o "$HOME/.local/bin/research-cli" "$base/$asset"
chmod +x "$HOME/.local/bin/research-cli"
```

Windows: `$base/research-cli-Windows-x86_64.exe` → `research-cli.exe` on PATH. macOS quarantine: `xattr -d com.apple.quarantine "$HOME/.local/bin/research-cli"`.

## Keys

After install, write `$HOME/.config/research-cli/env` (Windows: `%APPDATA%\research-cli\env`). Process env overrides the file. If a required key is missing, ask the user and write it, then run search.

```
BRAVE_API_KEY=
EXA_API_KEY=
FIRECRAWL_API_KEY=
# BGPT_API_KEY=
```

chmod 600 the file.

## Search / research

On search or research, run **all** of these in parallel with the same query. Do not pick one provider.

```bash
research-cli bgpt search "QUERY"
research-cli brave llm-context "QUERY"
research-cli exa search "QUERY"
research-cli firecrawl search "QUERY" --categories research
research-cli firecrawl papers search "QUERY"
```

Merge the JSON. Then scrape/read specific URLs or paper IDs if needed.

**bgpt** papers (optional `BGPT_API_KEY`). **brave** `llm-context` is page chunks (`BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`); `search` is titles/URLs. **exa** semantic search (`EXA_API_KEY`). **firecrawl** web search + paper index (`FIRECRAWL_API_KEY`).

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
