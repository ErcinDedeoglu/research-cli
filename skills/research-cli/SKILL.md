---
name: research-cli
version: 0.11.0
description: >
  MUST USE for search and research. Whenever the user asks to search, research,
  look up, find, google, investigate, cite, gather sources, check the web, or
  find papers/literature — run this CLI and call EVERY provider in parallel
  (bgpt, brave, exa, firecrawl, reddit, x, tgstat). For CVE, exploit, PoC, RCE, or hacktool
  queries, also run sploitus and exploitdb. For malware family, YARA, or actor
  queries, also run malpedia. For Telegram files after a tgstat hit, use tgstat download
  on telegram.target (Telegram user session). Do not pick one. Do not guess or use vendor MCP.
  Triggers: search, research, papers, literature, scrape, lookup, google, cite,
  sources, bgpt, brave, exa, firecrawl, reddit, sploitus, exploitdb, malpedia, x, twitter, telegram, tgstat, /research-cli.
---

# research-cli

Run this CLI. Do not call vendor MCP servers. Do not invent subcommands or flags — copy from **Commands** below.

JSON on stdout, errors on stderr. Shared flags on every provider command: `--timeout` (seconds, default 60), `--base-url` (fixture/origin override only). Missing Brave/Exa/Firecrawl/Reddit/X/TGStat/Telegram keys exit 2 and name the provider.

## Version guard

`version:` must match `research-cli --version`. Missing binary → https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/INSTALL.md (no CLI needed). Skill older → replace from https://raw.githubusercontent.com/ErcinDedeoglu/research-cli/main/skills/research-cli/SKILL.md. Binary older → `--self-update`. Already on PATH: `research-cli help install` is the same install text.

## Keys

`research-cli help keys` — env file (`$HOME/.config/research-cli/env`, Windows `%APPDATA%\research-cli\env`), provider key table, missing-key behavior. Missing required key: ask the user, write the file, retry. Skip `x` if cookies are unset; skip `tgstat` if `TGSTAT_IDR`/`TGSTAT_SIRK` are unset; skip `telegram` if `TELEGRAM_SESSION` is unset; do not block other providers.

## Search

Same query, all of these in parallel. Do not pick one provider.

```bash
research-cli bgpt search "QUERY"
research-cli brave llm-context "QUERY"
research-cli exa search "QUERY"
research-cli firecrawl search "QUERY" --categories research
research-cli firecrawl papers search "QUERY"
research-cli reddit search "QUERY"
research-cli x search "QUERY"
research-cli tgstat search "QUERY"
```

CVE / exploit / PoC / RCE / hacktool — also:

```bash
research-cli sploitus search "QUERY"
research-cli exploitdb search "QUERY"
```

Malware family / YARA / actor — also:

```bash
research-cli malpedia search "QUERY"
```

Merge the JSON, then use **Commands** to follow a hit (scrape a URL, open a thread, read a paper id, dump a PoC, `tgstat download` a Telegram file). Do not stop at titles if the user needs the page, comments, or exploit body.

## Commands

Use these exact invocations. Flags listed here are the ones that exist. Values in `a|b` are the only allowed choices.

### help

Setup text (JSON `body`). No API key.

```bash
research-cli help install
research-cli help keys
```

`research-cli help` lists topics. `installation` is an alias of `install`.

### bgpt

Scientific papers (optional `BGPT_API_KEY`). One op: `search`. `--num-results` default 10. `--days-back` optional int. `--output-format` default `evidence`.

```bash
research-cli bgpt search "CRISPR delivery neurons" --num-results 5
```

### brave

Web. Needs `BRAVE_API_KEY` or `BRAVE_SEARCH_API_KEY`.

- `llm-context` — ranked **page chunks** (use this on the parallel search). `--count` default 20.
- `search` — titles/URLs/snippets only. `--count` default 10. `--offset` pages.

Shared: `--country`. `--freshness` is `pd` (day), `pw` (week), `pm` (month), `py` (year), or `YYYY-MM-DDtoYYYY-MM-DD`.

```bash
research-cli brave llm-context "best practices for RAG" --count 20
research-cli brave search "rust async runtime" --count 10 --freshness pw
```

### exa

Semantic web. Needs `EXA_API_KEY`.

