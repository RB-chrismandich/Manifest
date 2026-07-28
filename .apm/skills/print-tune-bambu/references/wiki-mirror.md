# The local Bambu wiki mirror

`scripts/wiki_sync.py` maintains a Markdown mirror of wiki.bambulab.com so the
skill can quote Bambu's own documentation instead of paraphrasing it from memory,
and so a RAG index has something stable to point at.

## What the GraphQL endpoint actually gives you

wiki.bambulab.com runs **Wiki.js**, which exposes Apollo GraphQL at
`https://wiki.bambulab.com/graphql`. Anonymous access is partial, and knowing
exactly where the line falls is what makes the sync cheap:

| Query | Anonymous | Use |
|---|---|---|
| `pages.list(locale)` | **works** | The manifest: `id`, `path`, `title`, `description`, `updatedAt`, `contentType` for ~2500 English pages in one request |
| `pages.search(query, locale)` | **works** | Live search index; returns paths, not content |
| `pages.single(id)` | denied — `PageViewForbidden 6013` | — |
| `pages.singleByPath(path, locale)` | denied — `PageViewForbidden 6013` | — |
| `__schema` introspection | disabled by Apollo | — |

So GraphQL answers *what exists and when it changed*, but never *what it says*.
Content has to come from the public HTML at `https://wiki.bambulab.com/en/<path>`.
That split is why the tool is a hybrid rather than a pure GraphQL client — and
why staleness checking is nearly free while content sync is the expensive part.

`robots.txt` is empty, so nothing is disallowed. Be polite anyway: the defaults
are 4 concurrent fetches with a 0.25 s delay, and a full-scope sync is a few
hundred requests, run rarely.

## Staleness

`updatedAt` from the manifest is compared against the `updatedAt` recorded in
`index.json` when the page was last fetched. A page is stale if it is new, if the
timestamp moved, or if its file went missing. Nothing else is refetched, so a
routine `sync` after the first one costs a handful of requests.

```bash
python3 wiki_sync.py status          # one GraphQL request, no page fetches
python3 wiki_sync.py sync            # fetch only the stale ones
python3 wiki_sync.py sync --dry-run  # list what would be fetched
```

A page the wiki lists but refuses to serve anonymously (currently one HMS error
page returns HTTP 403) is recorded as failed and then skipped, so a routine sync
still exits 0. `--retry-failed` re-attempts them. The point is that a non-zero
exit keeps meaning "something new broke".

`status` also reports pages that exist locally but have disappeared from the
wiki. They are left in place rather than deleted — losing a page that was merely
renamed is worse than carrying a stale one, and the report makes the situation
visible either way.

## Layout

```
$BAMBU_WIKI_DIR            (default ~/.cache/bambu-wiki)
├── index.json             path -> {id, title, updatedAt, sha256, bytes, fetchedAt}
└── pages/
    └── software/bambu-studio/layer-height.md
```

Each file carries YAML front matter — `title`, `path`, `url`, `wiki_id`,
`updated_at`, `description`, `source` — followed by the article as Markdown.
Front matter is there so a retrieved chunk can cite its source URL and its age,
which is the difference between a citation and an assertion.

Only the article body is mirrored. Wiki.js server-renders it inside
`<template slot="contents">`, which is the extraction anchor; page chrome and
navigation are dropped. Mirroring navigation would put the same sidebar text in
every document and make a vector index retrieve on it.

## Scope

Default sections are the ones that answer settings questions:
`software`, `bambu-studio`, `knowledge-sharing`, `filament`, `filament-acc`,
`h2`, `h2d`, `h2d-pro`, `general`, `ams*`, `parts-acc`, `studio-handy`, `miniwiki` — about 1000 of ~2500 English pages, roughly 10 MB. The remainder is
largely per-model packing, teardown, and replacement guides that add bulk to a
RAG index without improving settings answers.

Note that the wiki's top-level namespace is untidy: Bambu Studio material lives
under both `software/` and `bambu-studio/`, and filament guides under both
`filament/` and `filament-acc/`. If a `search` hit comes back without the `*`
that marks a local copy, the section is missing from your scope — that is the
signal to widen it, and it is worth checking rather than assuming coverage.

```bash
python3 wiki_sync.py sync --section x1,p1     # other printers
python3 wiki_sync.py sync --all-sections      # everything
python3 wiki_sync.py --locale zh status       # other locales exist
```

## HMS error-code lookup

The wiki carries ~930 HMS pages, and formats the code four different ways: page
paths use `_` or `-`, upper or lower hex, and live under `hmscode/`, `HMS/`, or
plain `troubleshooting/` depending on the printer. The page title adds an
`HMS_` prefix. The printer screen shows it differently again.

