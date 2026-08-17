"""Model-chain policy and fallback continuation preparation."""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from manifest_model_policy import (
    ModelPolicyError,
    ResolvedModel,
    effective_fallback_mode,
    normalize_harness,
    parse_skill_model_policy,
    resolve_chain,
)

from . import backend, config
from .task_prompt import _build_task_extra


@dataclass(frozen=True)
class TaskModelPlan:
    """Resolved attempts and fallback behavior for one task dispatch."""

    chain: tuple[ResolvedModel, ...]
    fallback_mode: object
    pending_resume: bool

    @property
    def model_tier(self):
        return self.chain[0].model_id


def _policy_context(args, entry):
    policy_config = config.load_model_policy()
    try:
        skill_policy = (
            parse_skill_model_policy(Path(args.skill_path).resolve())
            if getattr(args, "skill_path", None)
            else None
        )
    except ModelPolicyError as error:
        return policy_config, None, None, f"delegate: invalid skill policy: {error}"
    try:
        harness = normalize_harness(entry["id"])
    except ModelPolicyError:
        harness = None
    return policy_config, skill_policy, harness, None


def _replacement_chain(args, entry, policy_config, harness, remaining):
    replacement = getattr(args, "replacement_tier", None)
    if not replacement:
        return remaining
    if harness and policy_config.get("model_tiers"):
        return resolve_chain(policy_config, harness, (replacement,))
    return (ResolvedModel(replacement, backend.map_model_tier(entry, replacement)),)


def _resolve_pending_chain(store, args, entry, resume_record, policy_config, harness):
    try:
        recorded_chain = tuple(
            ResolvedModel(item["tier"], item.get("model"))
            for item in (resume_record.get("model_chain") or [])
        )
    except (KeyError, TypeError):
        return None, "delegate: fallback_pending job has an invalid model chain"
    recovery = resume_record.get("recovery") or {}
    try:
        stored_recovery = store.read_recovery(resume_record["job_id"])
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "delegate: fallback_pending job has invalid recovery state"
    if stored_recovery != recovery or getattr(
        args, "recovery_id", None
    ) != recovery.get("recovery_id"):
        return None, "delegate: fallback_pending recovery identity does not match"
    next_index = recovery.get("next_index", 1)
    if not isinstance(next_index, int) or next_index < 1:
        return None, "delegate: fallback_pending job has invalid recovery state"
    remaining = recorded_chain[next_index:]
    return (
        _replacement_chain(args, entry, policy_config, harness, remaining),
        None,
    )


def _fresh_tiers(args, entry, user_config, skill_policy, harness):
    explicit_chain = tuple(
        item.strip()
        for item in (getattr(args, "model_chain", None) or "").split(",")
        if item.strip()
    )
    if args.model:
        return (args.model, *explicit_chain)
    if explicit_chain:
        return explicit_chain
    if skill_policy and harness and harness in skill_policy.chains:
        return skill_policy.chains[harness]
    backend_config = (user_config.get("backends") or {}).get(entry["id"], {})
    return (backend_config.get("model") or entry.get("default_tier") or "auto",)


def _resolve_fresh_chain(
    args, entry, user_config, policy_config, skill_policy, harness
):
    tiers = _fresh_tiers(args, entry, user_config, skill_policy, harness)
    if harness and policy_config.get("cli_agents") and policy_config.get("model_tiers"):
        return resolve_chain(policy_config, harness, tiers)
    return tuple(
        ResolvedModel(
            tier,
            backend.map_model_tier(entry, tier)
            if tier != "auto" or harness is None
            else None,
        )
        for tier in tiers
    )


def _fallback_mode(args, resume_record, policy_config, skill_policy, pending_resume):
    configured = policy_config.get("model_fallback", {}).get("mode")
    if pending_resume:
        requested = getattr(args, "replacement_mode", None) or (
            "auto" if getattr(args, "fallback_decision", None) == "auto" else None
        )
        return effective_fallback_mode(
            requested, resume_record.get("fallback_mode"), configured
        )
    return effective_fallback_mode(
        getattr(args, "model_fallback", None),
        skill_policy.fallback_mode if skill_policy else None,
        configured,
    )


def resolve_task_model_plan(store, args, entry, user_config, resume_record):
    """Resolve a bounded model chain without mutating pending recovery."""
    policy_config, skill_policy, harness, error = _policy_context(args, entry)
    if error:
        return None, error
    pending_resume = bool(
        resume_record is not None and resume_record.get("state") == "fallback_pending"
    )
    if pending_resume:
        chain, error = _resolve_pending_chain(
            store, args, entry, resume_record, policy_config, harness
        )
        if error:
            return None, error
    else:
        chain = _resolve_fresh_chain(
            args, entry, user_config, policy_config, skill_policy, harness
        )
    mode = _fallback_mode(
        args, resume_record, policy_config, skill_policy, pending_resume
    )
    if not chain:
        return None, (
            "delegate: no fallback attempts remain (maximum four cumulative attempts)"
        )
    return TaskModelPlan(tuple(chain), mode, pending_resume), None


def prepare_pending_resume(store, args, resume_record, plan):
    """Commit a validated fallback continuation with one versioned CAS."""
    if not plan.pending_resume:
        return resume_record, None
    decision = getattr(args, "fallback_decision", None)
    expected = getattr(args, "expected_version", None)
    if decision is None or expected is None:
        return None, (
            "delegate: fallback_pending requires --fallback-decision and "
            "--expected-version"
        )
    cumulative = len(resume_record.get("model_attempts") or []) + len(plan.chain)
    if cumulative > 4:
        return None, "delegate: fallback continuation exceeds four cumulative attempts"

    def _resume_pending(record):
        record["state"] = "fallback_prepared"
        record["fallback_pending"] = True
        record["model"] = plan.model_tier
        record["model_chain"] = [
            {"tier": item.tier, "model": item.model_id} for item in plan.chain
        ]
        record["fallback_mode"] = plan.fallback_mode.value
        record["pgid"] = None
        for key in (
            "worker_pid",
            "worker_pgid",
            "worker_start_identity",
            "foreground",
            "dispatch",
        ):
            record.pop(key, None)
        return record

    try:
        return (
            store.mutate(
                resume_record["job_id"],
                _resume_pending,
                expected_version=expected,
            ),
            None,
        )
    except ValueError as error:
        return None, f"delegate: {error}"


def build_dispatch_extra(
    args,
    entry,
    user_config,
    resume_record,
    second_opinion_record,
    plan,
    write,
):
    """Combine base metadata with the resolved fallback plan."""
    budget = backend.resolve_budget(entry, user_config, args.budget)
    extra = _build_task_extra(
        args,
        entry,
        resume_record,
        second_opinion_record,
        plan.model_tier,
        budget,
        write,
    )
    extra.update(
        {
            "model_chain": [
                {"tier": item.tier, "model": item.model_id} for item in plan.chain
            ],
            "model_attempts": (
                list(resume_record.get("model_attempts") or [])
                if plan.pending_resume
                else []
            ),
            "fallback_mode": plan.fallback_mode.value,
            "fallback_pending": False,
            "interactive_fallback": bool(
                not args.background and not getattr(args, "json", False)
            ),
            "attempt_id": uuid.uuid4().hex,
        }
    )
    if plan.pending_resume:
        resume_record.update(extra)
    return extra
