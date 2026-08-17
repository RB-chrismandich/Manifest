"""Model-aware direct skill execution and fallback transitions."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

from .controller import FallbackAction, FallbackController, FallbackDecision
from .failures import FailureEvidence, classify_failure
from .frontmatter import ModelFallbackMode, normalize_harness, parse_skill_model_policy
from .resolver import ResolvedModel, effective_fallback_mode, resolve_chain
from .skill_process import PROVIDER_OUTPUT_LIMIT, CommandResult, CommandRunner
from .skill_recovery import SkillRecoveryStore

TASK_LIMIT = 1024 * 1024


class SkillRunExecutionError(RuntimeError):
    """A provider process could not be launched or safely recovered."""


@dataclass(frozen=True)
class SkillRunReport:
    """Public direct-skill result with bounded fallback and recovery metadata."""

    harness: str
    attempts: tuple[dict[str, str | None], ...]
    final_model: str | None
    output: str
    failure: str | None
    fallback_decisions: tuple[dict[str, object], ...]
    recovery_command: str | None = None
    recovery: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        """Render the stable JSON-compatible result contract."""
        return asdict(self)


def read_task(*, stdin: bytes | None = None, task_file: Path | None = None) -> str:
    """Read one UTF-8 task from stdin or a safe regular file."""
    if stdin is not None and task_file is not None:
        raise ValueError("task stdin and --task-file are mutually exclusive")
    data = _read_task_file(task_file) if task_file is not None else stdin
    if data is None or not data or len(data) > TASK_LIMIT:
        raise ValueError("task must contain 1 byte to 1 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("task must be UTF-8") from error
    if not text.strip():
        raise ValueError("task must be non-empty")
    return text


def _read_task_file(task_file: Path) -> bytes:
    try:
        info = task_file.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError("--task-file must be a safe regular file")
        descriptor = os.open(task_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            return stream.read(TASK_LIMIT + 1)
    except OSError as error:
        raise ValueError("unable to read --task-file safely") from error


def read_task_input(stream: BinaryIO, *, task_file: Path | None = None) -> str:
    """Acquire a task once with the common one-MiB boundary."""
    data = None if task_file is not None else stream.read(TASK_LIMIT + 1)
    return read_task(stdin=data, task_file=task_file)


def resolve_skill_path(value: str | Path) -> Path:
    """Resolve a direct path or a deployed flat-skill identity."""
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    identity = str(value).partition(":")[2] or str(value)
    if not identity or any(
        char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in identity
    ):
        raise ValueError("skill must be a path or canonical deployed skill name")
    configured = os.environ.get("MANIFEST_SKILLS_ROOT")
    root = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".manifest/skills"
    )
    deployed = root / identity / "SKILL.md"
    if deployed.is_symlink() or not deployed.is_file():
        raise ValueError(f"deployed skill {identity!r} was not found")
    return deployed.resolve()


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise ValueError("skill frontmatter is unterminated")
        text = text[end + 5 :]
    return text.strip()


def _write_prompt_file(path: Path, prompt: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(prompt)
        stream.flush()
        os.fsync(stream.fileno())


def _invocation(
    agent: dict[str, Any],
    model: str | None,
    prompt: str,
    output_file: Path,
    prompt_file: Path,
) -> tuple[tuple[str, ...], bytes | None]:
    argv = [agent["binary"]]
    argv.extend(
        str(item).replace("{output_file}", str(output_file))
        for item in agent.get("base_args", ())
    )
    if model is not None:
        argv.extend(
            str(item).replace("{model}", model) for item in agent.get("model_args", ())
        )
    transport = agent.get("skill_prompt_transport", "argv")
    if transport not in {"argv", "stdin", "file"}:
        raise ValueError(f"unknown skill prompt transport {transport!r}")
    prompt_args = agent.get("skill_prompt_args")
    if prompt_args is None:
        prompt_args = agent.get("prompt_args", ("{prompt}",))
    if transport != "argv" and any("{prompt}" in str(item) for item in prompt_args):
        raise ValueError("non-argv skill prompt args cannot contain {prompt}")
    if transport == "file" and not prompt_file.exists():
        _write_prompt_file(prompt_file, prompt)
    argv.extend(
        str(item).replace("{prompt}", prompt).replace("{prompt_file}", str(prompt_file))
        for item in prompt_args
    )
    return tuple(argv), prompt.encode("utf-8") if transport == "stdin" else None


def _read_bounded_output(path: Path) -> tuple[str, bool]:
    with path.open("rb") as stream:
        data = stream.read(PROVIDER_OUTPUT_LIMIT + 1)
    return data[:PROVIDER_OUTPUT_LIMIT].decode("utf-8", errors="replace"), len(
        data
    ) > PROVIDER_OUTPUT_LIMIT


def _configured_timeout(config: dict[str, Any]) -> float:
    timeouts = config.get("timeouts") or {}
    value = timeouts.get("skill_run", timeouts.get("default", 120))
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("skill-run provider timeout must be a positive number")
    return float(value)


def _resolve_policy(
    skill_path: Path,
    harness: str,
    config: dict[str, Any],
    fallback_mode: str | ModelFallbackMode | None,
    model: str | None,
    model_chain: tuple[str, ...],
    previous_attempts: tuple[dict[str, str | None], ...],
) -> tuple[str, tuple[ResolvedModel, ...], ModelFallbackMode]:
    normalized = normalize_harness(harness)
    policy = parse_skill_model_policy(skill_path)
    tiers = policy.chains.get(normalized, ())
    if model is not None:
        tiers = (model, *model_chain)
    elif model_chain:
        tiers = model_chain
    if not tiers:
        tiers = ("auto",)
    if len(previous_attempts) + len(tiers) > 4 or len(set(tiers)) != len(tiers):
        raise ValueError("model policy permits at most four unique attempts")
    chain = resolve_chain(config, normalized, tiers)
    mode = effective_fallback_mode(
        fallback_mode,
        policy.fallback_mode,
        config.get("model_fallback", {}).get("mode"),
    )
    return normalized, chain, mode


@dataclass
class _SkillRunSession:
    skill_path: Path
    normalized: str
    chain: tuple[ResolvedModel, ...]
    mode: ModelFallbackMode
    controller: FallbackController
    agent: dict[str, Any]
    prompt: str
    runner: Any
    recovery_store: SkillRecoveryStore | None
    recovery_id: str | None
    active_version: int | None
    claimed_record: dict[str, object] | None
    claim_descriptor: int | None
    attempts: list[dict[str, str | None]]
    decisions: list[dict[str, object]]

    def run(self) -> SkillRunReport:
        with tempfile.TemporaryDirectory(prefix="manifest-skill-run-") as temporary:
            output_file = Path(temporary) / "last-message.txt"
            prompt_file = Path(temporary) / "prompt.txt"
            for index, resolved in enumerate(self.chain):
                report = self._attempt(index, resolved, output_file, prompt_file)
                if report is not None:
                    return report
        raise AssertionError("model attempt loop is unreachable")

    def _attempt(self, index, resolved, output_file, prompt_file):
        self.attempts.append({"tier": resolved.tier, "model": resolved.model_id})
        output_file.unlink(missing_ok=True)
        try:
            result = self._launch(resolved, output_file, prompt_file)
        # constitution: exempt C-ERR -- restore claims on any launcher failure.
        except Exception as error:
            self._raise_launch_error(error)
        output, truncated = self._attempt_output(result, output_file)
        if result.returncode == 0 and output.strip() and not truncated:
            return self._success_report(resolved, output)
        evidence = FailureEvidence(
            provider=self.normalized,
            harness=self.normalized,
            exit_status=result.returncode,
            stderr=result.stderr,
            truncated=truncated,
            output_envelope_status=(
                "empty" if result.returncode == 0 and not output.strip() else None
            ),
        )
        timeout_error = TimeoutError() if getattr(result, "timed_out", False) else None
        failure = classify_failure(evidence, error=timeout_error)
        decision = self.controller.decide(index, failure)
        self.decisions.append(_decision_record(decision))
        if decision.action is FallbackAction.RETRY:
            return None
        return self._failure_report(index, resolved, decision)

    def _launch(self, resolved, output_file, prompt_file):
        argv, stdin_bytes = _invocation(
            self.agent, resolved.model_id, self.prompt, output_file, prompt_file
        )
        kwargs = {"stdin_bytes": stdin_bytes} if stdin_bytes is not None else {}
        return self.runner.run(argv, **kwargs)

    @staticmethod
    def _attempt_output(result: CommandResult, output_file: Path) -> tuple[str, bool]:
        output, output_truncated = result.stdout, False
        if output_file.exists():
            output, output_truncated = _read_bounded_output(output_file)
            if not output:
                output = result.stdout
        return output, bool(getattr(result, "truncated", False)) or output_truncated

    def _success_report(self, resolved, output):
        try:
            if self.recovery_id is not None:
                if self.recovery_store is None or self.active_version is None:
                    raise ValueError("recovery store and expected version are required")
                self.recovery_store.delete(self.recovery_id, self.active_version)
        finally:
            self._release_claim()
        return SkillRunReport(
            self.normalized,
            tuple(self.attempts),
            resolved.model_id,
            output,
            None,
            tuple(self.decisions),
        )

    def _failure_report(self, index, resolved, decision):
        try:
            recovery, record = self._terminal_recovery(index, decision)
        finally:
            self._release_claim()
        return SkillRunReport(
            self.normalized,
            tuple(self.attempts),
            resolved.model_id,
            "",
            decision.failure.value,
            tuple(self.decisions),
            recovery,
            _public_recovery(record),
        )

    def _terminal_recovery(self, index, decision):
        if decision.action is FallbackAction.NEEDS_CONFIRMATION and decision.proposed:
            store = self.recovery_store or SkillRecoveryStore()
            document = {
                "skill_path": str(self.skill_path.resolve()),
                "harness": self.normalized,
                "remaining_tiers": [item.tier for item in self.chain[index + 1 :]],
                "fallback_mode": self.mode.value,
                "attempts": self.attempts,
                "requires_task_resubmission": True,
                "state": "pending",
            }
            record = self._write_recovery(store, document)
            command = (
                f"manifest skill-run {self.skill_path} --harness {self.normalized} "
                f"--recovery-id {record['recovery_id']} "
                f"--expected-version {record['version']} --fallback-decision approve"
            )
            return command, record
        if self.recovery_id is not None:
            if self.recovery_store is None or self.active_version is None:
                raise ValueError("recovery store and expected version are required")
            self.recovery_store.delete(self.recovery_id, self.active_version)
        return None, None

    def _write_recovery(self, store, document):
        if self.recovery_id is None:
            return store.create(document)
        if self.active_version is None:
            raise ValueError("expected recovery version is required")
        return store.replace(self.recovery_id, self.active_version, document)

    def _raise_launch_error(self, error):
        recovery_error = None
        try:
            if self.recovery_id and self.recovery_store and self.claimed_record:
                document = {
                    key: value
                    for key, value in self.claimed_record.items()
                    if key not in {"recovery_id", "version"}
                }
                document["state"] = "pending"
                restored = self.recovery_store.replace(
                    self.recovery_id, int(self.active_version), document
                )
                self.active_version = int(restored["version"])
        except (OSError, ValueError) as restore_error:
            recovery_error = restore_error
        finally:
            self._release_claim()
        if recovery_error is not None:
            raise SkillRunExecutionError(
                "provider launch failed and recovery restoration failed"
            ) from recovery_error
        suffix = (
            f"; recovery version {self.active_version} is pending"
            if self.recovery_id is not None
            else ""
        )
        raise SkillRunExecutionError(
            f"provider launch failed before execution{suffix}"
        ) from error

    def _release_claim(self) -> None:
        if self.claim_descriptor is not None:
            SkillRecoveryStore.release_claim(self.claim_descriptor)
            self.claim_descriptor = None


def _decision_record(decision: FallbackDecision) -> dict[str, object]:
    return {
        "action": decision.action.value,
        "failure": decision.failure.value,
        "current": decision.current.tier,
        "proposed": decision.proposed.tier if decision.proposed else None,
        "confirmed": decision.confirmed,
    }


def _public_recovery(record: dict[str, object] | None) -> dict[str, object] | None:
    if record is None:
        return None
    tiers = record["remaining_tiers"]
    return {
        "recovery_id": record["recovery_id"],
        "version": record["version"],
        "next_tier": tiers[0] if isinstance(tiers, list) and tiers else None,
        "requires_task_resubmission": True,
    }


def _claim_recovery(store, recovery_id, expected_version):
    if recovery_id is None:
        return None, None, expected_version
    if store is None or expected_version is None:
        raise ValueError("recovery store and expected version are required")
    claimed, descriptor = store.claim(recovery_id, expected_version)
    return claimed, descriptor, int(claimed["version"])


def run_skill(
    skill_path: Path,
    task: str,
    harness: str,
    *,
    config: dict[str, Any],
    fallback_mode: str | ModelFallbackMode | None = None,
    model: str | None = None,
    model_chain: tuple[str, ...] = (),
    interactive: bool = False,
    confirm_callback: Callable[[str], bool] | None = None,
    runner: Any = None,
    recovery_store: SkillRecoveryStore | None = None,
    recovery_id: str | None = None,
    expected_version: int | None = None,
    previous_attempts: tuple[dict[str, str | None], ...] = (),
) -> SkillRunReport:
    """Execute one skill through a bounded, policy-authorized model chain."""
    normalized, chain, mode = _resolve_policy(
        skill_path,
        harness,
        config,
        fallback_mode,
        model,
        model_chain,
        previous_attempts,
    )
    agent = config.get("cli_agents", {}).get(normalized)
    if not isinstance(agent, dict):
        raise ValueError(f"no native launcher is registered for {normalized}")
    claimed, descriptor, active_version = _claim_recovery(
        recovery_store, recovery_id, expected_version
    )
    session = _SkillRunSession(
        skill_path,
        normalized,
        chain,
        mode,
        FallbackController(
            chain,
            mode,
            interactive=interactive,
            confirm_callback=confirm_callback,
        ),
        agent,
        f"{_body(skill_path)}\n\nTask:\n{task}",
        runner or CommandRunner(_configured_timeout(config)),
        recovery_store,
        recovery_id,
        active_version,
        claimed,
        descriptor,
        list(previous_attempts),
        [],
    )
    return session.run()
