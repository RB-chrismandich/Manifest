"""Load and validate the adjacent JSON constitution into declared records.

CON-005 asks for a validated model at the boundary. This uses stdlib dataclasses
rather than pydantic on purpose: the pre-write hook must run under whatever bare
`python3` is on PATH, and a gate that cannot start is a gate that is not there.
Validation is therefore explicit and happens once, here.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config/code_constitution.json"
ENV_OVERRIDE = "CODE_CONSTITUTION_JSON"

_REQUIRED_TOP = ("version", "articles", "checks", "languages")


class RegistryError(Exception):
    """The registry could not be loaded or does not satisfy its own schema."""


@dataclass(frozen=True, slots=True)
class Article:
    id: str
    title: str
    rule: str
    severity: str
    checks: list[str] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    article: str
    module: str
    advisory: bool
    summary: str
    tiers: dict[str, int] = field(default_factory=dict)
    template_interpolation_ratio: float = 0.0

    def severity_for(self, span_lines: int) -> str:
        """Map a span length onto the check's configured severity tiers."""
        if not self.tiers:
            return "error"
        ranked = sorted(self.tiers.items(), key=lambda kv: kv[1], reverse=True)
        for name, floor in ranked:
            if span_lines >= floor:
                return name
        return "info"


@dataclass(frozen=True, slots=True)
class Language:
    key: str
    extensions: tuple[str, ...]
    annex: str
    thresholds: dict[str, Any]
    data_dirs: tuple[str, ...]
    toolchain: dict[str, str]

    @property
    def comment_prefix(self) -> str:
        return str(self.thresholds.get("comment_prefix", "#"))

    def threshold(self, name: str) -> int:
        """Return a ceiling, or 0 when this language has no such unit."""
        value = self.thresholds.get(name, 0)
        return int(value) if isinstance(value, int) else 0


@dataclass(frozen=True, slots=True)
class Registry:
    version: str
    articles: tuple[Article, ...]
    checks: dict[str, Check]
    languages: dict[str, Language]

    def article(self, article_id: str) -> Article:
        for article in self.articles:
            if article.id == article_id:
                return article
        raise KeyError(article_id)

    def check(self, check_id: str) -> Check:
        return self.checks[check_id]

    def language_for(self, path: Path) -> Language | None:
        suffix = path.suffix.lower()
        for language in self.languages.values():
            if suffix in language.extensions:
                return language
        return None


def load(path: Path | None = None) -> Registry:
    """Read the registry, or raise RegistryError naming the path that failed.

    Callers choose the failure posture: the CLI surfaces the error (a gate that
    silently passes is worse than one that stops), the hook swallows it (a hook
    must never break the tool it wraps).
    """
    target = Path(path or os.environ.get(ENV_OVERRIDE) or DEFAULT_PATH)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise RegistryError(f"registry not found: {target}") from err
    except OSError as err:
        raise RegistryError(f"cannot read registry {target}: {err}") from err
    except json.JSONDecodeError as err:
        raise RegistryError(f"registry {target} is not valid JSON: {err}") from err

    if not isinstance(raw, dict):
        raise RegistryError(
            f"registry {target} must be a mapping, got {type(raw).__name__}"
        )
    missing = [key for key in _REQUIRED_TOP if not raw.get(key)]
    if missing:
        raise RegistryError(
            f"registry {target} is missing required keys: {', '.join(missing)}"
        )

    try:
        return _build(raw)
    except (KeyError, TypeError, ValueError) as err:
        raise RegistryError(f"registry {target} failed validation: {err}") from err


def _build(raw: dict) -> Registry:
    articles = tuple(
        Article(
            id=item["id"],
            title=item["title"],
            rule=" ".join(item["rule"].split()),
            severity=item["severity"],
            checks=list(item.get("checks") or []),
            see_also=list(item.get("see_also") or []),
        )
        for item in raw["articles"]
    )
    checks = {
        check_id: Check(
            id=check_id,
            article=body["article"],
            module=body["module"],
            advisory=bool(body.get("advisory", False)),
            summary=body["summary"],
            tiers=dict(body.get("tiers") or {}),
            template_interpolation_ratio=float(
                body.get("template_interpolation_ratio", 0.0)
            ),
        )
        for check_id, body in raw["checks"].items()
    }
    languages = {
        key: Language(
            key=key,
            extensions=tuple(str(e).lower() for e in body["extensions"]),
            annex=body.get("annex", ""),
            thresholds=dict(body.get("thresholds") or {}),
            data_dirs=tuple(body.get("data_dirs") or ()),
            toolchain=dict(body.get("toolchain") or {}),
        )
        for key, body in raw["languages"].items()
    }

    known_articles = {a.id for a in articles}
    for check in checks.values():
        if check.article not in known_articles:
            raise ValueError(f"check {check.id} cites unknown article {check.article}")
    for article in articles:
        for check_id in article.checks:
            if check_id not in checks:
                raise ValueError(f"article {article.id} cites unknown check {check_id}")

    return Registry(
        version=str(raw["version"]),
        articles=articles,
        checks=checks,
        languages=languages,
    )
