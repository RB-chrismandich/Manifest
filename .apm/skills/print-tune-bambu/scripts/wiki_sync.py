#!/usr/bin/env python3
"""Keep a local Markdown mirror of the Bambu Lab wiki, refreshed only when stale.

The wiki runs Wiki.js, whose GraphQL endpoint answers `pages.list` without
authentication and includes each page's `updatedAt`. That is the whole staleness
story in one cheap request: ~2500 rows, no crawling, no HTML parsing, no guessing
which pages changed.

Content is a different matter. `pages.single` and `pages.singleByPath` both return
`PageViewForbidden 6013` for anonymous callers, so the rendered article has to come
from the public HTML page. So this is a hybrid by necessity, not by preference:
GraphQL decides *what* to fetch, HTTP+HTML provides the *content*.

Commands
    status                 Compare the remote manifest against the local mirror
    sync                   Fetch pages that are new or changed since last sync
    search QUERY           Query the live wiki search index (GraphQL)
    grep PATTERN           Search the local mirror
    show PATH              Print one local page
    paths [PATTERN]        List mirrored page paths
    hms CODE               Look up an HMS printer error code
    autorefresh            Throttled staleness check for use from a hook
    agent install|status|uninstall
                           Manage a launchd job that refreshes the mirror weekly

Mirror lives in $BAMBU_WIKI_DIR, default ~/.cache/bambu-wiki, as
`pages/<path>.md` with YAML front matter plus `index.json`. That layout is
directly consumable by a filesystem MCP server or any vector-store loader.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn

BASE = "https://wiki.bambulab.com"
GRAPHQL = f"{BASE}/graphql"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
DEFAULT_DIR = Path(os.environ.get("BAMBU_WIKI_DIR", "~/.cache/bambu-wiki")).expanduser()

# Sections worth mirroring for print-settings work. The wiki also carries several
# hundred pages of packing guides and per-model teardown steps that add bulk to a
# RAG index without ever answering a settings question.
DEFAULT_SECTIONS = [
    "software",  # Bambu Studio parameter documentation
    "bambu-studio",  # separate top-level section, easy to miss
    "knowledge-sharing",  # print-quality troubleshooting articles
    "filament",  # per-material usage guides
    "filament-acc",  # filament handling, drying, compatibility
    "h2d",
    "h2d-pro",
    "h2",  # H-series shared guides incl. H2D troubleshooting
    "general",
    "ams",
    "ams-2-pro",
    "ams-ht",
    "amsht",
    "ams-lite",
    "parts-acc",
    "studio-handy",
    "miniwiki",
]


def die(msg: str) -> NoReturn:  # type: ignore[valid-type]
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# transport


def _request(
    url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 60
) -> bytes:
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": UA, **(headers or {})}
    )
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            # 404 is an answer, not a transient fault — retrying it just wastes
            # the server's time and delays the rest of the sync.
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404, 410):
                raise
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def graphql(query: str, timeout: int = 90) -> dict:
    body = json.dumps({"query": query}).encode()
    raw = _request(
        GRAPHQL,
        data=body,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    doc = json.loads(raw)
    if "errors" in doc and not doc.get("data"):
        msgs = "; ".join(e.get("message", "?") for e in doc["errors"])
        die(f"GraphQL: {msgs}")
    return doc["data"]


def fetch_manifest(locale: str = "en") -> list[dict]:
    """The full page list with modification times — the staleness oracle."""
    data = graphql(
        f"query{{pages{{list(locale:{json.dumps(locale)},orderBy:PATH){{id path title description updatedAt contentType}}}}}}"
    )
    return data["pages"]["list"]


# ---------------------------------------------------------------------------
# HTML -> Markdown
#
# Wiki.js server-renders the article inside `<template slot="contents">`, which is
# a far more stable anchor than any CSS class on the page chrome. Everything
# outside it is navigation, and mirroring navigation would poison a RAG index with
# the same sidebar text on all 2500 documents.

CONTENT_RE = re.compile(r'<template\s+slot="contents"\s*>(.*?)</template>', re.S | re.I)

BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "figure",
    "figcaption",
    "blockquote",
    "hr",
    "br",
}
SKIP_TAGS = {"script", "style", "nav", "svg", "button"}


class _ToMarkdown(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.out: list[str] = []
        self.skip_depth = 0
        self.anchor_depth = 0  # Wiki.js '¶' heading permalinks — noise in a mirror
        self.pre_depth = 0
        self.list_stack: list[dict] = []
        self.link: str | None = None
        self.link_text: list[str] = []
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    # -- helpers

    def _emit(self, text: str) -> None:
        if self.cell is not None:
            self.cell.append(text)
        elif self.link is not None:
            self.link_text.append(text)
        else:
            self.out.append(text)

    def _abs(self, url: str) -> str:
        return urllib.parse.urljoin(self.page_url, url) if url else url

    # -- parser hooks

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if "toc-anchor" in classes:
            self.anchor_depth += 1
            return
        if self.anchor_depth:
            return

        if tag == "pre":
            self.pre_depth += 1
            self._emit("\n```\n")
        elif tag == "code" and not self.pre_depth:
            self._emit("`")
        elif re.fullmatch(r"h[1-6]", tag):
            self._emit(f"\n\n{'#' * int(tag[1])} ")
        elif tag in ("ul", "ol"):
            self.list_stack.append({"type": tag, "n": 0})
            self._emit("\n")
        elif tag == "li":
            if self.list_stack:
                lst = self.list_stack[-1]
                lst["n"] += 1
                indent = "  " * (len(self.list_stack) - 1)
                marker = f"{lst['n']}." if lst["type"] == "ol" else "-"
                self._emit(f"\n{indent}{marker} ")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a":
            self.link = self._abs(a.get("href", ""))
            self.link_text = []
        elif tag == "img":
            self._emit(f"![{a.get('alt', '')}]({self._abs(a.get('src', ''))})")
        elif tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br":
            self._emit("  \n")
        elif tag == "hr":
            self._emit("\n\n---\n")
        elif tag == "blockquote":
            self._emit("\n> ")
        elif tag in BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if self.anchor_depth:
            if tag == "a":
                self.anchor_depth -= 1
            return

        if tag == "pre":
            self.pre_depth = max(0, self.pre_depth - 1)
            self._emit("\n```\n")
        elif tag == "code" and not self.pre_depth:
            self._emit("`")
        elif re.fullmatch(r"h[1-6]", tag):
            self._emit("\n")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self._emit("\n")
        elif tag in ("strong", "b"):
            self._emit("**")
        elif tag in ("em", "i"):
            self._emit("*")
        elif tag == "a" and self.link is not None:
            text = "".join(self.link_text).strip()
            href, self.link = self.link, None
            self._emit(f"[{text}]({href})" if text else "")
        elif tag in ("td", "th") and self.cell is not None:
            cell = " ".join("".join(self.cell).split()).replace("|", "\\|")
            self.cell = None
            if self.row is not None:
                self.row.append(cell)
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self._emit(self._render_table(self.table))
            self.table = None
        elif tag in BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data):
        if self.skip_depth or self.anchor_depth:
            return
        if self.pre_depth:
            self._emit(data)
        elif data.strip():
            self._emit(re.sub(r"\s+", " ", data))
        elif data and not data.isspace():
            self._emit(data)
        elif self.cell is None and self.out and not self.out[-1].endswith((" ", "\n")):
            self._emit(" ")

    @staticmethod
    def _render_table(rows: list[list[str]]) -> str:
        rows = [r for r in rows if r]
        if not rows:
            return ""
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        head, *body = rows
        lines = ["| " + " | ".join(head) + " |", "|" + "---|" * width]
        lines += ["| " + " | ".join(r) + " |" for r in body]
        return "\n\n" + "\n".join(lines) + "\n\n"

    def result(self) -> str:
        text = "".join(self.out)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str, page_url: str) -> str | None:
    m = CONTENT_RE.search(html)
    if not m:
        return None
    parser = _ToMarkdown(page_url)
    parser.feed(m.group(1))
    return parser.result()


# ---------------------------------------------------------------------------
# mirror


def index_path(root: Path) -> Path:
    return root / "index.json"


def load_index(root: Path) -> dict:
    p = index_path(root)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        print(f"warning: {p} is corrupt; treating the mirror as empty", file=sys.stderr)
        return {}


def save_index(root: Path, index: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    tmp = index_path(root).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, indent=1, sort_keys=True))
    tmp.replace(index_path(root))


def page_file(root: Path, path: str) -> Path:
    # Page paths are wiki-controlled, but they still reach the filesystem, so
    # normalize away anything that could climb out of the mirror directory.
    safe = [seg for seg in path.split("/") if seg not in ("", ".", "..")]
    if not safe:
        raise ValueError(f"unusable page path: {path!r}")
    return root / "pages" / Path(*safe).with_suffix(".md")


def classify(
    remote: list[dict],
    index: dict,
    sections: list[str] | None,
    retry_failed: bool = False,
) -> dict:
    if sections:
        remote = [p for p in remote if p["path"].split("/")[0] in sections]
    wanted = {p["path"]: p for p in remote}
    new, changed, current, blocked = [], [], [], []
    for path, meta in wanted.items():
        have = index.get(path)
        if (
            have
            and have.get("failed")
            and have.get("updatedAt") == meta["updatedAt"]
            and not retry_failed
        ):
            # A page the wiki lists but will not serve anonymously (403) stays
            # broken until it changes upstream. Retrying it every sync would make
            # a non-zero exit the normal case and hide real regressions.
            blocked.append({**meta, "reason": have["failed"]})
        elif not have or have.get("failed"):
            new.append(meta)
        elif have.get("updatedAt") != meta["updatedAt"]:
            changed.append(meta)
        else:
            current.append(meta)
    removed = [p for p in index if p not in wanted]
    return {
        "new": new,
        "changed": changed,
        "current": current,
        "removed": removed,
        "blocked": blocked,
    }


IMG_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
_asset_lock = __import__("threading").Lock()


def mirror_images(
    markdown: str, root: Path, page_path: str, max_bytes: int = 500_000
) -> tuple[str, int]:
    """Download referenced images and repoint the Markdown at local copies.

    Worth doing for settings documentation specifically: many Bambu articles say
    "set it here" next to a screenshot, so the figure carries the location and the
    prose does not. A text-only mirror silently loses that.

    Scope this deliberately; the measured costs are not small. Mirroring figures
    across the whole wiki runs to ~5.4 GB, because maintenance and teardown pages
    carry full-resolution photos and 20-30 MB animated GIFs. Restricted to the
    sections that answer settings questions (software, bambu-studio,
    knowledge-sharing, filament, filament-acc — 343 pages) it is ~750 MB at a 1 MB
    cap, ~395 MB at 500 KB, ~130 MB at 200 KB. Median figure is 170 KB, and the
    Bambu Studio UI screenshots that carry the real information sit well under the
    default cap. Anything larger keeps its remote URL rather than being lost.

    Assets are keyed by a hash of the URL so pages that share a figure share one
    file, and a re-sync of an unchanged image costs nothing.
    """
    assets = root / "assets"
    page_dir = page_file(root, page_path).parent
    count = 0

    def replace(m: re.Match) -> str:
        nonlocal count
        alt, url = m.group(1), m.group(2)
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1][:6] or ".img"
        if not re.fullmatch(r"\.[A-Za-z0-9]+", ext):
            ext = ".img"
        name = hashlib.sha1(url.encode()).hexdigest()[:16] + ext
        dest = assets / name
        if not dest.is_file():
            try:
                # Non-ASCII paths are common (several figures have Chinese names)
                # and must be percent-encoded before the request.
                safe = urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")
                blob = _request(safe, timeout=45)
            except Exception:
                return m.group(0)  # keep the remote URL; a broken local link is worse
            if len(blob) > max_bytes:
                # Oversized figures are nearly always teardown photos or GIFs, whose
                # value does not scale with their size. Leave the link remote.
                return m.group(0)
            with _asset_lock:
                assets.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(blob)
        count += 1
        return f"![{alt}]({os.path.relpath(dest, page_dir)})"

    return IMG_RE.sub(replace, markdown), count


def fetch_page(
    meta: dict,
    root: Path,
    locale: str,
    delay: float,
    images: bool = False,
    max_bytes: int = 500_000,
) -> tuple[str, str | None]:
    url = f"{BASE}/{locale}/{meta['path']}"
    time.sleep(delay)
    try:
        html = _request(url).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return meta["path"], f"HTTP {exc.code}"
    except Exception as exc:  # network-level, already retried
        return meta["path"], str(exc)

    body = html_to_markdown(html, url)
    if not body:
        return meta["path"], 'no <template slot="contents"> in response'

    images_saved = 0
    if images:
        body, images_saved = mirror_images(body, root, meta["path"], max_bytes)

    front = {
        "title": meta.get("title") or meta["path"],
        "path": meta["path"],
        "url": url,
        "wiki_id": meta.get("id"),
        "updated_at": meta.get("updatedAt"),
        "description": meta.get("description") or "",
        "source": "wiki.bambulab.com",
        "local_images": images_saved,
    }
    fm = "\n".join(f"{k}: {json.dumps(v)}" for k, v in front.items())
    doc = f"---\n{fm}\n---\n\n# {front['title']}\n\n{body}\n"

    dest = page_file(root, meta["path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc, encoding="utf-8")
    return meta["path"], None


# ---------------------------------------------------------------------------
# commands


def _sections(args) -> list[str] | None:
    if args.all_sections:
        return None
    if args.section:
        return [s.strip() for s in args.section.split(",") if s.strip()]
    return DEFAULT_SECTIONS


def cmd_status(args) -> None:
    root = Path(args.dir).expanduser()
    index = load_index(root)
    remote = fetch_manifest(args.locale)
    sections = _sections(args)
    c = classify(remote, index, sections, getattr(args, "retry_failed", False))

    scope = "all sections" if sections is None else ", ".join(sections)
    print(f"mirror   : {root}")
    print(f"scope    : {scope}")
    print(
        f"remote   : {len(remote)} pages in locale {args.locale} ({len(c['new']) + len(c['changed']) + len(c['current'])} in scope)"
    )
    print(f"up to date: {len(c['current'])}")
    print(f"new       : {len(c['new'])}")
    print(f"changed   : {len(c['changed'])}")
    if c["blocked"]:
        print(
            f"unreadable   : {len(c['blocked'])} (listed by the wiki but not served anonymously)"
        )
    if c["removed"]:
        print(f"gone from wiki (still local): {len(c['removed'])}")
    stale = c["new"] + c["changed"]
    if stale:
        print("\nstale pages:")
        for m in sorted(stale, key=lambda m: m["path"])[: args.limit or 40]:
            print(f"  {m['updatedAt'][:10]}  {m['path']}")
        if args.limit and len(stale) > args.limit:
            print(f"  ... and {len(stale) - args.limit} more")
    else:
        print("\nnothing stale — mirror is current")


def cmd_sync(args) -> None:
    root = Path(args.dir).expanduser()
    index = load_index(root)
    remote = fetch_manifest(args.locale)
    sections = _sections(args)
    c = classify(remote, index, sections, args.retry_failed)

    todo = sorted(c["new"] + c["changed"], key=lambda m: m["path"])
    # A page whose file vanished is stale no matter what the index claims.
    todo += [m for m in c["current"] if not page_file(root, m["path"]).is_file()]
    if args.images:
        # Turning images on for the first time makes every already-mirrored page
        # stale in a way updatedAt cannot express, since only the local rendering
        # changed. Re-fetch the ones that still point at remote figures.
        have_local = {p for p in index if index[p].get("local_images")}
        todo += [
            m
            for m in c["current"]
            if m["path"] not in have_local
            and m["path"] not in {t["path"] for t in todo}
        ]
    if args.limit:
        todo = todo[: args.limit]

    if not todo:
        msg = (
            f"mirror is current ({len(c['current'])} pages in scope) — nothing to fetch"
        )
        if c["blocked"]:
            msg += f"; {len(c['blocked'])} unreadable page(s) skipped (--retry-failed to try again)"
        print(msg)
        return

    if args.dry_run:
        print(f"would fetch {len(todo)} page(s) into {root}:")
        for m in todo:
            print(f"  {m['path']}")
        return

    print(f"fetching {len(todo)} page(s) into {root} at concurrency {args.jobs}...")
    ok = 0
    failures: list[tuple[str, str]] = []
    by_path = {m["path"]: m for m in todo}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for path, err in pool.map(
            lambda m: fetch_page(
                m, root, args.locale, args.delay, args.images, args.image_max_bytes
            ),
            todo,
        ):
            if err:
                failures.append((path, err))
                meta = by_path[path]
                index[path] = {
                    "updatedAt": meta.get("updatedAt"),
                    "title": meta.get("title"),
                    "failed": err,
                    "failedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                continue
            meta = by_path[path]
            f = page_file(root, path)
            index[path] = {
                "id": meta.get("id"),
                "title": meta.get("title"),
                "updatedAt": meta.get("updatedAt"),
                "description": meta.get("description") or "",
                "file": str(f.relative_to(root)),
                "bytes": f.stat().st_size,
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest()[:16],
                "local_images": f.read_text(encoding="utf-8", errors="replace").count(
                    "](../"
                )
                + f.read_text(encoding="utf-8", errors="replace").count("](assets/"),
                "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            ok += 1
            if ok % 25 == 0:
                print(f"  {ok}/{len(todo)}")

    save_index(root, index)
    print(f"\nwrote {ok} page(s); mirror now holds {len(index)}")
    # Failures are reported, never swallowed: a silently short mirror looks
    # complete to whatever consumes it next, and produces confident wrong answers.
    if failures:
        print(f"{len(failures)} failed:", file=sys.stderr)
        for path, err in failures:
            print(f"  {path}: {err}", file=sys.stderr)
        sys.exit(1)


def cmd_search(args) -> None:
    data = graphql(
        f"query{{pages{{search(query:{json.dumps(args.query)},locale:{json.dumps(args.locale)}){{results{{id path title description}} totalHits}}}}}}"
    )
    res = data["pages"]["search"]
    print(f"{res.get('totalHits', 0)} hit(s)")
    root = Path(args.dir).expanduser()
    for r in res["results"][: args.limit or 20]:
        local = page_file(root, r["path"])
        mark = "*" if local.is_file() else " "
        print(f"{mark} {r['path']}\n    {r['title']}")
        if r.get("description"):
            print(f"    {r['description']}")
    print("\n('*' = present in the local mirror)")


def cmd_grep(args) -> None:
    root = Path(args.dir).expanduser()
    pages = sorted((root / "pages").rglob("*.md"))
    if not pages:
        die(f"no local mirror at {root}; run: wiki_sync.py sync")
    rx = re.compile(args.pattern, re.I)
    hits = 0
    for f in pages:
        text = f.read_text(encoding="utf-8", errors="replace")
        matched = [ln for ln in text.splitlines() if rx.search(ln)]
        if not matched:
            continue
        hits += 1
        print(f"\n{f.relative_to(root)}")
        for ln in matched[: args.context or 4]:
            print(f"    {ln.strip()[:200]}")
        if args.limit and hits >= args.limit:
            print(f"\n(stopped at {args.limit} files)")
            return
    if not hits:
        print(f"no match for {args.pattern!r} in {len(pages)} mirrored pages")


_HMS_CLEAN = re.compile(r"^(hms[_\-\s]*)?", re.I)


def normalize_hms(code: str) -> str:
    """Reduce any way a user might type an HMS code to a single canonical form.

    The wiki is inconsistent about this — page paths use `_` and `-`, upper and
    lower hex, and live under `hmscode/`, `HMS/`, or plain `troubleshooting/`
    depending on the printer. The printer itself shows the code a fourth way. So
    the only reliable match is to strip the formatting from both sides.
    """
    code = _HMS_CLEAN.sub("", code.strip())
    return re.sub(r"[^0-9a-z]", "", code.lower())


def cmd_hms(args) -> None:
    root = Path(args.dir).expanduser()
    index = load_index(root)
    if not index:
        die(f"no local mirror at {root}; run: wiki_sync.py sync")

    want = normalize_hms(args.code)
    if not want:
        die(f"{args.code!r} does not contain an HMS code")

    hits = []
    for path, meta in index.items():
        if meta.get("failed"):
            continue
        tail = normalize_hms(path.rsplit("/", 1)[-1])
        # Accept a prefix so a partial code ("0300_9500") still finds the page,
        # which is what someone reading a code off the printer screen usually has.
        if tail and (tail == want or tail.startswith(want) or want.startswith(tail)):
            hits.append((path, meta))

    if not hits:
        print(f"no mirrored HMS page for {args.code!r}")
        print(
            "The wiki carries ~930 HMS pages; only the sections in your sync scope are local."
        )
        print(
            f"Try:  wiki_sync.py sync --all-sections     or:  wiki_sync.py search {args.code!r}"
        )
        sys.exit(2)

    # Prefer the caller's printer: the same code is documented per model, and the
    # troubleshooting steps differ with the hardware.
    pref = [s.strip().lower() for s in (args.printer or "").split(",") if s.strip()]

    def rank(item):
        path = item[0].lower()
        for i, p in enumerate(pref):
            if path.startswith(p + "/") or f"/{p}/" in path:
                return (0, i)
        return (1, 0)

    hits.sort(key=rank)
    exact = [h for h in hits if normalize_hms(h[0].rsplit("/", 1)[-1]) == want]
    print(
        f"{len(hits)} page(s) for HMS {args.code}"
        + (f"  ({len(exact)} exact)" if exact else "  (prefix matches)")
    )
    for path, meta in hits[: args.limit]:
        print(f"\n  {path}\n    {meta.get('title', '')}")
    if len(hits) > args.limit:
        print(f"\n  ... and {len(hits) - args.limit} more")

    if args.show and hits:
        print("\n" + "=" * 70)
        print(page_file(root, hits[0][0]).read_text(encoding="utf-8"))


def cmd_autorefresh(args) -> None:
    """Throttled staleness check, designed to run from a PreToolUse hook.

    Three constraints shape this. It must be nearly free on a typical invocation,
    because it sits in front of every use of the skill. It must never block on a
    long sync, because the user is waiting. And it must never fail the tool call,
    because a wiki refresh is a nicety and the skill works without it.

    So: a timestamp file short-circuits all but the first run in each interval;
    the check itself is one GraphQL request; and an actual sync is spawned
    detached so the hook returns immediately. Output is the hook JSON envelope, so
    the model is told what happened rather than silently working from stale text.
    """
    root = Path(args.dir).expanduser()
    stamp = root / ".last-check"
    now = time.time()

    def emit(context: str | None = None, message: str | None = None) -> None:
        payload: dict = {"suppressOutput": True}
        if context:
            payload["hookSpecificOutput"] = {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            }
        if message:
            payload["systemMessage"] = message
        print(json.dumps(payload))
        sys.exit(0)

    if not args.force and stamp.is_file():
        age = now - stamp.stat().st_mtime
        if age < args.interval:
            emit()  # checked recently; say nothing, cost nothing

    try:
        remote = fetch_manifest(args.locale)
    except SystemExit:
        raise
    except Exception as exc:
        # Offline, DNS down, wiki unreachable: not the user's problem right now.
        emit(
            context=f"Bambu wiki mirror: staleness check skipped ({type(exc).__name__}). "
            f"The local mirror is still usable; it may be out of date."
        )

    root.mkdir(parents=True, exist_ok=True)
    stamp.touch()

    index = load_index(root)
    c = classify(remote, index, _sections(args))
    stale = c["new"] + c["changed"]

    if not index:
        emit(
            context=f"Bambu wiki mirror is EMPTY at {root}. "
            f"{len(stale)} pages are available in scope. "
            f"Run: wiki_sync.py sync   (a few minutes, one time)",
            message="Bambu wiki mirror not yet built",
        )

    if not stale:
        emit(context=f"Bambu wiki mirror is current ({len(c['current'])} pages).")

    if args.background:
        # Detached so the hook returns now. start_new_session keeps it alive past
        # the hook's own process group, which is the whole point.
        subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--dir",
                str(root),
                "sync",
                "--jobs",
                "3",
                "--delay",
                "0.3",
            ],
            stdout=(root / "sync.log").open("a"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        titles = ", ".join(m["path"] for m in stale[:5])
        emit(
            context=f"Bambu wiki mirror: {len(stale)} page(s) changed upstream "
            f"({titles}{'...' if len(stale) > 5 else ''}). A background refresh just "
            f"started; it will not be reflected in this turn. If a wiki answer matters "
            f"right now, re-read the page after the sync or cite it as possibly stale.",
            message=f"Refreshing Bambu wiki mirror ({len(stale)} pages) in background",
        )

    emit(
        context=f"Bambu wiki mirror: {len(stale)} page(s) are stale. "
        f"Run `wiki_sync.py sync` before relying on wiki content."
    )


AGENT_LABEL = "com.bambu.wiki-sync"


def agent_plist_path() -> Path:
    return Path("~/Library/LaunchAgents").expanduser() / f"{AGENT_LABEL}.plist"


def cmd_agent(args) -> None:
    """Install a launchd agent that keeps the mirror fresh unattended.

    A mirror nobody refreshes silently rots into confidently-stale answers, and
    "remember to run sync" is not a mechanism. launchd is the right layer on
    macOS: it survives reboots and Claude sessions, which an in-session scheduler
    does not.
    """
    plist = agent_plist_path()

    if args.action == "status":
        print(
            f"plist: {plist}  ({'installed' if plist.is_file() else 'not installed'})"
        )
        if plist.is_file():
            proc = subprocess.run(
                ["launchctl", "list", AGENT_LABEL], capture_output=True, text=True
            )
            print(proc.stdout.strip() or f"(not loaded: {proc.stderr.strip()})")
        log = Path(args.dir).expanduser() / "sync.log"
        if log.is_file():
            print(f"\nlast run ({log}):")
            print("  " + "\n  ".join(log.read_text().splitlines()[-8:]))
        return

    if args.action == "uninstall":
        if not plist.is_file():
            print("not installed")
            return
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink()
        print(f"removed {plist}")
        return

    root = Path(args.dir).expanduser()
    script = Path(__file__).resolve()
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script}</string>
    <string>--dir</string><string>{root}</string>
    <string>sync</string>
    <string>--jobs</string><string>2</string>
    <string>--delay</string><string>0.5</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>{args.weekday}</integer>
    <key>Hour</key><integer>{args.hour}</integer>
    <key>Minute</key><integer>{args.minute}</integer>
  </dict>
  <key>StandardOutPath</key><string>{root / "sync.log"}</string>
  <key>StandardErrorPath</key><string>{root / "sync.log"}</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
"""
    if args.print_only:
        print(body)
        print(f"# write to {plist} and: launchctl load {plist}", file=sys.stderr)
        return

    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(body)
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    proc = subprocess.run(
        ["launchctl", "load", str(plist)], capture_output=True, text=True
    )
    if proc.returncode != 0:
        die(f"wrote {plist} but launchctl load failed: {proc.stderr.strip()}")
    day = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][args.weekday % 7]
    print(
        f"installed {plist}\nruns {day} {args.hour:02d}:{args.minute:02d}, logging to {root / 'sync.log'}"
    )
    print(f"remove with: {Path(__file__).name} agent uninstall")


