"""Feature-context resolution via the spec_review.sh discovery seam
(FR-001, FR-002; research D2).

The layout rules live in ONE place — spec_review.sh's resolve_artifacts()
(explicit paths win, then speckit, then superpowers). We shell out to a bash
that sources the script (its main() is BASH_SOURCE-gated) and parse the
emitted ``role<TAB>path`` lines. A ``tasks`` line is deliberately ignored:
the loop never requires a tasks artifact (FR-002).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import PreflightError

SPEC_REVIEW = Path(__file__).resolve().parent.parent / "spec_review.sh"

_REFUSAL = (
    "target matches neither supported layout "
    "(speckit: specs/<n>/spec.md [+ plan.md]; "
    "superpowers: docs/superpowers/specs/*-design.md + plans/*.md): {root}"
)


@dataclass
class FeatureContext:
    layout_type: str  # speckit | superpowers | explicit
    spec_path: str
    plan_path: str | None
    spec_content: str
    plan_content: str | None
    clarifications: list = field(default_factory=list)


def _run_discovery(root: Path, spec: str, plan: str, script: Path) -> str:
    bash_snippet = (
        'source "$1" >/dev/null 2>&1 || exit 9; '
        'SPEC="$2"; PLAN="$3"; TASKS=""; resolve_artifacts "$4"'
    )
    try:
        proc = subprocess.run(
            [
                "bash",
                "-c",
                bash_snippet,
                "cddl-discovery",
                str(script),
                spec,
                plan,
                str(root),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(f"artifact discovery timed out under {root}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise PreflightError(f"artifact discovery failed: {detail}")
    return proc.stdout


def _discover(root: Path, spec, plan, seam: Path) -> dict[str, str]:
    output = _run_discovery(root, str(spec or ""), str(plan or ""), seam)
    artifacts: dict[str, str] = {}
    for line in output.splitlines():
        if "\t" not in line:
            continue
        role, path = line.split("\t", 1)
        if role in ("spec", "plan") and path.strip():
            artifacts.setdefault(role, path.strip())
        # A 'tasks' line is ignored by design (FR-002).
    return artifacts


def resolve_context(
    target: str | Path,
    spec: str | Path | None = None,
    plan: str | Path | None = None,
    script: str | Path | None = None,
) -> FeatureContext:
    """Resolve and snapshot the spec+plan context for one run (pre-flight)."""
    seam = Path(script) if script else SPEC_REVIEW
    if not seam.is_file():
        raise PreflightError(f"discovery seam missing: {seam}")
    root = Path(target).resolve()
    if not root.exists():
        raise PreflightError(f"target path does not exist: {root}")

    # File targets (US3: "point the command at the design doc") are handled
    # by the seam itself: discover_artifacts treats a file root as the
    # explicit spec and pairs the plan within its own layout tree (FR-001 —
    # the layout rules live in exactly one place).
    artifacts = _discover(root, spec, plan, seam)

    spec_path = artifacts.get("spec")
    if not spec_path or not Path(spec_path).is_file():
        raise PreflightError(_REFUSAL.format(root=Path(target).resolve()))

    layout = (
        "explicit"
        if spec
        else (
            "superpowers"
            if "/docs/superpowers/" in str(Path(spec_path).resolve())
            else "speckit"
        )
    )

    spec_content = Path(spec_path).read_text(encoding="utf-8")
    if not spec_content.strip():
        raise PreflightError(f"resolved spec is empty: {spec_path}")

    plan_path = artifacts.get("plan")
    plan_content: str | None = None
    if plan_path and Path(plan_path).is_file():
        plan_content = Path(plan_path).read_text(encoding="utf-8")
    else:
        # Missing plan is recorded and disclosed to critics, never fatal.
        plan_path = None

    return FeatureContext(
        layout_type=layout,
        spec_path=spec_path,
        plan_path=plan_path,
        spec_content=spec_content,
        plan_content=plan_content,
    )
