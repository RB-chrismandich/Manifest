"""Local dispatch evidence for subagent_breakdown; unknown is never compliance.

Only transcript models establish what served. Native sidecars establish requests,
not resolution or authorization. Current agent files cannot prove historical pins.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import model_pricing

CHANNELS = ("agent-tool", "workflow", "fork", "teams", "external-cli", "unknown")


def parse_ts(raw: object) -> datetime | None:
    """Accept only ISO timestamps; missing timestamps do not enter a window."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def model_name(raw: object) -> str | None:
    """Restrict report labels to bounded identifiers, never arbitrary payloads."""
    if isinstance(raw, str) and re.fullmatch(
        r"[\w.:[\]/-]{1,128}", raw.strip(), re.ASCII
    ):
        return raw.strip()
    return None


def is_premium(model: str | None) -> bool | None:
    """Use the existing price table; an unpriced served model stays unknown."""
    rates = model_pricing.rates(model)
    # Same historical Sonnet input-price baseline as the original audit. This
    # is classification of recorded usage, not a runtime model selector.
    return rates[0] > 3.0 if rates else None


@dataclass
class Observation:
    """Transcript evidence, including parsing failures and out-of-window rows."""

    models: set[str] = field(default_factory=set)
    issues: Counter = field(default_factory=Counter)
    outside: int = 0


def observe(path: Path, since: datetime | None, until: datetime | None) -> Observation:
    """Read a transcript without retaining prompts, responses or tool payloads."""
    observed = Observation()
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    observed.issues["malformed-record"] += 1
                    continue
                if not isinstance(record, dict):
                    observed.issues["malformed-record"] += 1
                    continue
                if record.get("type") != "assistant":
                    continue
                stamp = parse_ts(record.get("timestamp"))
                if stamp is None:
                    observed.issues["missing-timestamp"] += 1
                    continue
                if (since and stamp < since) or (until and stamp > until):
                    observed.outside += 1
                    continue
                message = record.get("message")
                model = (
                    model_name(message.get("model"))
                    if isinstance(message, dict)
                    else None
                )
                if model:
                    observed.models.add(model)
                else:
                    observed.issues["missing-served-model"] += 1
    except OSError:
        observed.issues["unreadable-transcript"] += 1
    return observed


@dataclass
class Dispatch:
    """Allowlisted report record; resolved is unknown without native evidence."""

    dispatch_id: str
    channel: str
    agent_type: str | None
    requested: str | None
    served: list[str]
    status: str
    issues: dict[str, int]
    resolved: None = None
    resolution_source: str = "unobserved"


def matches(requested: str, served: str) -> bool:
    """Compare exact IDs or bounded Claude aliases, not price-equivalent models."""
    if requested in {"sonnet", "opus", "haiku", "fable"}:
        return served.startswith(f"claude-{requested}-")
    return requested == served


def verdict(requested: str | None, observed: Observation, channel: str) -> str:
    """Classify evidence, never infer an approval from a model choice."""
    if observed.issues or not observed.models:
        return "incomplete-evidence"
    if channel in {"fork", "unknown"}:
        return "unsupported"
    if any(is_premium(model) is None for model in observed.models):
        return "unclassified-model"
    if requested and requested != "inherit":
        return (
            "observed"
            if all(matches(requested, m) for m in observed.models)
            else "model-mismatch"
        )
    if any(is_premium(model) for model in observed.models):
        return "unattributed-premium"
    return "observed"


def collect_dispatches(
    root: str, since: datetime | None, until: datetime | None
) -> list[Dispatch]:
    """Pair both sides of the native layout, so absent sidecars remain visible."""
    base = Path(root)
    transcripts = set(base.rglob("agent-*.jsonl"))
    transcripts.update(
        p.with_name(p.name.removesuffix(".meta.json") + ".jsonl")
        for p in base.rglob("agent-*.meta.json")
    )
    rows = []
    for path in sorted(transcripts):
        observed = observe(path, since, until)
        if observed.outside and not observed.models and not observed.issues:
            continue
        meta_path = path.with_suffix(".meta.json")
        try:
            with meta_path.open(encoding="utf-8") as handle:
                meta = json.load(handle)
            if not isinstance(meta, dict):
                raise ValueError("object required")
        except (OSError, ValueError):
            meta = {}
            observed.issues["unreadable-sidecar"] += 1
        requested = model_name(meta.get("model"))
        agent_type = model_name(meta.get("agentType"))
        if meta.get("model") not in (None, "") and requested is None:
            observed.issues["invalid-requested-model"] += 1
        if meta.get("agentType") is not None and agent_type is None:
            observed.issues["invalid-agent-type"] += 1
        channel = (
            "workflow" if "workflows" in path.relative_to(base).parts else "agent-tool"
        )
        if agent_type == "fork":
            channel = "fork"
        elif "subagents" not in path.relative_to(base).parts:
            channel = "unknown"
        identity = hashlib.sha256(str(path.relative_to(base)).encode()).hexdigest()[:16]
        rows.append(
            Dispatch(
                identity,
                channel,
                agent_type,
                requested,
                sorted(observed.models),
                verdict(requested, observed, channel),
                dict(observed.issues),
            )
        )
    return rows