def cmd_show(args) -> None:
    root = Path(args.dir).expanduser()
    f = page_file(root, args.path.strip("/"))
    if not f.is_file():
        die(f"not mirrored: {args.path}  (try: wiki_sync.py search {args.path!r})")
    print(f.read_text(encoding="utf-8"))


def cmd_paths(args) -> None:
    root = Path(args.dir).expanduser()
    index = load_index(root)
    if not index:
        die(f"no local mirror at {root}; run: wiki_sync.py sync")
    rx = re.compile(args.pattern, re.I) if args.pattern else None
    for path in sorted(index):
        if index[path].get("failed"):
            continue
        if rx is None or rx.search(path):
            print(f"{index[path].get('updatedAt', '')[:10]}  {path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--dir",
        default=str(DEFAULT_DIR),
        help=f"mirror directory (default {DEFAULT_DIR})",
    )
    ap.add_argument("--locale", default="en")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def scoped(p):
        p.add_argument(
            "--section", help="comma-separated top-level sections, e.g. 'h2d,software'"
        )
        p.add_argument(
            "--all-sections", action="store_true", help="every section (~2500 pages)"
        )
        return p

    p = scoped(sub.add_parser("status"))
    p.add_argument("--limit", type=int, default=40)
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="treat previously-unreadable pages as stale",
    )

    p = scoped(sub.add_parser("sync"))
    p.add_argument("--limit", type=int, help="fetch at most N pages this run")
    p.add_argument(
        "--jobs", type=int, default=4, help="concurrent fetches (default 4; be polite)"
    )
    p.add_argument("--delay", type=float, default=0.2, help="seconds before each fetch")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--images",
        action="store_true",
        help="also download referenced figures into assets/ and relink them",
    )
    p.add_argument(
        "--image-max-bytes",
        type=int,
        default=500_000,
        help="skip figures larger than this, keeping their remote URL (default 500 KB)",
    )
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="re-attempt pages that failed before",
    )

    p = sub.add_parser("search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("grep")
    p.add_argument("pattern")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument(
        "--context", type=int, default=4, help="matching lines shown per file"
    )

    p = sub.add_parser("show")
    p.add_argument("path")

    p = sub.add_parser("paths")
    p.add_argument("pattern", nargs="?")

    p = scoped(sub.add_parser("autorefresh"))
    p.add_argument(
        "--interval",
        type=float,
        default=86400,
        help="seconds between checks; earlier calls short-circuit (default 24h)",
    )
    p.add_argument(
        "--background",
        action="store_true",
        default=True,
        help="spawn the sync detached instead of only reporting",
    )
    p.add_argument("--no-background", dest="background", action="store_false")
    p.add_argument("--force", action="store_true", help="ignore the throttle")

    p = sub.add_parser("agent")
    p.add_argument("action", choices=["install", "status", "uninstall"])
    p.add_argument(
        "--weekday", type=int, default=2, help="0=Sun .. 6=Sat (default Tue)"
    )
    p.add_argument("--hour", type=int, default=9)
    p.add_argument("--minute", type=int, default=41, help="off-the-hour by default")
    p.add_argument(
        "--print-only",
        action="store_true",
        help="print the plist instead of installing it",
    )

    p = sub.add_parser("hms")
    p.add_argument(
        "code", help="e.g. HMS_0300_9500_0001_0005, 0300-9500-0001-0005, or 0300_9500"
    )
    p.add_argument(
        "--printer",
        default="h2d,h2d-pro,h2,ams,ams-2-pro",
        help="comma-separated section prefixes to rank first (default: H2D family)",
    )
    p.add_argument("--limit", type=int, default=8)
    p.add_argument(
        "--show", action="store_true", help="print the best-matching page in full"
    )

    args = ap.parse_args()
    {
        "status": cmd_status,
        "sync": cmd_sync,
        "search": cmd_search,
        "grep": cmd_grep,
        "show": cmd_show,
        "paths": cmd_paths,
        "hms": cmd_hms,
        "agent": cmd_agent,
        "autorefresh": cmd_autorefresh,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
