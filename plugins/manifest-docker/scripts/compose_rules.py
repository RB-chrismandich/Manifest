"""The ten commandment rules, one function each.

Every function takes a Context and returns Findings. Ids, severities, prose and
remedies are NOT here — they live in ``config/compose_commandments.yml``; this
module only decides whether a document violates each rule.

Adding a rule: add the YAML entry, add ``_rule_dc_nnn`` here, register it in
RULES. Retiring one: mark ``retired: true`` in the YAML and delete the function.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from compose_model import (
    Context,
    Finding,
    env_pairs,
    image_name,
    is_stateful,
    line_of,
    mount_specs,
    service_networks,
)


def _header(ctx: Context, name: str) -> int:
    """The service's own line, for findings with no offending key."""
    return ctx.ranges.get(name, (1, 1))[0]


def _rule_dc_001(ctx: Context) -> list[Finding]:
    """Explicit image version. Detect only — version-pin owns resolving the pin."""
    out = []
    for name, body in ctx.services.items():
        image = image_name(body)
        if not image or "@sha256:" in image:
            continue
        last = image.rsplit("/", 1)[-1]
        tag = last.rsplit(":", 1)[1] if ":" in last else ""
        if tag and tag != "latest":
            continue
        detail = (
            f"`{image}` is pinned to a mutable tag" if tag else f"`{image}` has no tag"
        )
        line = line_of(body, "image", _header(ctx, name))
        out.append(Finding("DC-001", "high", name, line, detail))
    return out


def _rule_dc_002(ctx: Context) -> list[Finding]:
    """No credential literals in the committed file."""
    hints = [hint.lower() for hint in ctx.cfg.get("secret_key_hints", [])]
    out = []
    for name, body in ctx.services.items():
        for key, value in env_pairs(body):
            if not isinstance(value, str) or not value or "${" in value:
                continue
            if key.upper().endswith("_FILE"):
                continue
            if not any(hint in key.lower() for hint in hints):
                continue
            block = line_of(body, "environment", _header(ctx, name))
            # Mapping form carries per-key lines; list form only has the block.
            line = line_of(body.get("environment"), key, block)
            out.append(
                Finding("DC-002", "high", name, line, f"`{key}` holds a literal value")
            )
    return out


def _rule_dc_003(ctx: Context) -> list[Finding]:
    """Healthchecks, and dependants waiting on health rather than start."""
    out: list[Finding] = []
    depended = _collect_dependency_edges(ctx, out)
    for name in sorted(depended & set(ctx.services)):
        check = ctx.services[name].get("healthcheck")
        if check and not (isinstance(check, dict) and check.get("disable")):
            continue
        # `healthcheck: {disable: true}` is worse than none: a dependant waiting
        # on `condition: service_healthy` can never be satisfied, so compose
        # blocks until it times out rather than starting degraded.
        detail = (
            "depended upon but its healthcheck is disabled"
            if check
            else "depended upon but has no healthcheck"
        )
        out.append(Finding("DC-003", "medium", name, _header(ctx, name), detail))
    return out


def _collect_dependency_edges(ctx: Context, out: list[Finding]) -> set[str]:
    """Record every depends_on edge, flagging those that cannot wait for health."""
    depended: set[str] = set()
    for name, body in ctx.services.items():
        depends = body.get("depends_on")
        line = line_of(body, "depends_on", _header(ctx, name))
        if isinstance(depends, dict):
            depended.update(depends)
            for dep, spec in depends.items():
                condition = spec.get("condition") if isinstance(spec, dict) else None
                if condition != "service_healthy":
                    out.append(
                        Finding(
                            "DC-003",
                            "medium",
                            name,
                            line,
                            f"waits on `{dep}` starting, not healthy",
                        )
                    )
        elif isinstance(depends, list):
            depended.update(str(dep) for dep in depends)
            out.append(
                Finding(
                    "DC-003",
                    "medium",
                    name,
                    line,
                    "short-form `depends_on` cannot wait for health",
                )
            )
    return depended


def _rule_dc_004(ctx: Context) -> list[Finding]:
    """CPU and memory ceilings on every service."""
    out = []
    for name, body in ctx.services.items():
        limits = ((body.get("deploy") or {}).get("resources") or {}).get("limits") or {}
        has_cpu = bool(limits.get("cpus") or body.get("cpus"))
        has_mem = bool(limits.get("memory") or body.get("mem_limit"))
        if has_cpu and has_mem:
            continue
        missing = " and ".join(
            part for part, ok in (("cpu", has_cpu), ("memory", has_mem)) if not ok
        )
        out.append(
            Finding("DC-004", "high", name, _header(ctx, name), f"no {missing} limit")
        )
    return out


def _rule_dc_005(ctx: Context) -> list[Finding]:
    """Backing services isolated from internet-facing ones."""
    networks = ctx.doc.get("networks") or {}
    internal = {
        name
        for name, spec in networks.items()
        if isinstance(spec, dict) and spec.get("internal")
    }
    exposed = _exposed_networks(ctx)
    out = []
    for name, body in ctx.services.items():
        if str(body.get("network_mode", "")).startswith("host"):
            # Host networking opts out of Docker networking entirely: the
            # container binds host interfaces directly, so `networks:` and
            # `internal: true` no longer constrain anything. Worth flagging even
            # for a lone service, unlike the default-bridge case below.
            if is_stateful(ctx, body):
                out.append(
                    Finding(
                        "DC-005",
                        "high",
                        name,
                        line_of(body, "network_mode", _header(ctx, name)),
                        "`network_mode: host` puts a stateful service on the host network",
                    )
                )
            continue
        attached = set(service_networks(body))
        if not attached and len(ctx.services) > 1:
            out.append(
                Finding(
                    "DC-005",
                    "high",
                    name,
                    _header(ctx, name),
                    "no explicit `networks:` — shares the implicit default bridge",
                )
            )
            continue
        shared = attached & exposed
        if not shared or attached <= internal or not is_stateful(ctx, body):
            continue
        line = line_of(body, "networks", _header(ctx, name))
        joined = ", ".join(sorted(shared))
        out.append(
            Finding(
                "DC-005",
                "high",
                name,
                line,
                f"stateful service shares `{joined}` with a published port",
            )
        )
    return out


