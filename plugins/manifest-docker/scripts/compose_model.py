"""The parsed compose document, and how rules ask questions of it.

Holds the line-tracking YAML loader, the finding/context records every rule
speaks in, and the predicates rules share (is this service stateful, where did
this key come from). Knows nothing about the rules themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class MissingDependency(RuntimeError):
    """PyYAML is unavailable; the caller degrades instead of crashing."""


@dataclass
class Finding:
    """One rule violation, anchored to a source line."""

    rule_id: str
    severity: str
    service: str | None
    line: int
    message: str

    def location(self, path: Path) -> str:
        return f"{path}:{self.line}"


@dataclass
class Context:
    """Everything a rule needs, so every rule function takes one parameter."""

    path: Path
    cfg: dict[str, Any]
    doc: dict[str, Any]
    raw_lines: list[str]
    services: dict[str, Any] = field(default_factory=dict)
    ranges: dict[str, tuple[int, int]] = field(default_factory=dict)


class _LineDict(dict):
    """A mapping that remembers where it and each of its keys came from.

    ``key_lines`` is what makes precise reporting possible. Without it a
    finding about a *missing* key has nowhere to point, and one about a
    present key can only point at the block, not the offending line.
    """

    line: int = 0
    key_lines: dict[Any, int]


def load_yaml_with_lines(text: str) -> Any:
    """Parse YAML, tagging every mapping with its own and its keys' lines.

    The loader derives from ``SafeLoader`` and overrides only the mapping
    constructor, so the safe tag table is intact: ``!!python/object`` and
    friends remain unconstructable.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise MissingDependency("PyYAML is required (pip install pyyaml)") from exc

    class LineLoader(yaml.SafeLoader):
        """SafeLoader plus source-line bookkeeping. Adds no constructible tags."""

    def construct_mapping(loader: Any, node: Any) -> _LineDict:
        loader.flatten_mapping(node)
        mapping = _LineDict(loader.construct_pairs(node, deep=True))
        mapping.line = node.start_mark.line + 1
        mapping.key_lines = {
            key_node.value: key_node.start_mark.line + 1
            for key_node, _ in node.value
            if hasattr(key_node, "value")
        }
        return mapping

    LineLoader.add_constructor("tag:yaml.org,2002:map", construct_mapping)
    # safe_load cannot be used here: it gives no access to node.start_mark, and
    # every finding this tool reports is anchored to a file:line.
    # constitution: exempt C-DANGER — LineLoader subclasses SafeLoader and adds
    # no constructible tags, so !!python/object remains unconstructable.
    return yaml.load(text, Loader=LineLoader)


def build_context(path: Path, cfg: dict[str, Any], text: str) -> Context | None:
    """Parse ``text`` into a Context, or None when it is not a compose mapping."""
    doc = load_yaml_with_lines(text)
    if not isinstance(doc, dict):
        return None
    block = doc.get("services") or {}
    services = {name: body for name, body in block.items() if isinstance(body, dict)}
    raw_lines = text.splitlines()
    return Context(
        path, cfg, doc, raw_lines, services, service_ranges(raw_lines, block, services)
    )


def service_ranges(
    raw_lines: list[str], block: Any, services: dict[str, Any]
) -> dict[str, tuple[int, int]]:
    """Map each service to its (start, end) 1-based inclusive line range.

    Ranges let a bypass marker placed anywhere inside a service suppress a
    finding that has no single offending line — a missing key has no line.
    """
    headers = sorted(
        (line, name)
        for name, line in getattr(block, "key_lines", {}).items()
        if name in services
    )
    block_end = _services_block_end(raw_lines, headers)
    ranges: dict[str, tuple[int, int]] = {}
    for position, (start, name) in enumerate(headers):
        following = (
            headers[position + 1][0] - 1 if position + 1 < len(headers) else block_end
        )
        ranges[name] = (start, max(start, following))
    return ranges


def _services_block_end(raw_lines: list[str], headers: list[tuple[int, str]]) -> int:
    """Line at which the `services:` block stops (next column-0 key, or EOF)."""
    if not headers:
        return len(raw_lines)
    for index, text in enumerate(raw_lines, start=1):
        stripped = text.strip()
        if not stripped or stripped.startswith("#") or text[:1].isspace():
            continue
        if index > headers[0][0]:
            return index - 1
    return len(raw_lines)


def line_of(body: Any, key: str, fallback: int) -> int:
    """Source line of ``key`` within ``body``, or ``fallback`` when absent."""
    return getattr(body, "key_lines", {}).get(key, fallback)


def image_name(body: dict[str, Any]) -> str:
    """The service's ``image:`` value, or empty when built from source."""
    image = body.get("image")
    return image if isinstance(image, str) else ""


def mount_specs(body: dict[str, Any]) -> list[str]:
    """Volume entries rendered as ``source:target`` strings."""
    specs: list[str] = []
    for entry in body.get("volumes") or []:
        if isinstance(entry, str):
            specs.append(entry)
        elif isinstance(entry, dict):
            specs.append(f"{entry.get('source', '')}:{entry.get('target', '')}")
    return specs


def env_pairs(body: dict[str, Any]) -> list[tuple[str, Any]]:
    """Normalise ``environment`` (mapping or ``KEY=value`` list) to pairs."""
    env = body.get("environment")
    if isinstance(env, dict):
        return list(env.items())
    pairs = []
    for item in env or []:
        if isinstance(item, str) and "=" in item:
            key, _, value = item.partition("=")
            pairs.append((key, value))
    return pairs


def service_networks(body: dict[str, Any]) -> list[str]:
    """Networks the service attaches to, from either mapping or list form."""
    networks = body.get("networks")
    if isinstance(networks, dict):
        return list(networks)
    return [str(item) for item in networks or []]


def _repository(image: str) -> str:
    """Image reference with digest and tag stripped, lowercased.

    The tag is stripped from the LAST path segment only. A registry host may
    carry a port (``registry.local:5000/postgres``), and a naive rsplit on the
    whole reference eats the image path along with the port — which silently
    turned every private-registry database into a stateless service.
    """
    repository = image.split("@", 1)[0]
    head, slash, last = repository.rpartition("/")
    return f"{head}{slash}{last.rsplit(':', 1)[0]}".lower()


def is_stateful(ctx: Context, body: dict[str, Any]) -> bool:
    """True when the service holds durable state (by image family or mount)."""
    image = _repository(image_name(body))
    if image and any(family in image for family in ctx.cfg.get("stateful_images", [])):
        return True
    targets = ctx.cfg.get("stateful_mount_targets", [])
    return any(
        any(target in mount for target in targets) for mount in mount_specs(body)
    )
