"""manifest-delegate: registry."""

import json
import sys

from . import constants

# ---------------------------------------------------------------------------
# Registry (backend-registry.schema.json)
# ---------------------------------------------------------------------------


class RegistryError(Exception):
    """Raised when the backend registry fails validation."""


def _walk_strings(value):
    """Yield every string leaf inside a JSON-decoded structure."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            for s in _walk_strings(v):
                yield s
    elif isinstance(value, list):
        for v in value:
            for s in _walk_strings(v):
                yield s


def _validate_argv_template(tokens, where):
    for token in tokens:
        if not isinstance(token, str):
            raise RegistryError(f"{where}: argv tokens must be strings")
        if constants.DANGEROUS_TOKEN_RE.search(token):
            raise RegistryError(
                f"{where}: token {token!r} contains a disallowed bypass/dangerously "
                "pattern (D8)"
            )
        if constants.PLACEHOLDER_RE.match(token):
            continue
        if constants.SHELL_METACHAR_RE.search(token):
            raise RegistryError(
                f"{where}: token {token!r} contains a shell metacharacter; argv arrays "
                "must not depend on shell interpretation"
            )


def _load_registry_raw(path):
    """Read and JSON-decode the registry file, raising RegistryError on failure."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise RegistryError(f"registry not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry {path} is not valid JSON: {exc}") from exc


def _validate_registry_aliases(entry, entry_id, path, seen_ids, seen_aliases):
    """Validate entry['aliases']: must be a list of non-empty, unique strings."""
    aliases = entry.get("aliases", []) or []
    if not isinstance(aliases, list):
        raise RegistryError(
            f"registry {path}: backend {entry_id!r} field 'aliases' must be an array"
        )
    for alias in aliases:
        if not isinstance(alias, str) or not alias:
            raise RegistryError(
                f"registry {path}: backend {entry_id!r} has a non-string/empty alias {alias!r}"
            )
        if alias in seen_aliases or alias in seen_ids:
            raise RegistryError(
                f"registry {path}: duplicate alias {alias!r} for backend {entry_id!r}"
            )
        seen_aliases.add(alias)


def _validate_registry_argv_fields(entry, entry_id, path):
    """Validate invoke/resume/model_args/sandbox argv-shaped fields."""
    invoke = entry.get("invoke")
    if not isinstance(invoke, list) or not invoke:
        raise RegistryError(
            f"registry {path}: backend {entry_id!r} field 'invoke' must be a non-empty array"
        )
    _validate_argv_template(invoke, f"{path}[{entry_id}].invoke")

    resume = entry.get("resume")
    if resume is not None:
        if not isinstance(resume, list):
            raise RegistryError(
                f"registry {path}: backend {entry_id!r} field 'resume' must be an array"
            )
        _validate_argv_template(resume, f"{path}[{entry_id}].resume")

    model_args = entry.get("model_args") or []
    _validate_argv_template(model_args, f"{path}[{entry_id}].model_args")

    sandbox = entry.get("sandbox") or {}
    for field in ("read_only_args", "write_args"):
        _validate_argv_template(
            sandbox.get(field) or [], f"{path}[{entry_id}].sandbox.{field}"
        )


def _validate_registry_input_shape(entry, entry_id, path):
    """Validate input/readiness are objects and input.transport is supported."""
    for field in ("input", "readiness"):
        section = entry.get(field)
        if section is not None and not isinstance(section, dict):
            raise RegistryError(
                f"registry {path}: backend {entry_id!r} field {field!r} must be an object"
            )

    transport = (entry.get("input") or {}).get("transport")
    if transport is not None and transport != "stdin":
        raise RegistryError(
            f"registry {path}: backend {entry_id!r} input.transport {transport!r} is unsupported "
            "(only 'stdin' implemented)"
        )


def _validate_registry_entry(entry, path, seen_ids, seen_aliases):
    """Validate a single backend entry in-place, tracking id/alias uniqueness."""
    if not isinstance(entry, dict):
        raise RegistryError(f"registry {path}: each backend entry must be an object")
    entry_id = entry.get("id")
    if not entry_id or not isinstance(entry_id, str):
        raise RegistryError(f"registry {path}: backend entry missing 'id'")
    if entry_id in seen_ids:
        raise RegistryError(f"registry {path}: duplicate backend id {entry_id!r}")
    seen_ids.add(entry_id)

    _validate_registry_aliases(entry, entry_id, path, seen_ids, seen_aliases)
    _validate_registry_argv_fields(entry, entry_id, path)
    _validate_registry_input_shape(entry, entry_id, path)

    # Belt-and-braces: scan every remaining string leaf for the bypass
    # tokens too, in case a future field carries one (D8 re-validation
    # is defense-in-depth, not just argv-shaped fields).
    for s in _walk_strings(entry):
        if constants.DANGEROUS_TOKEN_RE.search(s):
            raise RegistryError(
                f"registry {path}[{entry_id}]: disallowed bypass/dangerously token found in {s!r}"
            )


def load_registry(path=None):
    """Load and validate the backend registry.

    Raises RegistryError on any structural or safety violation (D8). Callers
    at the CLI boundary translate this into an exit-2 usage error.
    """
    path = path or constants.DEFAULT_REGISTRY_PATH
    raw = _load_registry_raw(path)

    if not isinstance(raw, dict):
        raise RegistryError(f"registry {path}: root must be a JSON object")

    backends = raw.get("backends")
    if not isinstance(backends, list) or not backends:
        raise RegistryError(f"registry {path}: 'backends' must be a non-empty array")

    seen_ids = set()
    seen_aliases = set()
    for entry in backends:
        _validate_registry_entry(entry, path, seen_ids, seen_aliases)

    return backends


def load_registry_or_exit(path=None):
    """CLI-boundary wrapper: load_registry(), or exit 2 on RegistryError.

    A hand-edited registry that fails validation (duplicate ids, dangerous
    tokens, shell metacharacters, ...) must refuse to run rather than
    silently degrade (D8).
    """
    try:
        return load_registry(path)
    except RegistryError as exc:
        print(f"delegate: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def resolve_backend(backends, name):
    """Resolve `name` to a registry entry by id or alias, else None.

    Deliberately backend-name-agnostic (FR-016): no `if name == "codex"`
    branching anywhere in the dispatcher.
    """
    for entry in backends:
        if entry.get("id") == name or name in (entry.get("aliases") or []):
            return entry
    return None