def audit(root: str, since: datetime | None, channel: str, options) -> int:
    """Emit bounded JSON/text coverage; exit 2 for incomplete scoped evidence."""
    rows = collect_dispatches(root, since, options.until)
    scoped = [r for r in rows if channel == "all" or r.channel == channel]
    counts = Counter(r.channel for r in rows)
    incomplete = sum(r.status != "observed" for r in scoped)
    status = "complete" if scoped and not incomplete else "incomplete"
    coverage = {
        name: {
            "observed": counts[name],
            "audited": channel == "all" or name == channel,
            "status": "unsupported"
            if name in {"teams", "external-cli", "fork", "unknown"}
            else ("observed" if counts[name] else "unobserved"),
        }
        for name in CHANNELS
    }
    payload = {
        "schema_version": 2,
        "status": status,
        "channel": channel,
        "since": since.isoformat() if since else None,
        "until": options.until.isoformat() if options.until else None,
        "dispatches": len(scoped),
        "pinned": sum(bool(r.requested) and r.channel != "fork" for r in scoped),
        "incomplete_dispatches": incomplete,
        "coverage": coverage,
        "global_coverage": "incomplete",
        "resolved_model_coverage": "unobserved",
        "records": [asdict(r) for r in scoped[: options.limit]],
        "omitted_records": max(0, len(scoped) - options.limit),
        "billing": "unknown",
        "verification_outcome": "unknown",
        "provenance": provenance(Path(options.stamp).expanduser()),
    }
    if options.json:
        from merge_mcp_defaults import write_private_json

        write_private_json(Path(options.json), payload)
    render(payload, scoped)
    return 0 if status == "complete" else 2


def provenance(stamp: Path) -> dict:
    """A deployment receipt is configuration evidence, never serving evidence."""
    result = {
        "repository_revision": None,
        "deployed_at": None,
        "host_version": None,
        "policy_sha256": None,
        "runtime_merge_status": "unobserved",
    }
    try:
        values = dict(
            line.split("=", 1) for line in stamp.read_text().splitlines() if "=" in line
        )
        revision = values.get("head_sha", "")
        if re.fullmatch(r"[0-9a-f]{40}", revision):
            result["repository_revision"] = revision
        deployed = parse_ts(values.get("deployed_at"))
        result["deployed_at"] = deployed.isoformat() if deployed else None
        with stamp.with_name("runtime_settings_merge.json").open() as handle:
            receipt = json.load(handle)
        if not isinstance(receipt, dict):
            return result
        version = receipt.get("host_version")
        if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
            result["host_version"] = version
        policy = receipt.get("policy_sha256")
        if isinstance(policy, str) and re.fullmatch(r"[0-9a-f]{64}", policy):
            result["policy_sha256"] = policy
        settings_hash = hashlib.sha256(
            (stamp.parent.parent / "settings.json").read_bytes()
        ).hexdigest()
        result["runtime_merge_status"] = (
            "merged"
            if receipt.get("status") == "merged"
            and receipt.get("settings_sha256") == settings_hash
            and values.get("runtime_merge_status") == "merged"
            else "stale"
        )
    except (OSError, ValueError):
        # Missing receipts are expected for older deployments; keep explicit unknowns.
        return result
    return result


def render(payload: dict, scoped: list[Dispatch]) -> None:
    """Render the same bounded population and totals as the JSON report."""
    status, channel, coverage = (
        payload["status"],
        payload["channel"],
        payload["coverage"],
    )
    print(f"window since={payload['since']} until={payload['until']}")
    print(f"audited channel: {channel} -> {len(scoped)} dispatch(es); status={status}")
    for name, item in coverage.items():
        scope = "AUDITED" if item["audited"] else "NOT AUDITED HERE"
        print(f"{scope} — {name}: {item['observed']} dispatch(es), {item['status']}")
    print(
        f"Unattributed premium: {sum(r.status == 'unattributed-premium' for r in scoped)}"
    )
    for row in scoped[: len(payload["records"])]:
        print(
            f"  {row.dispatch_id} {row.channel} {row.status}: requested={row.requested} served={','.join(row.served)}"
        )
    if payload["omitted_records"]:
        print(
            f"Omitted details: {payload['omitted_records']}; totals include all records."
        )
    print(
        "OK — scoped observed dispatch evidence only; other channels are not certified."
        if status == "complete"
        else "INCOMPLETE — evidence cannot certify the audited channel."
    )
