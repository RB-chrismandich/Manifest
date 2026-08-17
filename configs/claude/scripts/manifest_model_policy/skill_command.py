"""Shared CLI contract for direct skill execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import yaml

from .frontmatter import normalize_harness
from .skill_execution import (
    SkillRunReport,
    read_task_input,
    resolve_skill_path,
    run_skill,
)
from .skill_recovery import SkillRecoveryStore


@dataclass(frozen=True)
class SkillCommandOutcome:
    """Harness-neutral result consumed by both Manifest CLI distributions."""

    payload: dict[str, object]
    text: tuple[str, ...]
    exit_code: int


@dataclass(frozen=True)
class _PreparedResume:
    model: str | None
    model_chain: str | None
    model_fallback: str | None
    previous_attempts: tuple[dict[str, str | None], ...]
    cancellation: SkillCommandOutcome | None = None
    effective_version: int | None = None


def load_policy_config(path: Any) -> dict[str, Any]:
    """Load the shared model policy mapping from a trusted local path."""
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("model policy config must be a mapping")
    return value


def _recovered_at_version(
    store: SkillRecoveryStore, recovery_id: str, expected_version: int
) -> tuple[dict[str, Any], int]:
    """Validate the caller's version, then reset a crash-abandoned claim.

    recover_abandoned resets an abandoned claim through a versioned CAS, so it
    BUMPS the version. Comparing the caller's value against that post-reset
    number made the printed resume command fail forever after a crash -- the
    one case the reset exists to serve. Validate against what the caller could
    actually have been given, and return the version to use downstream.
    """
    current = store.read(recovery_id)
    resumable = {int(current["version"])}
    if current["state"] == "claimed":
        # The crashed claim bumped the record past the version the user was
        # shown, so that earlier value is still the legitimate handle.
        resumable.add(int(current["version"]) - 1)
    if expected_version not in resumable:
        raise ValueError(
            f"stale recovery version: expected {expected_version}, "
            f"found {current['version']}"
        )
    recovery = store.recover_abandoned(recovery_id)
    return recovery, int(recovery["version"])


def _rejected(
    store: SkillRecoveryStore,
    recovery: dict[str, Any],
    recovery_id: str,
    effective_version: int,
) -> _PreparedResume:
    """Discard a pending recovery, refusing to touch a live claim.

    store.delete is a version-only CAS: it never takes the .claim flock and
    never inspects state. recover_abandoned leaves a LIVE claim untouched
    (its flock is held), so without this guard a reject could delete the
    record out from under an in-progress run and orphan it.
    """
    if recovery["state"] != "pending":
        raise ValueError("skill-run recovery has an active claim")
    # State alone is not proof: claim() takes the .claim flock BEFORE it writes
    # state="claimed" through a different lock, so a record can read "pending"
    # while a live claimant is mid-flight. HOLD the claim lock across the
    # delete -- probing and releasing would only shrink the window, since a
    # claimant could take the lock between the probe and the delete.
    with store.holding_claim(recovery_id):
        store.delete(recovery_id, effective_version)
    payload = {
        "outcome": "cancelled",
        "recovery_id": recovery_id,
        "version": effective_version,
    }
    return _PreparedResume(
        None,
        None,
        None,
        (),
        SkillCommandOutcome(payload, ("outcome: cancelled",), 0),
        effective_version,
    )


def _prepare_resume(
    store: SkillRecoveryStore,
    resolved_skill: Path,
    harness: str,
    recovery_id: str | None,
    expected_version: int | None,
    fallback_decision: str | None,
    replacement_tier: str | None,
    replacement_mode: str | None,
    model: str | None,
    model_chain: str | None,
    model_fallback: str | None,
) -> _PreparedResume:
    if recovery_id is None:
        return _PreparedResume(model, model_chain, model_fallback, ())
    if expected_version is None or fallback_decision is None:
        raise ValueError("recovery requires --expected-version and --fallback-decision")
    recovery, effective_version = _recovered_at_version(
        store, recovery_id, expected_version
    )
    normalized = normalize_harness(harness)
    if (
        recovery["skill_path"] != str(resolved_skill)
        or recovery["harness"] != normalized
    ):
        raise ValueError("recovery does not match the requested skill/harness")
    if fallback_decision == "reject":
        return _rejected(store, recovery, recovery_id, effective_version)
    remaining = tuple(recovery["remaining_tiers"])
    if replacement_tier:
        remaining = (replacement_tier,)
    fallback = replacement_mode or (
        "auto" if fallback_decision == "auto" else recovery["fallback_mode"]
    )
    return _PreparedResume(
        None,
        ",".join(remaining),
        fallback,
        tuple(recovery["attempts"]),
        None,
        effective_version,
    )


def _render_outcome(result: SkillRunReport) -> SkillCommandOutcome:
    payload = result.to_dict()
    if result.output:
        text = (result.output,)
    else:
        lines = [f"failure: {result.failure}"]
        if result.recovery:
            lines.extend(
                (
                    f"recovery_id: {result.recovery['recovery_id']}",
                    f"version: {result.recovery['version']}",
                    f"next_tier: {result.recovery['next_tier']}",
                    f"resume: {result.recovery_command}",
                )
            )
        text = tuple(lines)
    return SkillCommandOutcome(payload, text, 1 if result.failure else 0)


def execute_skill_command(
    *,
    skill: str | Path,
    harness: str,
    task_stream: BinaryIO,
    config_path: Path,
    task_file: Path | None = None,
    model: str | None = None,
    model_chain: str | None = None,
    model_fallback: str | None = None,
    recovery_id: str | None = None,
    expected_version: int | None = None,
    fallback_decision: str | None = None,
    replacement_tier: str | None = None,
    replacement_mode: str | None = None,
    non_interactive: bool = False,
    as_json: bool = False,
    confirm_callback: Callable[[str], bool] | None = None,
) -> SkillCommandOutcome:
    """Execute the canonical skill-run command contract for either CLI."""
    resolved_skill = resolve_skill_path(skill)
    recovery_store = SkillRecoveryStore()
    prepared = _prepare_resume(
        recovery_store,
        resolved_skill,
        harness,
        recovery_id,
        expected_version,
        fallback_decision,
        replacement_tier,
        replacement_mode,
        model,
        model_chain,
        model_fallback,
    )
    if prepared.cancellation is not None:
        return prepared.cancellation
    task = read_task_input(task_stream, task_file=task_file)
    chain = tuple(
        item.strip() for item in (prepared.model_chain or "").split(",") if item.strip()
    )
    stream_is_tty = getattr(task_stream, "isatty", lambda: False)
    result = run_skill(
        resolved_skill,
        task,
        harness,
        config=load_policy_config(config_path),
        fallback_mode=prepared.model_fallback,
        model=prepared.model,
        model_chain=chain,
        interactive=not non_interactive and not as_json and bool(stream_is_tty()),
        confirm_callback=confirm_callback,
        recovery_store=recovery_store,
        recovery_id=recovery_id,
        expected_version=prepared.effective_version or expected_version,
        previous_attempts=prepared.previous_attempts,
    )
    return _render_outcome(result)
