"""Two-phase, re-entrant state machine (FR-003..FR-011; research D6).

Phase 1 (clarification gate): both critics independently interrogate the
spec+plan context; open questions park the run (exit 3) for skill-mediated
re-entry via ``answer``; the gate passes only on dual structured ``complete``.
Phase 2 (implementation loop): implementer candidate -> confinement check ->
project verification -> independent dual critic audit; staging happens only in
the implement -> success transition. Invocation order is a stable contract for
tests: qa_critic, arch_critic per round; implementer, qa_critic, arch_critic
per iteration.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from . import AbortError
from .candidate import apply_candidate, parse_candidate, serialize_candidate
from .context import resolve_context
from .gitops import preflight, repo_root_of, stage
from .invoke import invoke_role
from .persistence import RunStore, default_state_root, utcnow_iso
from .roles import load_roles
from .verdicts import parse_verdict
from .verify import run_verification


def _env(name: str, default):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return type(default)(raw)


@dataclass
class RunConfig:
    """Resolved ceilings/timeouts/flags snapshot (data-model.md RunConfig)."""

    max_rounds: int = 3
    max_iterations: int = 10
    invoke_timeout_s: float = 600.0
    run_timeout_s: float = 3600.0
    verify_cmd: str | None = None
    allow_dirty: bool = False
    cli: str = "claude"

    @classmethod
    def from_env(cls, **overrides) -> RunConfig:
        base = {
            "max_rounds": _env("CDDL_MAX_ROUNDS", cls.max_rounds),
            "max_iterations": _env("CDDL_MAX_ITERATIONS", cls.max_iterations),
            "invoke_timeout_s": _env("CDDL_INVOKE_TIMEOUT", cls.invoke_timeout_s),
            "run_timeout_s": _env("CDDL_RUN_TIMEOUT", cls.run_timeout_s),
            "cli": os.environ.get("CDDL_CLI") or cls.cli,
        }
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**base)

    def to_dict(self) -> dict:
        return {
            "max_rounds": self.max_rounds,
            "max_iterations": self.max_iterations,
            "invoke_timeout_s": self.invoke_timeout_s,
            "run_timeout_s": self.run_timeout_s,
            "verify_cmd": self.verify_cmd,
            "allow_dirty": self.allow_dirty,
            "cli": self.cli,
        }


STATUS_EXIT = {
    "success": 0,
    "questions_pending": 3,
    "gate_failure": 4,
    "ceiling_failure": 5,
    "preflight_failure": 6,
    "aborted": 7,
}

CRITIC_KEYS = ("qa_critic", "arch_critic")


@dataclass
class RunOutcome:
    status: str
    message: str
    run_id: str | None = None
    details: dict = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return STATUS_EXIT[self.status]


# --- prompt assembly (contracts/role-definition.md "Prompt assembly") --------

P1_TASK = (
    "## Your task (phase 1: clarification gate)\n\n"
    "Independently interrogate the specification and plan below for holes that "
    "would change what gets built. Do not propose or write any implementation."
)

P2_CRITIC_TASK = (
    "## Your task (phase 2: candidate audit)\n\n"
    "Independently audit the candidate change below against the specification, "
    "plan, and recorded clarifications. Judge only this iteration's candidate."
)

P2_IMPLEMENTER_TASK = (
    "## Your task (phase 2: produce the candidate)\n\n"
    "Produce the candidate change for the feature described below. Address "
    "every listed deficiency from previous iterations."
)


def _verdict_grammar(role_key: str, phase: int) -> str:
    if phase == 1:
        decisions = (
            '"complete" (no open questions remain; findings must be []) or '
            '"questions" (each open question is a finding)'
        )
    else:
        decisions = (
            '"approve" (no material defects; findings must be []) or '
            '"reject" (each deficiency is a finding)'
        )
    return (
        "## Required verdict format (mandatory)\n\n"
        "End your response with exactly one fenced block:\n\n"
        "```cddl-verdict\n"
        f'{{"role": "{role_key}", "decision": <decision>, '
        '"findings": [{"title": "...", "detail": "...", '
        '"severity": "high|medium|low"}]}\n'
        "```\n\n"
        f'Rules: decision is {decisions}; "role" must be exactly '
        f'"{role_key}"; the block must be strict JSON and must be the last '
        "fenced block in your response. A verdict quoted inside another fenced "
        "block does not count."
    )


CANDIDATE_GRAMMAR = (
    "## Required candidate format (mandatory)\n\n"
    "Express the change as one fenced block per file, with the COMPLETE new "
    "file content (full-file semantics, not a diff):\n\n"
    "```cddl-file relative/path/from/repo/root.py\n"
    "<entire file content>\n"
    "```\n\n"
    "To delete a file, use an empty-bodied block: "
    "```cddl-delete relative/path``` .\n"
    "Paths must be relative, without spaces or `..`, and must stay inside the "
    "repository (never `.git/`). Prose outside blocks is recorded as notes."
)


def _render_deficiencies(deficiencies: list[dict]) -> str:
    if not deficiencies:
        return "## Deficiencies to address\n\nNone — this is the first iteration."
    lines = ["## Deficiencies to address (full history; fix every open one)\n"]
    for d in deficiencies:
        lines.append(f"- [iteration {d['iteration']}, {d['source']}] {d['text']}")
    return "\n".join(lines)


def _render_written(written: list[str]) -> str:
    if not written:
        return ""
    return (
        "## Files this loop wrote in earlier iterations\n\n"
        + "\n".join(f"- {p}" for p in written)
        + "\n\nYour candidate is the complete intended change: re-emit any of "
        "these you still need, and remove any that are no longer needed with a "
        "cddl-delete block (leftovers are never cleaned up automatically and "
        "will fail the project verification gates if they break the build)."
    )


def _render_candidate(cand) -> str:
    parts = ["## Candidate change under audit\n"]
    if cand.notes.strip():
        parts.append(f"Implementer notes:\n{cand.notes.strip()}\n")
    for block in cand.files:
        if block.delete:
            parts.append(f"### delete: {block.path}\n")
        else:
            parts.append(f"### file: {block.path}\n\n{block.content}")
    return "\n".join(parts)


def _render_context(ctx) -> str:
    plan_section = (
        f"# Implementation plan ({ctx.plan_path})\n\n{ctx.plan_content}"
        if ctx.plan_path
        else (
            "# Implementation plan\n\nNO PLAN ARTIFACT EXISTS for this feature. "
            "Work from the specification alone; treat this absence as disclosed."
        )
    )
    return (
        f"# Feature specification ({ctx.spec_path})\n\n{ctx.spec_content}\n\n"
        f"{plan_section}\n"
    )


def _verdict_validator(
    role_key: str, phase: int, store=None, raw_rel: str | None = None
):
    """Validator for critic invocations. When a store/path is given, every
    attempt's raw output is persisted BEFORE validation, so a run aborted on a
    double parse failure still leaves the failing critic's output on disk for
    diagnosis (US4; quickstart troubleshooting)."""

    def validate(output: str) -> str | None:
        if store is not None and raw_rel:
            store.write_text(raw_rel, output)
        verdict = parse_verdict(output, role_key, phase)
        return None if verdict.parsed_ok else verdict.error

    return validate


def _check_deadline(deadline: float, where: str) -> None:
    if time.monotonic() >= deadline:
        raise AbortError(f"run wall-clock ceiling expired {where} (FR-008)")


# --- entry points -------------------------------------------------------------


def start_run(
    target,
    config: RunConfig,
    *,
    state_root=None,
    prompts_dir=None,
    runner=None,
    spec=None,
    plan=None,
    run_id=None,
) -> RunOutcome:
    """Pre-flight then phase 1 round 1; continues into phase 2 when the gate
    passes immediately. No state is mutated before pre-flight succeeds."""
    deadline = time.monotonic() + float(config.run_timeout_s)

    ctx = resolve_context(target, spec=spec, plan=plan)
    roles = load_roles(prompts_dir)
    repo_root = repo_root_of(target)
    branch = preflight(repo_root, config.allow_dirty)

    store = RunStore(
        state_root or default_state_root(), repo_root, run_id=run_id
    ).create()
    state = {
        "run_id": store.run_id,
        "repo_root": str(repo_root),
        "branch": branch,
        "created_at": utcnow_iso(),
        "finished_at": None,
        "config": config.to_dict(),
        "phase": "clarify",
        "status": "running",
        "layout_type": ctx.layout_type,
        "spec_path": ctx.spec_path,
        "plan_path": ctx.plan_path,
        "clarification_rounds": [],
        "iterations": [],
        "written_paths": [],
        "staged_paths": [],
        "staged": False,
        "report_path": str(store.run_dir / "report.md"),
    }
    store.write_text("context.md", _render_context(ctx))
    store.write_state(state)
    store.audit("run_started", status="running", branch=branch, layout=ctx.layout_type)
    return _drive(store, state, roles, config, runner, deadline)


def answer_run(
    cwd,
    run_id: str,
    answers_text: str,
    config: RunConfig,
    *,
    state_root=None,
    prompts_dir=None,
    runner=None,
) -> RunOutcome:
    """Re-entry after questions_pending (FR-003): ingest answers, next round."""
    from . import PreflightError

    repo_root = repo_root_of(cwd)
    store = RunStore.open(state_root or default_state_root(), repo_root, run_id)
    state = store.read_state()
    if state["status"] != "questions_pending":
        raise PreflightError(
            f"run {run_id} is not awaiting answers (status: {state['status']})"
        )
    if not (answers_text or "").strip():
        raise PreflightError("answers file is empty — nothing to ingest")

    # Ceilings come from the run's config snapshot; the CLI seam may refresh.
    snapshot = dict(state["config"])
    snapshot["cli"] = config.cli
    config = RunConfig(**snapshot)
    deadline = time.monotonic() + float(config.run_timeout_s)
    roles = load_roles(prompts_dir)

    round_no = len(state["clarification_rounds"])
    store.write_text(f"answers-{round_no}.md", answers_text)
    state["clarification_rounds"][-1]["answers_text"] = answers_text
    context_md = (store.run_dir / "context.md").read_text(encoding="utf-8")
    store.write_text(
        "context.md",
        context_md
        + f"\n## Operator clarification answers (round {round_no})\n\n"
        + answers_text.strip()
        + "\n",
    )
    state["status"] = "running"
    store.write_state(state)
    store.audit("answers_ingested", round=round_no)
    return _drive(store, state, roles, config, runner, deadline)


# --- state machine ------------------------------------------------------------


def _drive(store, state, roles, config, runner, deadline) -> RunOutcome:
    try:
        if state["phase"] == "clarify":
            outcome = _clarification_gate(store, state, roles, config, runner, deadline)
            if outcome is not None:
                return outcome
        return _implementation_loop(store, state, roles, config, runner, deadline)
    except AbortError as exc:
        return _finish(store, state, "aborted", str(exc))


def _clarification_gate(
    store, state, roles, config, runner, deadline
) -> RunOutcome | None:
    """Run rounds until dual complete (returns None), park, or gate failure."""
    while True:
        round_no = len(state["clarification_rounds"]) + 1
        _check_deadline(deadline, f"before clarification round {round_no}")
        rnd = _clarification_round(store, roles, config, runner, deadline, round_no)
        state["clarification_rounds"].append(rnd)
        store.write_state(state)

        if not rnd["questions"]:
            state["phase"] = "implement"
            store.write_state(state)
            store.audit("gate_passed", rounds=round_no)
            return None

        if round_no >= config.max_rounds:
            unresolved = "; ".join(q["text"] for q in rnd["questions"])
            return _finish(
                store,
                state,
                "gate_failure",
                f"clarification rounds exhausted ({config.max_rounds}) with open "
                f"questions — no code was produced. Unresolved: {unresolved}",
            )

        _write_questions_md(store, rnd)
        state["status"] = "questions_pending"
        store.write_state(state)
        store.audit("questions_pending", round=round_no, count=len(rnd["questions"]))
        return RunOutcome(
            "questions_pending",
            f"clarification questions from round {round_no} written to "
            f"{store.run_dir / 'questions.md'} — answer with: cddl_loop.py answer "
            f"--run {store.run_id} --answers-file <path>",
            run_id=store.run_id,
        )


def _clarification_round(store, roles, config, runner, deadline, round_no) -> dict:
    context_md = (store.run_dir / "context.md").read_text(encoding="utf-8")
    outputs: dict = {}
    questions: list[dict] = []
    for role_key in CRITIC_KEYS:
        role = roles[role_key]
        prompt = "\n\n".join(
            [role.prompt_body, P1_TASK, context_md, _verdict_grammar(role_key, 1)]
        )
        raw_rel = f"clarify/round-{round_no}-{role_key}.md"
        raw = invoke_role(
            role.model,
            prompt,
            config,
            runner=runner,
            deadline=deadline,
            validator=_verdict_validator(role_key, 1, store=store, raw_rel=raw_rel),
            role_name=role_key,
        )
        raw_path = store.write_text(raw_rel, raw)
        verdict = parse_verdict(raw, role_key, 1)
        verdict.raw_path = str(raw_path)
        outputs[role_key] = verdict.to_dict()
        if verdict.decision == "questions":
            for finding in verdict.findings:
                title = finding.get("title", "question")
                detail = finding.get("detail", "")
                questions.append(
                    {
                        "role_key": role_key,
                        "text": f"{title}: {detail}" if detail else title,
                    }
                )
    return {
        "round": round_no,
        "critic_outputs": outputs,
        "questions": questions,
        "answers_text": None,
    }


def _write_questions_md(store, rnd) -> None:
    lines = [
        f"# Open clarification questions (round {rnd['round']})",
        "",
        "Answer these, then re-enter the run with "
        "`cddl_loop.py answer --run <run-id> --answers-file <path>`.",
        "",
    ]
    for role_key in CRITIC_KEYS:
        role_questions = [q for q in rnd["questions"] if q["role_key"] == role_key]
        lines.append(f"## {role_key}")
        lines.append("")
        if role_questions:
            lines.extend(f"- {q['text']}" for q in role_questions)
        else:
            lines.append("- (no open questions — this critic signaled complete)")
        lines.append("")
    store.write_text("questions.md", "\n".join(lines))


def _implementation_loop(store, state, roles, config, runner, deadline) -> RunOutcome:
    repo_root = state["repo_root"]
    deficiencies: list[dict] = []
    prev_digest = None

    for n in range(1, config.max_iterations + 1):
        _check_deadline(deadline, f"before iteration {n}")
        iteration_dir = store.iteration_dir(n)
        record = {
            "n": n,
            "started_at": utcnow_iso(),
            "ended_at": None,
            "candidate": None,
            "verification": None,
            "verdicts": {},
            "deficiencies": [],
            "stalled": False,
        }
        state["iterations"].append(record)

        def add_deficiency(source: str, text: str, _n=n, _record=record) -> None:
            entry = {"source": source, "iteration": _n, "text": text}
            _record["deficiencies"].append(entry)
            deficiencies.append(entry)

        context_md = (store.run_dir / "context.md").read_text(encoding="utf-8")
        implementer = roles["implementer"]
        prompt = "\n\n".join(
            part
            for part in [
                implementer.prompt_body,
                P2_IMPLEMENTER_TASK,
                context_md,
                _render_deficiencies(deficiencies),
                _render_written(state["written_paths"]),
                CANDIDATE_GRAMMAR,
            ]
            if part
        )
        raw = invoke_role(
            implementer.model,
            prompt,
            config,
            runner=runner,
            deadline=deadline,
            role_name="implementer",
        )
        store.write_text(f"iterations/{n}/candidate.md", raw)
        cand = parse_candidate(raw, repo_root)

        if not cand.ok:
            source = (
                "no-candidate"
                if cand.deficiency.startswith("no-candidate")
                else "confinement"
            )
            store.write_text(
                f"iterations/{n}/files.json",
                json.dumps({"ok": False, "reason": cand.deficiency}, indent=2),
            )
            record["candidate"] = {"ok": False, "reason": cand.deficiency}
            add_deficiency(source, cand.deficiency)
            record["ended_at"] = utcnow_iso()
            store.write_state(state)
            store.audit("candidate_rejected", iteration=n, reason=source)
            continue

        digest = serialize_candidate(cand)
        files_meta = [
            {"path": b.path, "delete": b.delete, "bytes": len(b.content)}
            for b in cand.files
        ]
        store.write_text(
            f"iterations/{n}/files.json",
            json.dumps({"ok": True, "digest": digest, "files": files_meta}, indent=2),
        )
        record["candidate"] = {"ok": True, "digest": digest, "files": files_meta}

        if digest == prev_digest:
            # Identical candidate cannot change the previous outcome; skip
            # verification and critics, burn the iteration, flag the stall
            # (spec edge case: a stall is never reported as success).
            record["stalled"] = True
            add_deficiency(
                "stall",
                "candidate is byte-identical to the previous iteration — "
                "change something material or the ceiling will exhaust",
            )
            record["ended_at"] = utcnow_iso()
            store.write_state(state)
            store.audit("iteration_stalled", iteration=n)
            continue
        prev_digest = digest

        written = apply_candidate(cand, repo_root, backup_dir=iteration_dir / "backup")
        for path in written:
            if path not in state["written_paths"]:
                state["written_paths"].append(path)
        store.write_state(state)

        _check_deadline(deadline, f"before verification in iteration {n}")
        result = run_verification(
            repo_root,
            config.verify_cmd,
            iteration_dir / "verify.log",
            timeout=max(1.0, deadline - time.monotonic()),
        )
        record["verification"] = result.to_dict()
        if result.ran and not result.passed:
            log_tail = (iteration_dir / "verify.log").read_text(encoding="utf-8")[
                -2000:
            ]
            add_deficiency(
                "verification",
                f"project verification failed (critics were not shown this "
                f"candidate — FR-009):\n{log_tail}",
            )
            record["ended_at"] = utcnow_iso()
            store.write_state(state)
            store.audit("verification_failed", iteration=n)
            continue

        verdicts = {}
        candidate_md = _render_candidate(cand)
        for role_key in CRITIC_KEYS:
            role = roles[role_key]
            prompt = "\n\n".join(
                [
                    role.prompt_body,
                    P2_CRITIC_TASK,
                    context_md,
                    candidate_md,
                    _verdict_grammar(role_key, 2),
                ]
            )
            raw_rel = f"iterations/{n}/{role_key}.md"
            raw = invoke_role(
                role.model,
                prompt,
                config,
                runner=runner,
                deadline=deadline,
                validator=_verdict_validator(role_key, 2, store=store, raw_rel=raw_rel),
                role_name=role_key,
            )
            raw_path = store.write_text(raw_rel, raw)
            verdict = parse_verdict(raw, role_key, 2)
            verdict.raw_path = str(raw_path)
            verdicts[role_key] = verdict

        store.write_text(
            f"iterations/{n}/verdicts.json",
            json.dumps({k: v.to_dict() for k, v in verdicts.items()}, indent=2),
        )
        record["verdicts"] = {k: v.to_dict() for k, v in verdicts.items()}
        record["ended_at"] = utcnow_iso()

        if all(v.decision == "approve" for v in verdicts.values()):
            # FR-011 (staged = critic-approved): stage exactly the paths of the
            # approved candidate — never earlier iterations' leftovers, which
            # stay applied-but-unstaged (clarification Q1: no auto-revert).
            stage(repo_root, written)
            state["staged"] = True
            state["staged_paths"] = list(written)
            leftovers = [p for p in state["written_paths"] if p not in written]
            note = (
                f" ({len(leftovers)} leftover path(s) from earlier iterations "
                f"remain unstaged — see report)"
                if leftovers
                else ""
            )
            return _finish(
                store,
                state,
                "success",
                f"both critics approved iteration {n}; {len(written)} path(s) "
                f"staged on branch {state['branch']} (staged = approved; the "
                f"loop never commits){note}",
            )

        # FR-007: ALL critics' findings from this iteration feed the next one.
        for role_key, verdict in verdicts.items():
            for finding in verdict.findings:
                title = finding.get("title", "finding")
                detail = finding.get("detail", "")
                add_deficiency(role_key, f"{title}: {detail}" if detail else title)
        store.write_state(state)
        store.audit("iteration_rejected", iteration=n)

    return _finish(
        store,
        state,
        "ceiling_failure",
        f"iteration ceiling ({config.max_iterations}) exhausted without dual "
        f"approval — the last candidate remains applied but UNSTAGED; see the "
        f"report for per-critic outstanding deficiencies and discard steps",
    )


# --- finish + report (FR-010, FR-011, FR-016; report enriched per US4) --------


def _finish(store, state, status: str, message: str) -> RunOutcome:
    state["status"] = status
    state["finished_at"] = utcnow_iso()
    if status == "success":
        state["phase"] = "done"
    _write_report(store, state, message)
    store.write_state(state)
    store.audit(status, message=message[:500])
    return RunOutcome(status, message, run_id=state["run_id"])


def blocking_summary(state) -> list[dict]:
    """Per-critic outstanding deficiencies for the final iteration."""
    iterations = state.get("iterations") or []
    if not iterations:
        return []
    final = iterations[-1]
    summary = []
    for role_key in CRITIC_KEYS:
        verdict = (final.get("verdicts") or {}).get(role_key)
        if verdict and verdict.get("decision") == "approve":
            continue
        findings = (verdict or {}).get("findings") or []
        texts = [
            f"{f.get('title', 'finding')}: {f.get('detail', '')}".rstrip(": ")
            for f in findings
        ]
        if not texts:
            texts = [
                d["text"]
                for d in final.get("deficiencies", [])
                if d["source"]
                in (role_key, "verification", "confinement", "no-candidate", "stall")
            ] or ["no verdict recorded for the final iteration"]
        summary.append({"role_key": role_key, "outstanding": texts})
    return summary


def _earliest_backup(store, rel_path: str):
    """The pre-RUN image of a path = its backup from the FIRST iteration that
    touched it (later backups hold loop-written content)."""
    iterations_dir = store.run_dir / "iterations"
    if not iterations_dir.is_dir():
        return None
    for it_dir in sorted(iterations_dir.iterdir(), key=lambda p: int(p.name)):
        pre_image = it_dir / "backup" / rel_path
        if pre_image.is_file():
            return pre_image
    return None


def _write_report(store, state, message: str) -> None:
    status = state["status"]
    lines = [
        "# CDDL run report",
        "",
        f"- **Run**: `{state['run_id']}`  ",
        f"- **Repo**: `{state['repo_root']}` (branch `{state['branch']}`)  ",
        f"- **Status**: **{status}** (exit {STATUS_EXIT[status]})  ",
        f"- **Started**: {state['created_at']}  ",
        f"- **Finished**: {state['finished_at']}",
        "",
        f"{message}",
        "",
    ]

    rounds = state.get("clarification_rounds") or []
    if rounds:
        lines += [f"## Clarification gate: {len(rounds)} round(s)", ""]
        if status == "gate_failure":
            for q in rounds[-1]["questions"]:
                lines.append(f"- UNRESOLVED [{q['role_key']}] {q['text']}")
            lines.append("")

    iterations = state.get("iterations") or []
    if iterations:
        lines += [f"## Iterations: {len(iterations)}", ""]
        for it in iterations:
            verdict_bits = (
                ", ".join(
                    f"{k}={v.get('decision')}"
                    for k, v in (it.get("verdicts") or {}).items()
                )
                or "critics not reached"
            )
            stall = " [STALLED]" if it.get("stalled") else ""
            lines.append(f"- iteration {it['n']}: {verdict_bits}{stall}")
        lines.append("")

    blocking = blocking_summary(state) if status not in ("success",) else []
    if blocking and iterations:
        lines += ["## Blocking critics (final iteration)", ""]
        for entry in blocking:
            lines.append(f"### {entry['role_key']}")
            lines += [f"- {t}" for t in entry["outstanding"]]
            lines.append("")

    written = state.get("written_paths") or []
    staged_paths = state.get("staged_paths") or []
    unstaged = [p for p in written if p not in staged_paths]
    if staged_paths:
        lines += [
            "## Working-tree disposition: STAGED (critic-approved)",
            "",
            *(f"- {p}" for p in staged_paths),
            "",
        ]
    if unstaged:
        label = (
            "unstaged leftovers from earlier (rejected) iterations"
            if staged_paths
            else "UNSTAGED candidate"
        )
        restore_cmds = []
        for path in unstaged:
            pre_image = _earliest_backup(store, path)
            if pre_image is not None:
                # Restores the pre-RUN content — safe under --allow-dirty,
                # where `git checkout` would destroy uncommitted edits.
                restore_cmds.append(f"cp '{pre_image}' '{path}'")
            else:
                restore_cmds.append(f"rm -f '{path}'  # created by the loop")
        lines += [
            f"## Working-tree disposition: {label}",
            "",
            *(f"- {p}" for p in unstaged),
            "",
            "To discard these unapproved writes and restore pre-run content "
            "(the loop never reverts on its own):",
            "",
            "```bash",
            *restore_cmds,
            "```",
            "",
        ]
    if written:
        lines += [
            "Pre-write backups of every file the loop touched are kept per "
            "iteration under `iterations/<n>/backup/` (restore by copying "
            "back).",
            "",
        ]
    if not written and status != "success":
        lines += ["## Working-tree disposition: untouched", ""]

    store.write_text("report.md", "\n".join(lines))
