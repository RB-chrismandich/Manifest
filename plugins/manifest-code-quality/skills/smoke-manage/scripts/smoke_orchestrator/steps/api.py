"""API/HTTP step runner — Playwright APIRequestContext (T016).

Receives a live ``APIRequestContext`` from the executor (created with or without
a browser). Captures use a small JSONPath subset (``$.a.b[0].c``) over the JSON
response — enough for ids/tokens/urls without taking a JSONPath dependency.
"""

from __future__ import annotations

import re

from . import CaptureError, StepOutcome, join_url

# Matches ``.key`` (incl. hyphens) or ``[<index>]`` segments of a $.a.b[0] path.
_JP_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")


def run(step: dict, *, api_ctx, base_url: str | None, timeout_ms: int) -> StepOutcome:
    method = step["method"]
    url = join_url(base_url, step["path"])
    kwargs: dict = {"timeout": timeout_ms}
    if step.get("body") is not None:
        kwargs["data"] = step["body"]  # dict -> JSON by Playwright
    try:
        resp = api_ctx.fetch(url, method=method, **kwargs)
    except Exception as exc:
        return StepOutcome(False, f"{method} {url} errored: {exc}")

    expect = step.get("expect_status")
    ok = (resp.status == expect) if expect is not None else (200 <= resp.status < 300)
    if not ok:
        body = (resp.text() or "")[:200]
        return StepOutcome(
            False, f"HTTP {resp.status} (expected {expect or '2xx'}): {body}"
        )
    return StepOutcome(True, captures=_extract(step.get("captures", {}), resp))


def _extract(captures: dict, resp) -> dict:
    if not captures:
        return {}
    try:
        data = resp.json()
    except Exception as exc:
        raise CaptureError("api response body is not valid JSON") from exc
    return {name: _jsonpath(data, jp) for name, jp in captures.items()}


def _jsonpath(data, path: str):
    if not path.startswith("$"):
        raise CaptureError(f"api capture path must start with '$': {path!r}")
    cur = data
    for m in _JP_TOKEN.finditer(path):
        key, idx = m.group(1), m.group(2)
        try:
            cur = cur[int(idx)] if idx is not None else cur[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise CaptureError(
                f"api capture: path {path!r} failed at {m.group(0)!r}"
            ) from exc
    return cur
