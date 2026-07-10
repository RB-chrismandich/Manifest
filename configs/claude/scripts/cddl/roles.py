"""Role-definition loading and pre-flight validation (FR-013, research D3).

Contract: specs/482-critic-dev-loop/contracts/role-definition.md. Roles are
read from the deployed prompts namespace (~/.claude/prompts/cddl/) at runtime;
tests inject a fixture directory via the prompts_dir parameter.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import PreflightError

ROLE_FILES = {
    "implementer": "implementer.md",
    "qa_critic": "qa-critic.md",
    "arch_critic": "arch-critic.md",
}

KNOWN_KEYS = {"name", "description", "model", "effort"}
# Contract role-definition.md: alias only — never a dated model ID (FR-013).
ALLOWED_MODELS = {"haiku", "sonnet", "opus"}
# Claude-only in v1 (spec clarification): a provider binding is rejected, not ignored.
RESERVED_KEYS = {"provider"}


@dataclass
class RoleDefinition:
    role_key: str
    name: str
    description: str
    model: str
    prompt_body: str
    source_path: str


def default_prompts_dir() -> Path:
    return Path.home() / ".claude" / "prompts" / "cddl"


def _parse_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise PreflightError(f"role file missing frontmatter delimiter: {path}")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise PreflightError(f"role file frontmatter never closed: {path}")
    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise PreflightError(
            f"role file frontmatter unparseable: {path}: {exc}"
        ) from exc
    if not isinstance(frontmatter, dict):
        raise PreflightError(f"role file frontmatter is not a mapping: {path}")
    return frontmatter, "\n".join(lines[end + 1 :])


def load_role(role_key: str, prompts_dir: str | Path | None = None) -> RoleDefinition:
    prompts_dir = Path(prompts_dir) if prompts_dir else default_prompts_dir()
    path = prompts_dir / ROLE_FILES[role_key]
    if not path.is_file():
        raise PreflightError(f"role file missing: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PreflightError(f"role file unreadable: {path}: {exc}") from exc

    frontmatter, body = _parse_frontmatter(text, path)

    reserved = RESERVED_KEYS & frontmatter.keys()
    if reserved:
        raise PreflightError(
            f"role file uses reserved key '{sorted(reserved)[0]}' "
            f"(roles are Claude-only in v1): {path}"
        )
    unknown = frontmatter.keys() - KNOWN_KEYS
    if unknown:
        print(
            f"cddl-loop: warning: ignoring unknown role keys "
            f"{sorted(unknown)} in {path}",
            file=sys.stderr,
        )

    fields = {}
    for field in ("name", "description", "model"):
        value = str(frontmatter.get(field) or "").strip()
        if not value:
            raise PreflightError(f"role file has empty '{field}': {path}")
        fields[field] = value
    if fields["model"] not in ALLOWED_MODELS:
        raise PreflightError(
            f"role 'model' must be an alias ({'|'.join(sorted(ALLOWED_MODELS))}), "
            f"got {fields['model']!r}: {path}"
        )
    if fields["name"] != path.stem:
        raise PreflightError(
            f"role 'name' ({fields['name']!r}) must equal the file stem "
            f"({path.stem!r}): {path}"
        )
    if not body.strip():
        raise PreflightError(f"role file has an empty prompt body: {path}")

    return RoleDefinition(
        role_key=role_key,
        prompt_body=body,
        source_path=str(path),
        **fields,
    )


def load_roles(prompts_dir: str | Path | None = None) -> dict[str, RoleDefinition]:
    """Load and validate the fixed v1 role set; any failure refuses pre-flight."""
    return {key: load_role(key, prompts_dir) for key in ROLE_FILES}