def _exposed_networks(ctx: Context) -> set[str]:
    """Networks reachable from a service that publishes a host port."""
    exposed: set[str] = set()
    for body in ctx.services.values():
        if body.get("ports"):
            exposed |= set(service_networks(body)) or {"<default>"}
    return exposed


def _rule_dc_006(ctx: Context) -> list[Finding]:
    """Named volumes rather than host bind mounts for durable data."""
    declared = set(ctx.doc.get("volumes") or {})
    targets = ctx.cfg.get("stateful_mount_targets", [])
    out = []
    for name, body in ctx.services.items():
        stateful = is_stateful(ctx, body)
        for spec in mount_specs(body):
            source, _, rest = spec.partition(":")
            target = rest.split(":", 1)[0]
            if (
                not source
                or source in declared
                or not source.startswith((".", "/", "~"))
            ):
                continue
            if not stateful and not any(hint in target for hint in targets):
                continue
            line = line_of(body, "volumes", _header(ctx, name))
            out.append(
                Finding(
                    "DC-006",
                    "medium",
                    name,
                    line,
                    f"bind mount `{spec}` holds durable state",
                )
            )
    return out


def _rule_dc_007(ctx: Context) -> list[Finding]:
    """Non-root execution."""
    out = []
    for name, body in ctx.services.items():
        user = body.get("user")
        if user is not None and str(user).split(":", 1)[0] not in ("root", "0"):
            continue
        detail = (
            "runs as root"
            if user is not None
            else "no `user:` — inherits the image default, often root"
        )
        out.append(
            Finding(
                "DC-007",
                "medium",
                name,
                line_of(body, "user", _header(ctx, name)),
                detail,
            )
        )
    return out


def _rule_dc_008(ctx: Context) -> list[Finding]:
    """Bounded log output."""
    out = []
    for name, body in ctx.services.items():
        logging = body.get("logging") or {}
        if str(logging.get("driver", "json-file")) not in ("json-file", "local"):
            continue
        options = logging.get("options") or {}
        if options.get("max-size") and options.get("max-file"):
            continue
        line = line_of(body, "logging", _header(ctx, name))
        out.append(
            Finding(
                "DC-008",
                "medium",
                name,
                line,
                "log output is unbounded (no max-size/max-file)",
            )
        )
    return out


def _rule_dc_009(ctx: Context) -> list[Finding]:
    """Repetition factored into anchors.

    Anchors are expanded by the parser, so identical blocks in the tree prove
    nothing on their own — only the raw text says whether an anchor was used.
    """
    raw = "\n".join(ctx.raw_lines)
    if re.search(r"^\s*(x-[\w-]+:|<<:\s*\*)", raw, re.MULTILINE):
        return []
    counts: dict[tuple[str, str], list[str]] = {}
    for name, body in ctx.services.items():
        for key in ("logging", "deploy", "healthcheck", "restart"):
            value = body.get(key)
            if value in (None, {}, []):
                continue
            fingerprint = json.dumps(value, sort_keys=True, default=str)
            counts.setdefault((key, fingerprint), []).append(name)
    out = []
    for (key, _), owners in sorted(counts.items()):
        if len(owners) < 3:
            continue
        joined = ", ".join(owners)
        out.append(
            Finding(
                "DC-009",
                "low",
                None,
                _header(ctx, owners[0]),
                f"identical `{key}:` repeated across {joined}",
            )
        )
    return out


def _rule_dc_010(ctx: Context) -> list[Finding]:
    """Graceful shutdown for stateful services."""
    out = []
    for name, body in ctx.services.items():
        if not is_stateful(ctx, body) or body.get("stop_grace_period"):
            continue
        out.append(
            Finding(
                "DC-010",
                "medium",
                name,
                _header(ctx, name),
                "stateful service has no `stop_grace_period` (default is 10s)",
            )
        )
    return out


RULES: dict[str, Callable[[Context], list[Finding]]] = {
    "DC-001": _rule_dc_001,
    "DC-002": _rule_dc_002,
    "DC-003": _rule_dc_003,
    "DC-004": _rule_dc_004,
    "DC-005": _rule_dc_005,
    "DC-006": _rule_dc_006,
    "DC-007": _rule_dc_007,
    "DC-008": _rule_dc_008,
    "DC-009": _rule_dc_009,
    "DC-010": _rule_dc_010,
}


def run_rules(ctx: Context, only: list[str] | None = None) -> list[Finding]:
    """Run every enabled rule from the registry over one document."""
    findings: list[Finding] = []
    for rule in ctx.cfg.get("rules", []):
        rule_id: Any = rule.get("id", "")
        if rule.get("retired") or (only and rule_id not in only):
            continue
        handler = RULES.get(rule_id)
        if handler is not None:
            findings.extend(handler(ctx))
    return findings