```bash
python3 wiki_sync.py hms HMS_0300_9500_0001_0005 --show
python3 wiki_sync.py hms 0300-9500              # partial prefix is fine
python3 wiki_sync.py hms 0300_1800 --printer a1 # rank another model first
```

Lookup normalizes both sides to hex digits only, accepts a prefix, and ranks the
H2D family first by default — the same code is documented per model and the
troubleshooting steps genuinely differ with the hardware. Codes outside the sync
scope are not local; the command says so and suggests `--all-sections`.

## Images

Off by default, and the reason is cost rather than principle.

```bash
python3 wiki_sync.py sync --section software,bambu-studio,knowledge-sharing --images
```

Measured: mirroring figures for the **whole** wiki runs to **~5.4 GB**, because
maintenance and teardown pages carry full-resolution photos and 20–30 MB animated
GIFs. Restricted to the sections that answer settings questions (software,
bambu-studio, knowledge-sharing, filament, filament-acc — 343 pages) it is about
750 MB at a 1 MB cap, **395 MB at the 500 KB default**, or 130 MB at 200 KB.
Median figure is 170 KB.

The figures worth having are the Bambu Studio UI screenshots — articles routinely
say "set it here" beside one, so the image carries the location and the prose does
not. Those sit well under the default cap. Anything larger keeps its remote URL
rather than being dropped, so nothing is lost, only deferred to the network.

Assets are content-addressed under `assets/` by a hash of the source URL, so
pages sharing a figure share one file and re-syncing an unchanged image is free.
Turning `--images` on later re-fetches already-mirrored pages, since only the
local rendering changed and `updatedAt` cannot express that.

## Keeping it fresh

**Primary mechanism: a hook tied to actual use.** A `PreToolUse` hook on the
`Skill` tool in `~/.claude/settings.json` runs `autorefresh` whenever
print-tune-bambu is invoked:

```json
{ "matcher": "Skill",
  "hooks": [{ "type": "command", "timeout": 20,
              "statusMessage": "Checking Bambu wiki mirror",
              "command": "jq -e -r \"select(.tool_input.skill == \\\"print-tune-bambu\\\")\" >/dev/null 2>&1 && python3 ~/.claude/skills/print-tune-bambu/scripts/wiki_sync.py autorefresh 2>/dev/null || true" }] }
```

This is better than a timer because it refreshes exactly when freshness could
matter and never when it cannot. Three properties make it safe to sit in front of
every invocation:

- **Nearly free.** A `.last-check` timestamp short-circuits all but the first run
  per interval — ~0.1 s. When it does check, one GraphQL request, ~0.5 s.
- **Never blocks.** If pages are stale the sync is spawned detached
  (`start_new_session`) and the hook returns immediately.
- **Never fails the tool call.** Offline, DNS failure, unreachable wiki — all
  caught and reported as context. `|| true` is the last line of defence.

It reports through `hookSpecificOutput.additionalContext`, so the model is *told*
a refresh is in flight and that this turn's mirror is one sync behind. A silent
refresh would be worse than none: the model would quote stale text believing it
current.

```bash
python3 wiki_sync.py autorefresh --force          # ignore the throttle
python3 wiki_sync.py autorefresh --no-background  # report only, do not sync
python3 wiki_sync.py autorefresh --interval 3600  # check hourly instead of daily
```

**Alternative: a launchd timer.** Still available for refreshing regardless of
use — worth it only if something other than this skill consumes the mirror (a
vector index, a filesystem MCP server).

```bash
python3 wiki_sync.py agent install     # weekly, Tue 09:41
python3 wiki_sync.py agent status      # loaded? what did the last run say?
python3 wiki_sync.py agent install --print-only   # inspect the plist first
python3 wiki_sync.py agent uninstall
```

Neither path passes `--images`; add it to the plist or run a manual sync.

## Consuming it

- **Directly:** `grep` and `show` are usually enough, and are exact rather than
  approximate.
- **Filesystem MCP server:** point it at `~/.cache/bambu-wiki/pages`.
- **Vector store:** load `pages/**/*.md`, chunk on headings, and carry the front
  matter into metadata so retrieved chunks keep their URL and `updated_at`.
- **Freshness in a pipeline:** `status` exits 0 either way and prints counts;
  `sync` exits non-zero if any page failed, so it is safe to gate on.

## Limits worth knowing

- Images are linked, not downloaded. Several wiki figures carry information the
  surrounding text does not, so a mirrored page can be less complete than the
  live one.
- Some articles are `contentType: html` rather than `markdown`; conversion is
  best-effort and those can come out less tidy.
- A page whose HTML lacks the expected container is reported as a failure rather
  than written empty — an empty file in a RAG corpus is worse than a missing one,
  because it retrieves and says nothing.