- `search` — hits. `--num-results` default 10. `--include-domains` / `--exclude-domains` comma lists. `--category` (e.g. `research paper`). `--start-published` / `--end-published`. `--highlights` and `--text` pull snippets/body with the search.
- `contents` — fetch one URL’s text.

```bash
research-cli exa search "LLM evaluations" --include-domains arxiv.org --highlights
research-cli exa contents https://example.com
```

### firecrawl

Scrape + web search + paper index. Needs `FIRECRAWL_API_KEY`.

- `search` — web hits. `--limit` default 10. `--categories` (use `research` on the parallel search). `--include-domains` / `--exclude-domains`. `--scrape` also fetches markdown for each hit.
- `scrape` — one URL to markdown. `--live` forces a live fetch (`maxAge=0`). `--formats` default `markdown`. `--max-age` ms. `--no-main-content` keeps chrome.
- `map` — list URLs under a site. `--search` filters paths. `--limit` default 50.
- `papers` — research **index** (not BGPT). `search` → `inspect` → `read` / `related`. Paper ids look like `arxiv:1706.03762`.
  - `papers search` — `--k` default 40, `--authors`, `--categories`, `--from` / `--to` dates.
  - `papers inspect` — metadata for one id.
  - `papers read` — `--question` is required. `--k` default 4 passages.
  - `papers related` — `--intent` is required. `--mode` `similar|citers|references` (default `similar`). `--k` default 40. `--anchors`.

```bash
research-cli firecrawl search "transformers" --categories research --limit 10
research-cli firecrawl scrape https://example.com --live
research-cli firecrawl map https://docs.firecrawl.dev --search webhook --limit 50
research-cli firecrawl papers search "CRISPR off-target T cells" --k 10
research-cli firecrawl papers inspect arxiv:1706.03762
research-cli firecrawl papers read arxiv:1706.03762 --question "what is the architecture?"
research-cli firecrawl papers related arxiv:1706.03762 --intent "efficient attention" --mode similar
```

### reddit

Posts and comments. Needs `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

- `search` — `--sort` `relevance|hot|top|new|comments` (default `relevance`). `--time` `hour|day|week|month|year|all` (default `all`). `--limit` default 25. `--subreddit` without `r/`.
- `thread` — post id, `t3_` id, or comments URL. `--sort` `best|top|new|controversial|old|qa` (default `best`). `--limit` default 50. `--depth` comment tree.
- `subreddit` — name without `r/`. `--sort` `hot|new|top|rising|controversial` (default `hot`). `--time` same window as search (for `top`/`controversial`). `--limit` default 25.

```bash
research-cli reddit search "CRISPR neurons" --sort top --time week --limit 10
research-cli reddit search "async rust" --subreddit rust
research-cli reddit thread abc123 --sort top --limit 50
research-cli reddit thread https://www.reddit.com/r/python/comments/abc123/title/
research-cli reddit subreddit rust --sort top --time week --limit 25
```

### sploitus

Exploit/hacktool index. No key. `search` then `exploit` for the full PoC (CVSS, EPSS, entry, tags, related).

- `search` — `--type` `exploits|tools` (default `exploits`). `--sort` `default|relevance|date|score|cvss`. `--limit` default 10 (server pages 10). `--offset`. `--source` inlines PoC bodies (large).
- `exploit` — id (`EDB-ID:50592`) or `https://sploitus.com/exploit?id=...`.
- `cve` — `CVE-YYYY-NNNNN`. `--limit` default 100.
- `product` — name or `/product/slug`. `--limit` default 50 (pages of 50).
- `latest` — newest. `--limit` default 50.
- `home` — trending/popular widgets.
- `autocomplete` — typeahead.

```bash
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
```

### exploitdb

OffSec Exploit Database. No key. `search` then `exploit` / `raw` for the PoC. `download` writes the file (exploit, paper PDF, shellcode, or attached app).

- `search` — `--type` `dos|local|remote|shellcode|papers|webapps|hardware`. `--platform` slug (`java`, `php`, `windows`, …). `--port`. `--cve` `CVE-YYYY-NNNNN` or `YYYY-NNNNN`. `--text` full-text. `--author`. `--tag`. `--verified`. `--hasapp`. `--nomsf`. `--limit` default 15. `--offset`.
- `latest` — homepage table. `--limit` / `--offset`.
- `exploit` / `raw` / `download` — EDB id. `download --output` file or directory (default cwd, name from `Content-Disposition`).
- `papers` / `paper` — papers table vs hub `/docs/{id}`. `papers` takes optional query, `--language`, `--platform`, `--author`, `--limit`/`--offset`.
- `shellcodes` / `shellcode` — same pattern for `/shellcodes`.
- `ghdb` — Google dorks. `--category` id `1`–`14` or title. `dork` is one GHDB id.
- `authors` — name fragment or numeric id.
- `stats` — counts.

