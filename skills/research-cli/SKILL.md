---
name: research-cli
version: 0.8.0
description: >
  MUST USE for search and research. Whenever the user asks to search, research,
  look up, find, google, investigate, cite, gather sources, check the web, or
  find papers/literature — run this CLI and call EVERY provider in parallel
  (bgpt, brave, exa, firecrawl, reddit). For CVE, exploit, PoC, RCE, or hacktool
  queries, also run sploitus and exploitdb. For malware family, YARA, or actor
  queries, also run malpedia. Do not pick one. Do not guess or use vendor MCP.
  Triggers: search, research, papers, literature, scrape, lookup, google, cite,
  sources, bgpt, brave, exa, firecrawl, reddit, sploitus, exploitdb, malpedia, /research-cli.
---

# research-cli

Do not call BGPT, Brave, Exa, Firecrawl, Reddit, Sploitus, Exploit-DB, or Malpedia MCP servers. Run this CLI.

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
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
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
research-cli reddit search "QUERY"
```

For CVE, exploit, PoC, RCE, or hacktool queries, also run:

```bash
research-cli sploitus search "QUERY"
research-cli exploitdb search "QUERY"
```

For malware family, YARA, or actor queries, also run:

```bash
research-cli malpedia search "QUERY"
```

Merge the JSON. Then scrape/read specific URLs or paper IDs if needed. For Reddit, search then `reddit thread` on the best permalinks; `reddit subreddit` to browse a community. For Sploitus: `search` then `exploit` on an id for the full PoC (CVSS, EPSS, entry point, tags, related); `cve` / `product` / `latest` / `home` for the HTML hubs; `autocomplete` for typeahead. Pass `--source` on search when you need PoC bodies in the hit list; `--type tools` searches hacktools. For Exploit-DB: `search` then `exploit` / `raw` for the OffSec PoC; `download` writes `/download/{id}` to disk (exploit, paper PDF, shellcode, or attached app); `latest` is the homepage table; `ghdb` / `dork` for Google dorks; `papers` / `paper` and `shellcodes` / `shellcode` for those databases; `authors` typeahead; `stats` for counts. Pass `--output` as a file or directory. For Malpedia (guest, no key): `search` then `family` (full metadata including `uuid`, `library_entries`, `urls`) and `yara` on a family id (`win.emotet`); `bib --family` for the library BibTeX; `references --url` on a family URL to get linked actors (the details-page attribution); `actor` for an actor id. `yara --zip` writes the family rule zip. `yara-list` indexes guest rules; `yara-dump --tlp white` / `--auto` writes the bulk `.yar` (or `--zip`); `yara-after YYYY-MM-DD` is the incremental JSON. `families` / `actors` list ids; `--full` dumps every record (multi-MB). `misp` is the galaxy cluster (~4MB). `bib` without flags is the full library (~6.7MB). Sample zip endpoints are invite-only and not on the CLI. For bulk dumps use `--output` and `--timeout 180`.

**bgpt** papers (optional `BGPT_API_KEY`). **brave** `llm-context` is page chunks (`BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`); `search` is titles/URLs. **exa** semantic search (`EXA_API_KEY`). **firecrawl** web search + paper index (`FIRECRAWL_API_KEY`). **reddit** posts + comments (`REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET`). **sploitus** exploit/hacktool index (no key). **exploitdb** OffSec Exploit Database (no key). **malpedia** malware families/actors/YARA/bib/MISP (no key; guest).

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
research-cli reddit search "CRISPR neurons" --sort top --time week --limit 10
research-cli reddit search "async rust" --subreddit rust
research-cli reddit thread abc123 --sort top --limit 50
research-cli reddit thread https://www.reddit.com/r/python/comments/abc123/title/
research-cli reddit subreddit rust --sort top --time week --limit 25
research-cli sploitus search "CVE-2021-44228" --type exploits --sort score --limit 10
research-cli sploitus search "wordpress rce" --type exploits --sort relevance --source
research-cli sploitus search "c2" --type tools --sort date
research-cli sploitus exploit EDB-ID:50592
research-cli sploitus exploit https://sploitus.com/exploit?id=EDB-ID:50592
research-cli sploitus cve CVE-2021-44228 --limit 20
research-cli sploitus product wordpress --limit 50
research-cli sploitus latest --limit 25
research-cli sploitus home
research-cli sploitus autocomplete log4
research-cli exploitdb search "CVE-2021-44228" --type remote --platform java
research-cli exploitdb latest
research-cli exploitdb exploit 50592
research-cli exploitdb raw 50592
research-cli exploitdb download 50592 --output /tmp
research-cli exploitdb papers "polkit" --language english
research-cli exploitdb paper 50981
research-cli exploitdb shellcodes "reverse tcp" --platform linux
research-cli exploitdb shellcode 52599
research-cli exploitdb ghdb "inurl:admin" --category 9
research-cli exploitdb dork 2
research-cli exploitdb authors leon
research-cli exploitdb stats
research-cli malpedia search emotet
research-cli malpedia family win.emotet
research-cli malpedia actor apt28
research-cli malpedia yara win.emotet
research-cli malpedia yara win.emotet --zip --output /tmp
research-cli malpedia families --limit 20
research-cli malpedia families --full --limit 5
research-cli malpedia actors --limit 20
research-cli malpedia bib --family win.owowa
research-cli malpedia bib --actor goffee
research-cli malpedia misp --output /tmp
research-cli malpedia references --url https://securelist.com/goffee-apt-new-attacks/116139/
research-cli malpedia yara-list --family win.emotet
research-cli malpedia yara-dump --tlp white --output /tmp --timeout 180
research-cli malpedia yara-dump --auto --zip --output /tmp --timeout 180
research-cli malpedia yara-after 2026-01-01
research-cli malpedia version
```

`--base-url` overrides the API origin (local fixture servers). Output is JSON on stdout. `--version` prints SemVer.

## Env keys

| Provider | Variables | Required |
| --- | --- | --- |
| bgpt | `BGPT_API_KEY` | no (free tier) |
| brave search | `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY` | yes |
| exa | `EXA_API_KEY` | yes |
| firecrawl | `FIRECRAWL_API_KEY` | yes |
| reddit | `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` | yes |
| sploitus | none | no |
| exploitdb | none | no |
| malpedia | none | no |

Missing Brave, Exa, Firecrawl, or Reddit keys exit non-zero and name the provider. BGPT, Sploitus, Exploit-DB, and Malpedia HTTP error bodies are printed on failure.