```bash
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
```

### malpedia

Malware catalog (guest, no key). `search` then `family` / `yara` / `actor`. Sample zip is invite-only and **not** on the CLI. Bulk dumps: `--output` and `--timeout 180`.

- `search` — name fragment (`emotet`, `apt28`).
- `family` — id `win.emotet` (uuid, library_entries, urls).
- `actor` — id `apt28`.
- `yara` — guest TLP white for a family. `--zip` writes the family rule zip; `--output` file or directory.
- `families` / `actors` — ids; `--limit`; `--full` dumps every record (multi-MB); `--output`.
- `bib` — full library (~6.7MB) or `--family` / `--actor` (mutually exclusive). `--output` writes `.bib`.
- `misp` — galaxy cluster (~4MB). `--output`.
- `references` — URL → family/actor map (~4.7MB). `--url` filters one reference.
- `yara-list` — guest rule index; `--family` optional.
- `yara-dump` — **requires** `--tlp white|green|amber` **or** `--auto`. `--zip` for the bundle. `--output`.
- `yara-after` — `YYYY-MM-DD` incremental JSON. `--output`.
- `version` — catalog version.

```bash
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

### x

Logged-in X web GraphQL. Needs `X_AUTH_TOKEN` and `X_CT0` (browser `auth_token` + `ct0`). Guest search does not work. Dead cookies exit 2. Do not invent `x-client-transaction-id`.

- `search` — `--product` `latest|top|people|media` (default `latest`). For news / “what’s going on”, `--product top`. `--count` default 20. `--cursor` pages. `from:user` operators work in the query.
- `thread` — tweet id or `https://x.com/{user}/status/{id}` (twitter.com URLs work). `--cursor` pages.

`--compact` minifies JSON (still valid). `--fields` comma list of result keys (`id,url,text,user,likes`, plus `urls`, `media`, `views`, `in_reply_to`, `retweet` when present).

```bash
research-cli x search "VMProtect LLVM" --product latest --count 20
research-cli x search "breaking news" --product top --count 20
research-cli x search "QUERY" --compact --fields id,url,text,user,likes
research-cli x thread 2069347283918000383
research-cli x thread https://x.com/user/status/2069347283918000383
research-cli x thread 2069347283918000383 --compact --fields id,url,text
```

### tgstat

Public Telegram **post search** via the logged-in **Premium-search website** (not Search API). Needs `TGSTAT_IDR` (cookie `tgstat_idrk`) and `TGSTAT_SIRK` (cookie `tgstat_sirk`) from tgstat.com — HttpOnly; copy from the browser Application cookies, same idea as X. Optional `TGSTAT_CSRK` / `TGSTAT_SETTINGS`. CSRF is fetched from `GET /search` each search. Dead/expired cookies exit 2. Skip if unset.

This is the internet-wide Telegram search. Do **not** use `telegram search` / `telegram posts` (those commands do not exist). Do not buy or call the Search API. Website UI defaults to 7 days; the CLI omits dates unless `--start`/`--end` so the archive is used. Hard cap **1000 posts per query** (20/page). Query count is unlimited on Premium-search.

Shared search filters (search / sources / mentions / export): `--peer-type` `all|channel|chat` (default `all`). `--start` / `--end` `YYYY-MM-DD` or `DD.MM.YYYY`. `--sort` `date|views` (default `date`). `--country` `--language` `--category` slugs (`tgstat catalogs`). `--minus-words`. `--views-range` `all|lt1000|1k-10k|10k` (default `all`). `--channel-id` TGStat numeric id from `sources`. `--source-sort` `members|freq` (default `members`). `--forwards` `all|hide|only` (default `all`; `--hide-forwards` is `hide`). `--hide-deleted` `--strong` `--extended` `--only-mentioned`.

Agent loop for Telegram files: `tgstat search` (prefer `--peer-type channel`) → keep hits whose `telegram.has_media` is true and `telegram.private` is false → `tgstat download` **only** `telegram.target`. Do **not** invent `telegram search`. Do **not** join chats. Private joinchat hits are omitted unless `--private`. Link-preview cards are not files; Telegram `get`/`download` is the source of truth (`document|photo|video`, plus mime/name/size).

- `search` — `POST /search/list`. `--limit` default 20 (cap 1000). `--offset`. `--download DIR` inspects via Telegram and saves real files. `--media` `document|photo|video`. `--allow-large` keeps files over 25MB. `--jobs` default 4. `--private` includes joinchat hits. Each hit has `telegram.target` (the only download argument), `telegram.has_media`, `telegram.private`.
- `sources` — mentioning channels (`id`, `title`, `members`, `freq`) for `--channel-id`.
- `mentions` — mentions/reach chart. `--group` `day|month` (default `day`).
- `export` — xlsx of hits. `--output` file or directory. Use `--timeout 180` for large queries.
- `catalogs` — country / language / category / filter value lists. No cookies.
- `me` — cookie probe. Expired session: recopy `tgstat_idrk` / `tgstat_sirk`.
- `download` — Telegram user session fetches the file for `telegram.target`. Public `@channel`: no join. Private: already a member only. CLI does not join.

```bash
research-cli tgstat search "llvm obfuscation" --limit 20
research-cli tgstat search "QUERY" --peer-type channel --sort views --views-range 1k-10k --forwards hide
research-cli tgstat search "QUERY" --download /tmp --media document --allow-large
research-cli tgstat sources "QUERY"
research-cli tgstat mentions "QUERY" --group month
research-cli tgstat export "QUERY" --output /tmp
research-cli tgstat catalogs
research-cli tgstat me
research-cli tgstat download https://t.me/durov/1 --output /tmp
research-cli tgstat download https://t.me/joinchat/AbCdefgh/12 --output /tmp
```

### telegram

Logged-in **user** MTProto via Telethon. **Not** Bot API / BotFather. **Not** public post search — that is `tgstat`. `login` is **once**. It writes `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION` to `~/.config/research-cli/env` and a durable `telegram.session` next to that file. Live calls use an in-memory copy so `discover` / `history` / `download` can run in **parallel**. Every later command reuses that session — no phone, no code. Lasts until you revoke the device in Telegram (Settings → Devices). Copy the env file **and** `telegram.session` to a server. No Telegram app at runtime. Dead/revoked session exit 2. Skip if unset. Optional `TELEGRAM_SESSION_FILE` overrides the sqlite path.

- `login` — `--api-id` and `--api-hash` from https://my.telegram.org/apps. `--phone +country…` then `telegram login --code CODE`. 2FA: `--password`. `--no-write-env` skips saving. Never commit the env or `.session` file.
- `me` — current user for the session.
- `discover` — `contacts.search` public users/groups/channels by name (no join). `--limit` default 20.
- `history` — messages from a public `@username` / `t.me/user` (often works without membership). `--search` runs `messages.search` in that chat. `--limit` default 50. `--offset-id` / `--min-id`. `t.me/user/id` uses that id as `--offset-id`. Invite links are not history; use `resolve`.
- `resolve` — `@username` / `t.me/user`, or peek `t.me/+invite` / `t.me/joinchat/…` without joining. Invite JSON `status` is `already_member`, `request_needed`, `preview`, `peek`, or `expired`. CLI does not join.
- `get` — one message body (text + Telegram media classification). Use this for text posts (`has_media` false). Same targets as download.
- `download` — one message's **file** (`document|photo|video`). Link-preview `web_page` is not a file (`no media`). Same `telegram.target` as `tgstat download`. Prefer `tgstat download` after a search hit.

```bash
research-cli telegram login --api-id 123456 --api-hash HASH --phone +15551234567
research-cli telegram login --code 12345
research-cli telegram me
research-cli telegram discover "reverse engineering"
research-cli telegram history @durov --limit 20
research-cli telegram resolve durov
research-cli telegram resolve https://t.me/joinchat/AbCdefgh
research-cli telegram get https://t.me/durov/1
research-cli telegram download https://t.me/durov/1 --output /tmp
research-cli telegram download https://t.me/joinchat/AbCdefgh/12 --output /tmp
```
