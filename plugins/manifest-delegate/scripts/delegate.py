#!/usr/bin/env python3
# help-coverage: covered by tests/bats/help_coverage.bats
"""manifest-delegate dispatcher.

Stdlib-only CLI that routes delegation/second-opinion/review/gate work to an
extensible backend registry (config/backends.json). See
specs/675-multi-agent-delegation/contracts/delegate-cli.md for the full
subcommand contract.
"""

import sys

# --- Early interpreter version probe (D11) --------------------------------
# Must be the first executable statements and must be parseable by very old
# interpreters (no f-strings, no type hints) so the remediation message can
# always be printed.
if sys.version_info < (3, 9):  # noqa: UP036 — deliberate runtime guard, see D11
    sys.stderr.write(
        "delegate.py: unsupported Python version %s.%s — "  # noqa: UP031
        "manifest-delegate requires Python 3.9 or newer.\n"
        "Install a supported interpreter, e.g.:\n"
        "  macOS:  brew install python@3.11\n"
        "  Linux:  use your distro's python3.9+ package\n"
        "Then re-run with that interpreter's `python3` on PATH.\n"
        % (sys.version_info[0], sys.version_info[1])
    )
    sys.exit(2)

# Everything below this line may use 3.9+ syntax.
import argparse
import concurrent.futures
import contextlib
import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_REGISTRY_PATH = os.path.join(PLUGIN_DIR, "config", "backends.json")

DANGEROUS_TOKEN_RE = re.compile(r"dangerously|bypass", re.IGNORECASE)
SHELL_METACHAR_RE = re.compile(r"[;|&`$><\n]")
PLACEHOLDER_RE = re.compile(r"^\{[a-z_]+\}$")

SUBCOMMANDS = [
    "task",
    "review",
    "status",
    "result",
    "cancel",
    "setup",
    "transfer",
    "gate",
    "resume-candidate",
]

DELEGATIONS_DIR_ENV = "MANIFEST_DELEGATIONS_DIR"
CONFIG_DIR_ENV = "MANIFEST_CONFIG_DIR"
HOME_CONFIG_DIR = os.path.expanduser("~/.claude/config")

KEEP_LAST_N = 50


def err(message):
    sys.stderr.write(f"delegate.py: {message}\n")


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
        if DANGEROUS_TOKEN_RE.search(token):
            raise RegistryError(
                f"{where}: token {token!r} contains a disallowed bypass/dangerously "
                "pattern (D8)"
            )
        if PLACEHOLDER_RE.match(token):
            continue
        if SHELL_METACHAR_RE.search(token):
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
        if DANGEROUS_TOKEN_RE.search(s):
            raise RegistryError(
                f"registry {path}[{entry_id}]: disallowed bypass/dangerously token found in {s!r}"
            )


def load_registry(path=None):
    """Load and validate the backend registry.

    Raises RegistryError on any structural or safety violation (D8). Callers
    at the CLI boundary translate this into an exit-2 usage error.
    """
    path = path or DEFAULT_REGISTRY_PATH
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


# ---------------------------------------------------------------------------
# User configuration (delegation-config.schema.json, research.md D3)
# ---------------------------------------------------------------------------

FACTORY_DEFAULTS = {
    "default_backend": "codex",
    "review_gate": {
        "enabled": False,
        "backend": None,
        "budget_seconds": 600,
    },
    "backends": {},
}

GATE_BUDGET_CAP_SECONDS = 840  # Stop-hook timeout (900s) minus cleanup overhead


def _config_search_dirs(explicit_dir=None):
    dirs = []
    if explicit_dir:
        dirs.append(explicit_dir)
    env_dir = os.environ.get(CONFIG_DIR_ENV)
    if env_dir:
        dirs.append(env_dir)
    dirs.append(HOME_CONFIG_DIR)
    return dirs


def _yaml_module():
    try:
        import yaml  # type: ignore

        return yaml
    except ImportError:
        return None


def _find_user_config_path(explicit_dir):
    """Locate the first delegation.{json,yml} across the search-dir precedence."""
    for candidate_dir in _config_search_dirs(explicit_dir):
        json_path = os.path.join(candidate_dir, "delegation.json")
        yaml_path = os.path.join(candidate_dir, "delegation.yml")
        if os.path.isfile(json_path):
            return json_path
        if os.path.isfile(yaml_path):
            return yaml_path
    return None


def _parse_user_config_file(chosen_path, report):
    """Parse the resolved config file. Returns (data, error_message_or_None)."""
    if chosen_path.endswith(".json"):
        try:
            with open(chosen_path, encoding="utf-8") as fh:
                return json.load(fh), None
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"{chosen_path} is unreadable ({exc}); using factory defaults"

    yaml_mod = _yaml_module()
    if yaml_mod is None:
        return None, (
            f"{chosen_path} present but PyYAML is not importable; delegation.yml is "
            "unreadable in this environment — using factory defaults"
        )
    try:
        with open(chosen_path, encoding="utf-8") as fh:
            return yaml_mod.safe_load(fh) or {}, None
    except (OSError, Exception) as exc:
        return None, f"{chosen_path} is unreadable ({exc}); using factory defaults"


def _is_positive_int(value):
    """True JSON integers only (bool is an int subclass; exclude it)."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_backend_entry(backend_id, entry, chosen_path, report):
    """Validate one backends.<id> entry; drop invalid keys, report why (D3)."""
    known_backend_keys = {"enabled", "model", "budget_seconds"}
    clean_entry = {}
    for key, val in entry.items():
        if key not in known_backend_keys:
            report(f"{chosen_path}: unknown key backends.{backend_id}.{key} ignored")
            continue
        if key == "enabled" and not isinstance(val, bool):
            report(
                f"{chosen_path}: backends.{backend_id}.enabled must be true/false, got {val!r}; ignored"
            )
            continue
        if key == "budget_seconds" and not _is_positive_int(val):
            report(
                f"{chosen_path}: backends.{backend_id}.budget_seconds must be a positive integer, got {val!r}; ignored"
            )
            continue
        if key == "model" and not isinstance(val, str):
            report(
                f"{chosen_path}: backends.{backend_id}.model must be a string, got {val!r}; ignored"
            )
            continue
        clean_entry[key] = val
    return clean_entry


def _merge_review_gate(gate, chosen_path, result, report):
    """Validate and merge a `review_gate` block in-place into `result`."""
    if isinstance(gate.get("enabled"), bool):
        result["review_gate"]["enabled"] = gate["enabled"]
    elif "enabled" in gate:
        report(
            "{}: review_gate.enabled must be true/false, got {!r}; using factory default".format(
                chosen_path, gate["enabled"]
            )
        )

    if isinstance(gate.get("backend"), str):
        result["review_gate"]["backend"] = gate["backend"]
    elif "backend" in gate:
        report(
            "{}: review_gate.backend must be a string, got {!r}; ignored".format(
                chosen_path, gate["backend"]
            )
        )

    budget = gate.get("budget_seconds")
    if "budget_seconds" in gate:
        if not _is_positive_int(budget):
            report(
                f"{chosen_path}: review_gate.budget_seconds must be a positive integer, got {budget!r}; using factory default"
            )
        else:
            if budget > GATE_BUDGET_CAP_SECONDS:
                report(
                    f"{chosen_path}: review_gate.budget_seconds {budget} "
                    f"exceeds cap {GATE_BUDGET_CAP_SECONDS}; capping"
                )
                budget = GATE_BUDGET_CAP_SECONDS
            result["review_gate"]["budget_seconds"] = budget


def _merge_user_config_data(data, chosen_path, result, report):
    """Merge validated top-level keys from `data` into `result` in-place."""
    known_top = {"default_backend", "review_gate", "backends"}
    for key in list(data.keys()):
        if key not in known_top:
            report(f"{chosen_path}: unknown top-level key {key!r} ignored")
            data.pop(key)

    if "default_backend" in data and isinstance(data["default_backend"], str):
        result["default_backend"] = data["default_backend"]

    gate = data.get("review_gate")
    if isinstance(gate, dict):
        _merge_review_gate(gate, chosen_path, result, report)

    backends_cfg = data.get("backends")
    if isinstance(backends_cfg, dict):
        for backend_id, entry in backends_cfg.items():
            if not isinstance(entry, dict):
                report(
                    f"{chosen_path}: backends.{backend_id} is not an object; ignored"
                )
                continue
            result["backends"][backend_id] = _validate_backend_entry(
                backend_id, entry, chosen_path, report
            )


def load_user_config(explicit_dir=None, reporter=None):
    """Resolve ~/.claude/config/delegation.{json,yml} per D3.

    Precedence: explicit_dir > $MANIFEST_CONFIG_DIR > ~/.claude/config.
    Within a directory: delegation.json always wins if present; otherwise
    delegation.yml is honored only when PyYAML is importable. Any parse
    failure is reported (never raised) and factory defaults are returned —
    this is a deliberate divergence from agents-config's ConfigError (D3).
    """
    report = reporter or (lambda msg: err(msg))
    result = json.loads(json.dumps(FACTORY_DEFAULTS))  # deep copy

    chosen_path = _find_user_config_path(explicit_dir)
    if chosen_path is None:
        return result

    data, error_message = _parse_user_config_file(chosen_path, report)
    if error_message is not None:
        report(error_message)
        return result

    if not isinstance(data, dict):
        report(f"{chosen_path} did not parse to an object; using factory defaults")
        return result

    _merge_user_config_data(data, chosen_path, result, report)
    return result


def _write_review_gate_yaml(changes, config_dir, yaml_path, yaml_mod, report):
    """Update review_gate in an existing delegation.yml. Returns (path, data).

    Raises RegistryError if yaml_path exists but cannot be read/parsed —
    an existing unreadable config is never overwritten with defaults.
    """
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            data = yaml_mod.safe_load(fh) or {}
    except (OSError, yaml_mod.YAMLError) as exc:
        raise RegistryError(
            f"refusing to overwrite unreadable config {yaml_path} ({exc}); fix or remove it first"
        ) from exc
    if not isinstance(data, dict):
        data = {}
    gate = data.get("review_gate")
    if not isinstance(gate, dict):
        gate = dict(FACTORY_DEFAULTS["review_gate"])
    gate.update(changes)
    data["review_gate"] = gate
    os.makedirs(config_dir, exist_ok=True)
    content = yaml_mod.safe_dump(data, default_flow_style=False, sort_keys=False)
    _atomic_write_0600(yaml_path, content)
    return yaml_path, data


def _write_review_gate_json(changes, config_dir, json_path, report):
    """Update review_gate in delegation.json (creating from defaults if absent).

    Returns (path, data). Raises RegistryError if json_path exists but
    cannot be read/parsed — an existing unreadable config is never
    overwritten with defaults.
    """
    data = json.loads(json.dumps(FACTORY_DEFAULTS))  # deep copy
    if os.path.isfile(json_path):
        try:
            with open(json_path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(
                f"refusing to overwrite unreadable config {json_path} ({exc}); fix or remove it first"
            ) from exc
        if isinstance(existing, dict):
            data.update(existing)
    gate = data.get("review_gate")
    if not isinstance(gate, dict):
        gate = dict(FACTORY_DEFAULTS["review_gate"])
    gate.update(changes)
    data["review_gate"] = gate
    os.makedirs(config_dir, exist_ok=True)
    content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    _atomic_write_0600(json_path, content)
    return json_path, data


def write_review_gate_config(changes, explicit_dir=None, reporter=None):
    """Write review_gate.* changes to the user config per D3.

    Canonical write target: delegation.json (created with factory defaults +
    the change when no config exists). An existing delegation.yml is updated
    in place only when PyYAML is importable; a .yml present without PyYAML is
    reported unreadable and delegation.json is written and takes precedence.
    Returns (path_written, dict_written).
    """
    report = reporter or (lambda msg: err(msg))
    config_dir = next(iter(_config_search_dirs(explicit_dir)), None)
    json_path = os.path.join(config_dir, "delegation.json")
    yaml_path = os.path.join(config_dir, "delegation.yml")

    yaml_mod = _yaml_module()
    use_yaml = (
        yaml_mod is not None
        and os.path.isfile(yaml_path)
        and not os.path.isfile(json_path)
    )

    if os.path.isfile(yaml_path) and not os.path.isfile(json_path) and yaml_mod is None:
        report(
            f"{yaml_path} present but PyYAML is not importable; delegation.yml is "
            "unreadable in this environment — writing delegation.json, "
            "which takes precedence"
        )

    if use_yaml:
        return _write_review_gate_yaml(changes, config_dir, yaml_path, yaml_mod, report)
    return _write_review_gate_json(changes, config_dir, json_path, report)


def load_services_disabled(config_dir=None):
    """Read workspace services.yml for backend disables via a fixed-format
    line reader — matched to write_services_config() in
    bootstrap/lib/config.sh — so this never requires PyYAML.

    Returns a set of services_key values explicitly disabled
    (`enabled: false` under that key).
    """
    disabled = set()
    for candidate_dir in _config_search_dirs(config_dir):
        services_path = os.path.join(candidate_dir, "services.yml")
        if not os.path.isfile(services_path):
            continue
        current_key = None
        try:
            with open(services_path, encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    top_match = re.match(r"^([A-Za-z0-9_-]+):\s*$", line.rstrip("\n"))
                    if top_match:
                        current_key = top_match.group(1)
                        continue
                    kv_match = re.match(
                        r"^\s+enabled:\s*(true|false)\s*$", line.rstrip("\n")
                    )
                    if kv_match and current_key:
                        if kv_match.group(1) == "false":
                            disabled.add(current_key)
                    else:
                        flat_match = re.match(
                            r"^([A-Za-z0-9_-]+):\s*(true|false)\s*$", line.rstrip("\n")
                        )
                        if flat_match and flat_match.group(2) == "false":
                            disabled.add(flat_match.group(1))
        except OSError:
            continue
        break  # first services.yml found wins, same precedence as delegation.*
    return disabled


def load_model_tiers(config_dir=None):
    """Read parallel_agent.yml's model_tiers, only when PyYAML is importable.

    Returns {} (tier passthrough) when PyYAML is absent or the file/key is
    missing — never raises.
    """
    yaml_mod = _yaml_module()
    if yaml_mod is None:
        return {}
    for candidate_dir in _config_search_dirs(config_dir):
        path = os.path.join(candidate_dir, "parallel_agent.yml")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = yaml_mod.safe_load(fh) or {}
        except Exception:
            return {}
        tiers = data.get("model_tiers")
        if isinstance(tiers, dict):
            return tiers
        return {}
    return {}


def effective_backend_enabled(backend_id, user_config, services_disabled):
    """Resolve enable/disable with layer attribution (workspace beats user).

    Returns (enabled: bool, layer: str).
    """
    if backend_id in services_disabled:
        return False, "workspace services.yml"
    entry = (user_config.get("backends") or {}).get(backend_id, {})
    enabled = entry.get("enabled", True)
    return bool(enabled), (
        "user delegation config" if "enabled" in entry else "factory default"
    )


# ---------------------------------------------------------------------------
# Job-record store (data-model.md)
# ---------------------------------------------------------------------------

TERMINAL_STATES = {"completed", "failed", "timeout", "cancelled"}
NON_TERMINAL_STATES = {"queued", "running"}


def workspace_slug(cwd=None):
    cwd = cwd or os.getcwd()
    base = os.path.basename(os.path.normpath(cwd)) or "workspace"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", base).strip("-").lower() or "workspace"
    digest = hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]
    return f"{slug}-{digest}"


def delegations_root():
    override = os.environ.get(DELEGATIONS_DIR_ENV)
    if override:
        return override
    return os.path.expanduser("~/.claude/.agent_outputs/delegations")


def _mkdir_0700(path):
    os.makedirs(path, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)


def _write_0600(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    finally:
        pass
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _atomic_write_0600(path, content):
    """Write content to path atomically: tmp file (0600) + fsync + os.replace.

    If path already exists and is readable, best-effort back it up to
    ``<path>.bak`` before the replace so a bad write is always recoverable.
    """
    directory = os.path.dirname(path) or "."
    if os.path.isfile(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except OSError as exc:
            # Best-effort backup; never block the write on this, but the
            # operator should still know the .bak safety net didn't land.
            err(f"warning: could not create backup {path}.bak ({exc})")
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError as cleanup_exc:
            err(f"warning: could not remove temp file {tmp_path} ({cleanup_exc})")
        raise


class JobStore:
    """Per-job record directories with CAS-locked record.json mutation."""

    def __init__(self, cwd=None, root=None):
        self.workspace_dir = os.path.join(
            root or delegations_root(), workspace_slug(cwd)
        )
        _mkdir_0700(self.workspace_dir)

    def job_dir(self, job_id):
        return os.path.join(self.workspace_dir, job_id)

    def create(self, backend_id, extra=None):
        job_id = uuid.uuid4().hex
        job_dir = self.job_dir(job_id)
        _mkdir_0700(job_dir)
        record = {
            "job_id": job_id,
            "backend": backend_id,
            "state": "queued",
            "pgid": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        if extra:
            record.update(extra)
        _write_0600(os.path.join(job_dir, "record.json"), json.dumps(record, indent=2))
        _write_0600(os.path.join(job_dir, "output.txt"), "")
        _write_0600(os.path.join(job_dir, "job.log"), "")
        self._prune()
        return record

    def _lock_path(self, job_id):
        return os.path.join(self.job_dir(job_id), ".lock")

    def read(self, job_id):
        record_path = os.path.join(self.job_dir(job_id), "record.json")
        with open(record_path, encoding="utf-8") as fh:
            return json.load(fh)

    def mutate(self, job_id, mutator):
        """Compare-and-replace mutation inside a per-job flock.

        `mutator(record) -> record | None`. Returning None means "refuse the
        mutation" (e.g. record is already terminal); the caller gets back the
        current on-disk record unchanged.
        """
        job_dir = self.job_dir(job_id)
        lock_path = self._lock_path(job_id)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            record_path = os.path.join(job_dir, "record.json")
            with open(record_path, encoding="utf-8") as fh:
                current = json.load(fh)
            if (
                current.get("state") in TERMINAL_STATES
                and mutator.__name__ != "_reaper_noop"
            ):
                # Terminal states are immutable; refuse silently (no-op).
                allow_terminal = getattr(mutator, "allow_terminal_reentry", False)
                if not allow_terminal:
                    return current
            updated = mutator(current)
            if updated is None:
                return current
            updated["updated_at"] = time.time()
            fd, tmp_path = tempfile.mkstemp(
                dir=job_dir, prefix=".record.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(updated, indent=2))
                os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
                os.rename(tmp_path, record_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError as cleanup_exc:
                    err(
                        f"job {job_id}: failed to remove stale tempfile {tmp_path}: {cleanup_exc}"
                    )
                raise
            return updated
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _pgid_alive(self, pgid):
        if not pgid:
            return False
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError as exc:
            return exc.errno != errno.ESRCH

    def reap_if_dead(self, job_id):
        """If the recorded worker/pgid is dead and the job is non-terminal,
        kill any surviving backend pgid and mark the job failed."""
        record = self.read(job_id)
        if record.get("state") not in NON_TERMINAL_STATES:
            # Terminal already, but a cancel that raced a backend fork can leave
            # the detached process group alive after the record was frozen. Reap
            # that orphan ONCE, then clear the pgid and the crash-safe file so no
            # later pass re-probes: a recycled pgid must never be re-killed.
            if record.get("state") == "cancelled" and _has_pgid_tracking(
                self, job_id, record
            ):
                _reap_cancelled_orphan(self, job_id, record)
            return record
        # Liveness via the worker's lifetime flock, not os.kill(worker_pid, 0):
        # a recycled pid would answer the signal-0 probe and falsely read alive.
        if _worker_alive(self, job_id, record):
            return record

        # Startup grace: between job creation and the worker acquiring its
        # lifetime lock, the worker is not yet confirmable-alive but the job is
        # NOT dead — it is still starting. Reaping here would fail a live job
        # (observable when parallel sessions share a workspace). Give the worker
        # WORKER_STARTUP_GRACE_SECONDS to publish its lock before we treat a
        # missing worker as death.
        age = time.time() - record.get("created_at", 0)
        if age < WORKER_STARTUP_GRACE_SECONDS:
            return record

        pgid = record.get("pgid") or _read_pgid_file(self.job_dir(job_id))
        if pgid and _backend_alive(self, job_id):
            _kill_pgid(self, job_id, pgid)

        def _mark_failed(rec):
            if rec.get("state") not in NON_TERMINAL_STATES:
                return None
            rec["state"] = "failed"
            rec["error"] = "process died without result"
            return rec

        return self.mutate(job_id, _mark_failed)

    def list_job_ids(self):
        if not os.path.isdir(self.workspace_dir):
            return []
        return [
            name
            for name in os.listdir(self.workspace_dir)
            if os.path.isdir(os.path.join(self.workspace_dir, name))
        ]

    def _prune(self):
        """Delete oldest terminal jobs beyond KEEP_LAST_N.

        Non-terminal (queued/running) jobs are never prune candidates and
        never count toward the KEEP_LAST_N cap, regardless of age.
        """
        job_ids = self.list_job_ids()
        entries = []
        for job_id in job_ids:
            try:
                record = self.read(job_id)
            except (OSError, ValueError):
                continue
            if record.get("state") not in TERMINAL_STATES:
                continue
            record_path = os.path.join(self.job_dir(job_id), "record.json")
            try:
                mtime = os.path.getmtime(record_path)
            except OSError:
                mtime = 0
            entries.append((mtime, job_id))
        if len(entries) <= KEEP_LAST_N:
            return
        entries.sort()
        excess = len(entries) - KEEP_LAST_N
        for _, job_id in entries[:excess]:
            self._delete_job_locked(job_id)

    def _delete_job_locked(self, job_id):
        """Delete a job dir under its own flock, re-checking terminal state.

        Guards against a race where the job transitioned to non-terminal
        between the prune scan and this call.

        Returns True if the job dir (and its lock file) was fully removed,
        False if any part of the cleanup was skipped — a job dir that can't
        be read/locked/removed is simply left in place, not pruned, and the
        reason is logged at debug level.
        """
        job_dir = self.job_dir(job_id)
        lock_path = self._lock_path(job_id)
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                record = self.read(job_id)
            except (OSError, ValueError):
                record = None
            if record is not None and record.get("state") not in TERMINAL_STATES:
                return
            try:
                for root, dirs, files in os.walk(job_dir, topdown=False):
                    for name in files:
                        if os.path.join(root, name) == lock_path:
                            continue
                        os.unlink(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
            except OSError:
                return
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        try:
            os.unlink(lock_path)
        except OSError as exc:
            logging.debug(
                "delegate: prune: could not remove lock file %s for job %s, "
                "leaving job dir in place: %s",
                lock_path,
                job_id,
                exc,
            )
            return False
        try:
            os.rmdir(job_dir)
        except OSError as exc:
            logging.debug(
                "delegate: prune: job dir %s not empty/removable for job %s, "
                "not pruned: %s",
                job_dir,
                job_id,
                exc,
            )
            return False
        return True


# ---------------------------------------------------------------------------
# Result-envelope normalization (result-envelope.schema.json)
# ---------------------------------------------------------------------------

REQUIRED_ENVELOPE_FIELDS = [
    "backend",
    "model",
    "outcome",
    "attempted",
    "changes",
    "succeeded",
    "failed",
    "follow_ups",
]

FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def _extract_last_json_block(text):
    matches = FENCE_RE.findall(text or "")
    for block in reversed(matches):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


ENVELOPE_OUTCOMES = ("success", "partial", "failure")
ENVELOPE_ARRAY_FIELDS = ("changes", "succeeded", "failed", "follow_ups")


def _envelope_type_errors(parsed):
    """Return a list of schema type/enum violations in `parsed` (empty if valid)."""
    errors = []
    outcome = parsed.get("outcome")
    if outcome not in ENVELOPE_OUTCOMES:
        errors.append(
            f"outcome must be one of {list(ENVELOPE_OUTCOMES)}, got {outcome!r}"
        )
    if not isinstance(parsed.get("attempted"), str):
        errors.append("attempted must be a string")
    for field in ENVELOPE_ARRAY_FIELDS:
        value = parsed.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            errors.append(f"{field} must be an array of strings")
    model = parsed.get("model")
    if model is not None and not isinstance(model, str):
        errors.append("model must be a string or null")
    return errors


def _failure_envelope(backend_id, model, error, parsed=None, raw_output=""):
    """Build a failure envelope, salvaging only well-typed fields from `parsed`."""
    parsed = parsed or {}

    def _safe_list(field):
        value = parsed.get(field)
        return (
            value
            if isinstance(value, list) and all(isinstance(v, str) for v in value)
            else []
        )

    attempted = parsed.get("attempted")
    return {
        "backend": backend_id,
        "model": model,
        "outcome": "failure",
        "attempted": attempted if isinstance(attempted, str) else "",
        "changes": _safe_list("changes"),
        "succeeded": _safe_list("succeeded"),
        "failed": _safe_list("failed"),
        "follow_ups": _safe_list("follow_ups"),
        "error": error,
        "raw_output": raw_output,
    }


def normalize_envelope(raw_output, backend_id, model):
    """Mechanically extract and strictly validate the last fenced JSON block.

    Never derives fields from prose. Empty/malformed/no-block/invalid output is
    a `failure` outcome with the raw output preserved (SC-004) — the dispatcher
    must never fabricate a summary. `backend`/`model` are always overwritten
    with dispatcher-known provenance; a backend can never self-report identity.
    """
    parsed = _extract_last_json_block(raw_output)
    if parsed is None:
        return _failure_envelope(
            backend_id, model, "backend returned nothing usable", raw_output=raw_output
        )

    missing = [f for f in REQUIRED_ENVELOPE_FIELDS if f not in parsed]
    if missing:
        return _failure_envelope(
            backend_id,
            model,
            "backend envelope invalid: missing required fields: {}".format(
                ", ".join(missing)
            ),
            parsed=parsed,
            raw_output=raw_output,
        )

    type_errors = _envelope_type_errors(parsed)
    if type_errors:
        return _failure_envelope(
            backend_id,
            model,
            "backend envelope invalid: {}".format("; ".join(type_errors)),
            parsed=parsed,
            raw_output=raw_output,
        )

    if parsed.get("outcome") == "failure" and not parsed.get("error"):
        parsed["error"] = "backend reported failure without an error message"

    parsed["backend"] = backend_id
    parsed["model"] = model
    return parsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


REGISTRY_PATH_ENV = "MANIFEST_DELEGATE_REGISTRY_PATH"
DEFAULT_BUDGET_SECONDS = 600


def _registry_path_override():
    return os.environ.get(REGISTRY_PATH_ENV)


def _substitute_argv(tokens, mapping):
    out = []
    for tok in tokens:
        if PLACEHOLDER_RE.match(tok):
            out.append(mapping.get(tok[1:-1], tok))
        else:
            out.append(tok)
    return out


def map_model_tier(entry, tier):
    """Map a tier name through parallel_agent.yml model_tiers (D3/D4/D5 contract).

    Consults `model_tiers.<entry["tier_source-keyed backend id]>.<tier>` only
    when PyYAML is importable and the deployed config + key + tier are all
    present; any of those being absent falls back to verbatim passthrough
    (the devin precedent — never an error).
    """
    if not tier:
        return tier
    tier_source = entry.get("tier_source")
    if tier_source:
        tiers = load_model_tiers()
        backend_tiers = tiers.get(entry["id"]) if isinstance(tiers, dict) else None
        if isinstance(backend_tiers, dict) and tier in backend_tiers:
            return backend_tiers[tier]
    return tier


def resolve_model_tier(entry, user_config, model_arg):
    if model_arg:
        tier = model_arg
    else:
        backend_cfg = (user_config.get("backends") or {}).get(entry["id"], {})
        tier = backend_cfg.get("model") or entry.get("default_tier")
    return map_model_tier(entry, tier)


def resolve_budget(entry, user_config, budget_arg):
    if budget_arg is not None:
        return budget_arg
    backend_cfg = (user_config.get("backends") or {}).get(entry["id"], {})
    if isinstance(backend_cfg.get("budget_seconds"), int):
        return backend_cfg["budget_seconds"]
    return DEFAULT_BUDGET_SECONDS


def build_invoke_argv(entry, write, model_tier, mapping):
    argv = list(entry.get("invoke") or [])
    sandbox = entry.get("sandbox") or {}
    argv += list(
        (sandbox.get("write_args") if write else sandbox.get("read_only_args")) or []
    )
    if model_tier:
        argv += [
            tok.replace("{model}", model_tier)
            for tok in (entry.get("model_args") or [])
        ]
    return _substitute_argv(argv, mapping)


def build_resume_argv(entry, session_ref, write, model_tier, mapping):
    argv = list(entry.get("resume") or [])
    sandbox = entry.get("sandbox") or {}
    argv += list(
        (sandbox.get("write_args") if write else sandbox.get("read_only_args")) or []
    )
    if model_tier:
        argv += [
            tok.replace("{model}", model_tier)
            for tok in (entry.get("model_args") or [])
        ]
    full_mapping = dict(mapping)
    full_mapping["session_ref"] = session_ref
    return _substitute_argv(argv, full_mapping)


def extract_session_ref(entry, raw_output):
    """Extract a resumable session pointer per the registry's
    session_id_capture method. Never raises; unmatched input -> None."""
    cap = entry.get("session_id_capture") or {}
    method = cap.get("method")
    raw_output = raw_output or ""
    if method == "jsonl_event":
        event_name = cap.get("event")
        field = cap.get("field")
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == event_name:
                return obj.get(field)
        return None
    if method == "json_field":
        field = cap.get("field")
        try:
            obj = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            return None
        return obj.get(field) if isinstance(obj, dict) else None
    if method == "output_scan":
        pattern = cap.get("pattern")
        if not pattern:
            return None
        match = re.search(pattern, raw_output)
        return match.group(1) if match else None
    return None


def check_payload_limits(entry, payload_bytes):
    input_cfg = entry.get("input") or {}
    max_payload = input_cfg.get("max_payload_bytes")
    if max_payload is not None and len(payload_bytes) > max_payload:
        return (
            f"prompt exceeds input.max_payload_bytes "
            f"({len(payload_bytes)} > {max_payload})"
        )
    max_context = input_cfg.get("max_context_bytes")
    if max_context is not None and len(payload_bytes) > max_context:
        return (
            f"prompt exceeds input.max_context_bytes "
            f"({len(payload_bytes)} > {max_context})"
        )
    return None


def _read_prompt(args):
    """Read the effective prompt text. Returns (text, error_message_or_None);
    never raises (D3: a bad --prompt-file must exit 2, not traceback)."""
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        if os.path.isdir(prompt_file):
            return (
                None,
                f"delegate: cannot read --prompt-file {prompt_file}: is a directory",
            )
        try:
            with open(prompt_file, encoding="utf-8") as fh:
                return fh.read(), None
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"delegate: cannot read --prompt-file {prompt_file}: {exc}"
    if args.prompt in (None, "-"):
        return sys.stdin.read(), None
    return args.prompt, None


def _executable_missing(argv):
    if not argv:
        return "empty invoke command"
    exe = argv[0]
    if os.path.dirname(exe):
        return None if os.access(exe, os.X_OK) else f"not executable: {exe}"
    from shutil import which

    return None if which(exe) else f"not found on PATH: {exe}"


BACKEND_PGID_FILENAME = "backend.pgid"
BACKEND_LOCK_FILENAME = "backend.lock"
WORKER_LOCK_FILENAME = "worker.lock"

# Worker-held lock fds, kept open for the worker process's lifetime so the
# kernel releases them only on exit. Never closed explicitly.
_WORKER_LOCK_FDS = []


def _acquire_worker_lifetime_lock(job_dir):
    """Called once at worker startup: hold an exclusive flock on worker.lock for
    the whole process lifetime. Because the kernel releases an flock only when
    the holding process exits, the lock's held-ness is a pid-reuse-proof liveness
    signal — unlike os.kill(pid, 0), which a recycled pid would answer for."""
    fd = os.open(
        os.path.join(job_dir, WORKER_LOCK_FILENAME), os.O_CREAT | os.O_RDWR, 0o600
    )
    fcntl.flock(fd, fcntl.LOCK_EX)
    _WORKER_LOCK_FDS.append(fd)


def _worker_alive(store, job_id, record):
    """True iff THIS job's worker process is still running, proven by the
    worker.lock flock rather than os.kill(worker_pid, 0) — so a recycled pid can
    never be mistaken for a live worker. A missing lock file means the worker was
    recorded but has not yet acquired its lock (a sub-millisecond startup window);
    treated as not-confirmably-alive, which is safe because the atomic
    queued->running claim independently stops a cancelled job's backend."""
    if not record.get("worker_pid"):
        return False
    lock_path = os.path.join(store.job_dir(job_id), WORKER_LOCK_FILENAME)
    if not os.path.exists(lock_path):
        return False
    fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)  # acquired ⇒ no live worker holds it ⇒ dead
        return False
    except OSError:
        return True  # EWOULDBLOCK/EAGAIN ⇒ our worker still holds it
    finally:
        os.close(fd)


def _backend_preexec(job_dir):
    """Return a child preexec_fn that starts a new session (so the backend gets
    its own process group for clean timeout kills) AND writes that group id to
    <job_dir>/backend.pgid before exec. The write happens in the forked child,
    so the pgid is recoverable even if the parent worker is SIGKILLed in the
    window between Popen() returning and the parent's on_pgid persist — closing
    the pre-persist orphan race. Runs post-fork/pre-exec: uses only raw syscalls
    (async-signal-safe-ish), reports nothing (no stdio) and never raises out."""
    pgid_path = os.path.join(job_dir, BACKEND_PGID_FILENAME)

    def _preexec():
        os.setsid()
        fd = os.open(pgid_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.write(fd, str(os.getpgid(0)).encode("ascii"))
        os.close(fd)

    return _preexec


def _backend_alive(store, job_id):
    """True iff this job's backend process group is still running, proven by the
    backend.lock flock (held for the backend's lifetime) rather than
    os.killpg(pgid, 0) — so a recycled pgid is never mistaken for a live backend.
    A missing lock file means no backend is currently holding it (never started,
    or already exited): not confirmably alive."""
    lock_path = os.path.join(store.job_dir(job_id), BACKEND_LOCK_FILENAME)
    if not os.path.exists(lock_path):
        return False
    fd = os.open(lock_path, os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)  # acquired ⇒ no live backend holds it ⇒ dead
        return False
    except OSError:
        return True  # EWOULDBLOCK/EAGAIN ⇒ the backend still holds it
    finally:
        os.close(fd)


def _read_pgid_file(job_dir):
    """Crash-safe fallback: the backend pgid the child wrote in preexec, or None.
    Used by cancel/reap when the worker died before persisting pgid to the record."""
    try:
        with open(os.path.join(job_dir, BACKEND_PGID_FILENAME), encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


MAX_CAPTURED_OUTPUT_BYTES = 1_048_576  # 1 MiB retained tail of backend output
DRAIN_GRACE_SECONDS = 5  # bound on waiting for the stdout drain after process exit
WORKER_STARTUP_GRACE_SECONDS = 15  # a job younger than this is "starting", not dead


class _BoundedTail:
    """A thread-safe, size-capped byte tail. The reader thread feeds it
    incrementally so that even if the drain thread is later abandoned (a
    detached descendant holding the pipe open would otherwise block it forever),
    the bytes read so far — including the final fenced envelope emitted before
    the block — are already available to the main thread. Memory is bounded to
    `cap` regardless of total output volume."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            self._buf += chunk
            if len(self._buf) > self._cap:
                del self._buf[: len(self._buf) - self._cap]

    def value(self):
        with self._lock:
            return bytes(self._buf)


SESSION_CAPTURE_HEAD_BYTES = (
    262_144  # 256 KiB head retained for early session-id events
)


class _BoundedHead:
    """Thread-safe buffer that keeps only the FIRST `cap` bytes of a stream and
    then stops growing. Session-identification events (e.g. codex's
    `thread.started`) are emitted near the START of the JSONL stream, so the head
    preserves the session ref even when the run emits far more than the tail cap."""

    def __init__(self, cap):
        self._cap = cap
        self._buf = bytearray()
        self._lock = threading.Lock()

    def feed(self, chunk):
        with self._lock:
            room = self._cap - len(self._buf)
            if room > 0:
                self._buf += chunk[:room]

    def value(self):
        with self._lock:
            return bytes(self._buf)


def _drain_into(stream, sinks):
    """Read `stream` to EOF, feeding every sink in `sinks` (each has .feed(bytes)).
    Runs in a daemon thread; if the main thread abandons it (grace exceeded), the
    process exit reaps it."""
    while True:
        try:
            chunk = stream.read(65536)
        except (ValueError, OSError):
            break
        if not chunk:
            break
        for sink in sinks:
            sink.feed(chunk)


def _feed_stdin(stdin, payload):
    """Write `payload` to a subprocess stdin and close it, tolerating a backend
    that closed its end early. Runs in its own thread so a non-draining backend
    cannot deadlock the caller on a full pipe."""
    try:
        stdin.write(payload)
        stdin.close()
    except (
        BrokenPipeError,
        OSError,
    ):  # constitution: exempt C-ERR — backend closed stdin early; captured output is authoritative
        pass


def _read_file_tail(path, cap):
    """Return the last `cap` bytes of `path` decoded as text, or '' on error."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > cap:
                fh.seek(size - cap)
            return fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        err(f"job dir: failed to read output tail {path}: {exc}")
        return ""


def _launch_backend(argv, transport, job_dir):
    """Popen the backend with its own session (setsid) holding a lifetime flock.
    The lock fd is opened in the parent and passed via pass_fds (so close_fds
    does not close it); preexec flocks it in the child. Returns (proc, pgid)."""
    stdin_arg = subprocess.PIPE if transport == "stdin" else subprocess.DEVNULL
    # Flock in the PARENT before Popen so there is NO fork->flock window: the
    # child inherits the already-locked open-file description via pass_fds (an
    # flock lives on the description, shared across fork), so backend.lock is held
    # continuously from the instant Popen returns until the backend exits. The
    # parent then closes its copy; the child keeps the description (and the lock).
    lock_fd = os.open(
        os.path.join(job_dir, BACKEND_LOCK_FILENAME), os.O_CREAT | os.O_RDWR, 0o600
    )
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=stdin_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=_backend_preexec(job_dir),
            pass_fds=(lock_fd,),
        )
    finally:
        os.close(lock_fd)  # child holds the locked description; parent's copy is done
    try:
        return proc, os.getpgid(proc.pid)
    except OSError:
        return proc, proc.pid


def _spawn_backend(entry, argv, prompt_bytes, job_dir, budget, on_pgid=None):
    stdout_path = os.path.join(job_dir, "output.txt")
    with open(os.path.join(job_dir, "job.log"), "a", encoding="utf-8") as log_fh:
        log_fh.write("invoke: {}\n".format(" ".join(argv)))
    transport = (entry.get("input") or {}).get("transport", "stdin")
    proc, pgid = _launch_backend(argv, transport, job_dir)
    if on_pgid:
        on_pgid(pgid)

    # Drain stdout in a thread that keeps only a bounded tail, so peak memory is
    # capped regardless of how much the backend emits. proc.wait enforces the
    # budget independently of output volume.
    tail = _BoundedTail(MAX_CAPTURED_OUTPUT_BYTES)
    head = _BoundedHead(SESSION_CAPTURE_HEAD_BYTES)
    reader = threading.Thread(
        target=_drain_into, args=(proc.stdout, (head, tail)), daemon=True
    )
    reader.start()
    if transport == "stdin":
        # Feed stdin from its own thread: a backend that never drains stdin must
        # not deadlock our write on a full pipe (the reader is draining stdout
        # concurrently, and the timeout below still bounds the whole run).
        writer = threading.Thread(
            target=_feed_stdin, args=(proc.stdin, prompt_bytes), daemon=True
        )
        writer.start()
    timed_out = False
    try:
        proc.wait(timeout=budget)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(pgid, signal.SIGKILL)
        except OSError as exc:
            err(f"job dir {job_dir}: failed to kill timed-out pgid {pgid}: {exc}")
        proc.wait()
    reader.join(DRAIN_GRACE_SECONDS)
    if reader.is_alive():
        # The backend exited/was killed, but a detached descendant is still
        # holding the stdout pipe open, so the reader is blocked in read() —
        # which closing the fd does NOT reliably interrupt. Abandon the daemon
        # reader (process exit reaps it) rather than hang past budget (a DoS
        # vector): the bytes read so far, including the envelope emitted before
        # the block, are already in the tail. Mark the run timed out (incomplete).
        timed_out = True
    raw = tail.value().decode("utf-8", errors="replace")
    output_file_content = (
        _read_file_tail(stdout_path, MAX_CAPTURED_OUTPUT_BYTES)
        if os.path.isfile(stdout_path)
        else ""
    )
    combined = (output_file_content + "\n" + raw) if output_file_content else raw
    # Session ref may scroll out of the 1 MiB tail on large runs, so prefer the
    # retained head (early events) and fall back to the tail.
    session_ref = extract_session_ref(
        entry, head.value().decode("utf-8", errors="replace")
    ) or extract_session_ref(entry, combined)
    return proc.returncode, combined, pgid, timed_out, session_ref


def _kill_pgid(store, job_id, pgid):
    """Best-effort SIGKILL of a backend process group. Shared by the cancel
    path, the reaper, and the worker's cancel-during-fork guard so there is one
    killpg call site with one error-reporting convention."""
    try:
        os.killpg(pgid, signal.SIGKILL)
        return True
    except OSError as exc:
        # pgid may have exited between a liveness check and this call.
        err(f"job {job_id}: failed to kill pgid {pgid}: {exc}")
        return False


def _has_pgid_tracking(store, job_id, record):
    """True if a job still has ANY backend-pgid tracking — recorded in the
    record OR present as the crash-safe backend.pgid file — regardless of
    whether that pgid is currently alive. Gates the cancelled-orphan reap on
    *presence* (not liveness) so a dead-but-uncleared stale pgid is still
    cleaned up once, closing the recycled-pgid wrong-kill window."""
    if record.get("pgid") is not None:
        return True
    return os.path.exists(os.path.join(store.job_dir(job_id), BACKEND_PGID_FILENAME))


def _clear_pgid_tracking(store, job_id):
    """Erase all backend-pgid tracking for a job: null the recorded pgid (a
    terminal-safe mutate) and delete the crash-safe backend.pgid file. Called as
    the FINAL act of every site that kills a backend because the job went
    cancelled, so no later reap/status/list call can re-derive a stale pgid and
    SIGKILL a process group the kernel has since recycled."""

    def _clear(rec):
        return dict(rec, pgid=None)

    _clear.allow_terminal_reentry = True
    store.mutate(job_id, _clear)
    # constitution: exempt C-ERR — absent file is the expected steady state; nothing to recover
    with contextlib.suppress(OSError):
        os.remove(os.path.join(store.job_dir(job_id), BACKEND_PGID_FILENAME))


def _reap_cancelled_orphan(store, job_id, record):
    """Kill the orphaned backend group of a cancelled job (if still alive), then
    clear all pgid tracking so this runs at most once and no later pass can
    re-probe a (possibly recycled) pgid."""
    pgid = record.get("pgid") or _read_pgid_file(store.job_dir(job_id))
    if pgid and _backend_alive(store, job_id):
        _kill_pgid(store, job_id, pgid)
    _clear_pgid_tracking(store, job_id)


def _make_pgid_persister(store, job_id):
    """Return an on_pgid callback that records the backend's process group even
    after the job goes terminal (recording a pgid is bookkeeping, not a
    lifecycle transition), then kills the group if cancel already won the race."""

    def _record(rec):
        return dict(rec, pgid=_record.pgid_val)

    _record.allow_terminal_reentry = True

    def _persist(pgid_val):
        _record.pgid_val = pgid_val
        updated = store.mutate(job_id, _record)
        if updated.get("state") == "cancelled":
            # Detached (setsid) backend outlived the cancel; the worker is the
            # only party that reliably knows the pgid at this instant. Kill it,
            # then clear tracking so the pgid we just re-recorded cannot linger
            # stale for a later reap to re-probe.
            _kill_pgid(store, job_id, pgid_val)
            _clear_pgid_tracking(store, job_id)

    return _persist


def _run_backend_and_finish(store, job_id, entry, record, prompt_bytes):
    job_dir = store.job_dir(job_id)
    mapping = {"output_file": os.path.join(job_dir, "output.txt")}
    resume_from = record.get("resume_from_session_ref")
    if resume_from and entry.get("resume"):
        argv = build_resume_argv(
            entry, resume_from, record.get("write", False), record.get("model"), mapping
        )
    else:
        argv = build_invoke_argv(
            entry, record.get("write", False), record.get("model"), mapping
        )
    budget = record.get("budget_seconds", DEFAULT_BUDGET_SECONDS)

    returncode, raw_output, pgid, timed_out, session_ref = _spawn_backend(
        entry,
        argv,
        prompt_bytes,
        job_dir,
        budget,
        on_pgid=_make_pgid_persister(store, job_id),
    )
    _write_0600(os.path.join(job_dir, "output.txt"), raw_output)
    envelope = normalize_envelope(raw_output, entry["id"], record.get("model"))
    if session_ref is None and entry.get("resume"):
        err(
            "backend {!r} produced no capturable session id this run "
            "(session_id_capture found nothing); a follow-up will start fresh".format(
                entry["id"]
            )
        )
    if timed_out:
        final_state = "timeout"
    elif returncode == 0 and envelope.get("outcome") != "failure":
        final_state = "completed"
    else:
        final_state = "failed"

    def _finish(rec):
        if rec.get("state") in TERMINAL_STATES:
            return None
        rec["state"] = final_state
        rec["envelope"] = envelope
        rec["pgid"] = pgid
        rec["returncode"] = returncode
        if session_ref:
            rec["session_ref"] = session_ref
        return rec

    return store.mutate(job_id, _finish)


def _spawn_worker(store, job_id):
    script = os.path.abspath(__file__)
    proc = subprocess.Popen(
        [sys.executable, script, "_worker", job_id, store.workspace_dir],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    store.mutate(job_id, lambda rec: dict(rec, worker_pid=proc.pid))


def _run_backend_foreground(store, job_id, entry, record, prompt_bytes):
    """Run a backend synchronously in THIS (CLI) process, taking the same
    ownership a background worker does: record this pid as the worker and hold
    the lifetime lock. Without this a long-running foreground delegation has no
    worker pid or lock, so after WORKER_STARTUP_GRACE_SECONDS a concurrent
    status/SessionEnd reap from another session sharing the workspace would see
    it as dead and kill its backend (codex round-3 finding). The lock is held
    for the CLI process lifetime and released on exit, after which a genuinely
    crashed foreground job becomes reapable again."""
    # `foreground=True` marks worker_pid as THIS interactive CLI process, so
    # cancel/terminate kills only the backend group and never SIGKILLs the CLI
    # the user is running (a background worker_pid, by contrast, is killable).
    owned = store.mutate(
        job_id, lambda rec: dict(rec, worker_pid=os.getpid(), foreground=True)
    )
    _acquire_worker_lifetime_lock(store.job_dir(job_id))
    return _run_backend_and_finish(store, job_id, entry, owned, prompt_bytes)


def cmd_worker(job_id, workspace_dir):
    store = JobStore.__new__(JobStore)
    store.workspace_dir = workspace_dir
    try:
        record = store.read(job_id)
    except (OSError, ValueError):
        return 1
    backends = load_registry_or_exit(_registry_path_override())
    entry = resolve_backend(backends, record["backend"])
    if entry is None:
        store.mutate(
            job_id,
            lambda rec: dict(
                rec, state="failed", error="backend no longer in registry"
            ),
        )
        return 1
    job_dir = store.job_dir(job_id)
    # Hold the lifetime lock before the claim so any cancel/reap that observes
    # this worker's pid can verify it is really us (not a recycled pid).
    _acquire_worker_lifetime_lock(job_dir)
    with open(os.path.join(job_dir, "prompt.txt"), encoding="utf-8") as fh:
        prompt_bytes = fh.read().encode("utf-8")
    claimed = store.mutate(
        job_id,
        lambda rec: (
            dict(rec, state="running")
            if rec.get("state") not in TERMINAL_STATES
            else None
        ),
    )
    if claimed.get("state") != "running":
        # Claim lost the race (job already cancelled/terminal): do not start
        # the backend.
        return 1
    _run_backend_and_finish(store, job_id, entry, claimed, prompt_bytes)
    return 0


def _resolve_job_id(store, prefix):
    ids = store.list_job_ids()
    if prefix in ids:
        return prefix, None
    matches = sorted(j for j in ids if j.startswith(prefix))
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"no job matches {prefix!r}"
    return None, "ambiguous job id {!r} matches: {}".format(prefix, ", ".join(matches))


def _resolve_sole_active(store):
    active = []
    for job_id in store.list_job_ids():
        try:
            rec = store.reap_if_dead(job_id)
        except (OSError, ValueError):
            continue
        if rec.get("state") in NON_TERMINAL_STATES:
            active.append(job_id)
    if len(active) == 1:
        return active[0], None
    if not active:
        return None, "no active job"
    return None, "ambiguous: multiple active jobs: {}".format(", ".join(sorted(active)))


def _find_last_job_for_backend(store, backend_id):
    candidates = []
    for job_id in store.list_job_ids():
        try:
            rec = store.read(job_id)
        except (OSError, ValueError):
            continue
        if rec.get("backend") == backend_id and rec.get("session_ref"):
            candidates.append(rec)
    if not candidates:
        return None
    candidates.sort(key=lambda r: r.get("updated_at", 0))
    return candidates[-1]


def _resolve_task_resume(store, args, backends, user_config):
    """Resolve --resume / --resume-last into (resume_record, error_message)."""
    if getattr(args, "resume", None):
        job_id, resume_error = _resolve_job_id(store, args.resume)
        if not job_id:
            return None, resume_error
        try:
            return store.read(job_id), None
        except (OSError, ValueError) as exc:
            return None, f"delegate: cannot read job {args.resume!r}: {exc}"
    if getattr(args, "resume_last", False):
        if args.backend:
            probe = resolve_backend(backends, args.backend)
            probe_id = probe["id"] if probe else args.backend
        else:
            probe_id = user_config.get("default_backend") or "codex"
        resume_record = _find_last_job_for_backend(store, probe_id)
        if resume_record is None:
            return None, f"delegate: no resumable job found for backend {probe_id!r}"
        return resume_record, None
    return None, None


def _resolve_task_second_opinion(store, args):
    """Resolve --second-opinion/--of into (record, error_message)."""
    if not getattr(args, "second_opinion", False):
        return None, None
    if not getattr(args, "of", None):
        return None, "delegate: --second-opinion requires --of <job-id>"
    of_id, of_error = _resolve_job_id(store, args.of)
    if of_error:
        return None, f"delegate: {of_error}"
    try:
        return store.read(of_id), None
    except (OSError, ValueError) as exc:
        return None, f"delegate: cannot read job {args.of!r}: {exc}"


def _resolve_task_backend_entry(args, backends, user_config, resume_record):
    """Resolve the backend registry entry to dispatch to. Returns (entry, error_message)."""
    if resume_record is not None:
        backend_name = resume_record["backend"]
        if args.backend:
            explicit = resolve_backend(backends, args.backend)
            if explicit is None or explicit["id"] != backend_name:
                return None, (
                    f"delegate: --backend {args.backend!r} does not match resumed job's backend {backend_name!r}"
                )
    else:
        backend_name = args.backend or user_config.get("default_backend") or "codex"

    entry = resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        return None, f"delegate: unknown backend {backend_name!r} (known: {known})"
    return entry, None


def _warn_if_second_opinion_same_backend(
    second_opinion_record, entry, backends, user_config, services_disabled
):
    """Print a warning if the second-opinion backend matches the original job's backend."""
    if (
        second_opinion_record is None
        or second_opinion_record.get("backend") != entry["id"]
    ):
        return
    ready_alternatives = []
    for other in backends:
        if other["id"] == entry["id"]:
            continue
        try:
            row = probe_backend_readiness(other, user_config, services_disabled)
        except (OSError, ValueError):
            continue
        if row.get("state") == "ready":
            ready_alternatives.append(other["id"])
    print(
        "delegate: warning: second opinion backend {!r} is the same as the original job's backend"
        " (ready alternatives: {})".format(
            entry["id"], ", ".join(sorted(ready_alternatives)) or "none"
        ),
        file=sys.stderr,
    )


def _check_task_backend_ready(entry, user_config, services_disabled, model_tier):
    """Check backend is enabled and its executable is available. Returns (error_message, exit_code)."""
    enabled, layer = effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if not enabled:
        return (
            "delegate: backend {!r} disabled by {} config; run `delegate.py setup` for alternatives".format(
                entry["id"], layer
            ),
            3,
        )
    unavailable = _executable_missing(
        build_invoke_argv(entry, False, model_tier, {"output_file": "/dev/null"})
    )
    if unavailable:
        return (
            "delegate: backend {!r} unavailable ({}); run `delegate.py setup` to check remediation and alternatives".format(
                entry["id"], unavailable
            ),
            3,
        )
    return None, None


def _build_task_prompt(args, second_opinion_record):
    """Build the effective prompt text and write flag.

    Returns (prompt, write, error_or_None). Never raises: a bad
    --prompt-file must exit 2 through the caller, not traceback.
    """
    if second_opinion_record is not None and getattr(args, "prompt", None) is None:
        # --second-opinion runs with no positional prompt; avoid blocking on
        # sys.stdin.read() (nothing is piped in this mode) and default to "".
        prompt = ""
    else:
        prompt, prompt_error = _read_prompt(args)
        if prompt_error:
            return None, False, prompt_error
    if second_opinion_record is None:
        return prompt, bool(args.write), None
    so_prompt = second_opinion_record.get(
        "prompt_summary"
    ) or second_opinion_record.get("job_id")
    so_envelope = second_opinion_record.get("envelope") or {}
    prompt = (
        "Second opinion requested on job {} (backend={}).\n"
        "Original task: {}\n"
        "Prior findings: {}\n\n{}".format(
            second_opinion_record["job_id"],
            second_opinion_record.get("backend"),
            so_prompt,
            json.dumps(so_envelope) if so_envelope else "(none)",
            prompt,
        )
    )
    return prompt, False, None


def _build_task_extra(
    args, entry, resume_record, second_opinion_record, model_tier, budget, write
):
    """Assemble the job-record `extra` dict for cmd_task, warning on unsupported resume."""
    resume_from_session_ref = None
    if resume_record is not None and not getattr(args, "fresh", False):
        if entry.get("resume"):
            resume_from_session_ref = resume_record.get("session_ref")
        else:
            print(
                "delegate: backend {!r} does not support resume; sending context fresh".format(
                    entry["id"]
                ),
                file=sys.stderr,
            )
    extra = {
        "kind": "task",
        "write": write,
        "model": model_tier,
        "budget_seconds": budget,
    }
    if resume_from_session_ref:
        extra["resume_from_session_ref"] = resume_from_session_ref
    if second_opinion_record is not None:
        extra["second_opinion_of"] = second_opinion_record["job_id"]
    return extra


_PROMPT_SUMMARY_MAX_CHARS = 2000


def _dispatch_task(store, args, entry, model_tier, extra, prompt, prompt_bytes):
    """Create the job record and either background-spawn it or run it synchronously."""
    extra = dict(extra)
    extra["prompt_summary"] = prompt[:_PROMPT_SUMMARY_MAX_CHARS]
    record = store.create(entry["id"], extra=extra)
    job_dir = store.job_dir(record["job_id"])
    _write_0600(os.path.join(job_dir, "prompt.txt"), prompt)

    print(
        "delegate: dispatching to backend {!r} (model={})".format(
            entry["id"], model_tier
        ),
        file=sys.stderr,
    )

    if args.background:
        _spawn_worker(store, record["job_id"])
        if args.json:
            print(
                json.dumps(
                    {
                        "job_id": record["job_id"],
                        "backend": entry["id"],
                        "state": "queued",
                    }
                )
            )
        else:
            print("job_id: {}".format(record["job_id"]))
            print("check: delegate.py status {}".format(record["job_id"]))
        return 0

    store.mutate(record["job_id"], lambda rec: dict(rec, state="running"))
    final = _run_backend_foreground(
        store, record["job_id"], entry, record, prompt_bytes
    )
    envelope = final.get("envelope") or {}
    envelope.setdefault("job_id", record["job_id"])

    if args.json:
        print(json.dumps(envelope))
    else:
        print("job_id: {}".format(record["job_id"]))
        print("backend: {}".format(entry["id"]))
        if extra.get("second_opinion_of"):
            print("second_opinion_of: {}".format(extra["second_opinion_of"]))
        print("outcome: {}".format(envelope.get("outcome")))
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))

    if final.get("state") == "timeout":
        return 1
    return 0 if envelope.get("outcome") != "failure" else 1


def cmd_task(args, backends, user_config, services_disabled):
    store = JobStore()
    resume_record, resume_error = _resolve_task_resume(
        store, args, backends, user_config
    )
    if resume_error:
        print(resume_error, file=sys.stderr)
        return 2

    second_opinion_record, so_error = _resolve_task_second_opinion(store, args)
    if so_error:
        print(so_error, file=sys.stderr)
        return 2

    entry, backend_error = _resolve_task_backend_entry(
        args, backends, user_config, resume_record
    )
    if backend_error:
        print(backend_error, file=sys.stderr)
        return 2

    _warn_if_second_opinion_same_backend(
        second_opinion_record, entry, backends, user_config, services_disabled
    )

    model_tier = resolve_model_tier(entry, user_config, args.model)
    ready_error, ready_code = _check_task_backend_ready(
        entry, user_config, services_disabled, model_tier
    )
    if ready_error:
        print(ready_error, file=sys.stderr)
        return ready_code

    prompt, write, prompt_error = _build_task_prompt(args, second_opinion_record)
    if prompt_error:
        print(prompt_error, file=sys.stderr)
        return 2
    prompt_bytes = prompt.encode("utf-8")
    limit_error = check_payload_limits(entry, prompt_bytes)
    if limit_error:
        print(f"delegate: {limit_error}", file=sys.stderr)
        return 2

    budget = resolve_budget(entry, user_config, args.budget)
    extra = _build_task_extra(
        args, entry, resume_record, second_opinion_record, model_tier, budget, write
    )
    return _dispatch_task(store, args, entry, model_tier, extra, prompt, prompt_bytes)


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class ReviewDiffError(Exception):
    """Raised when git invocations backing a review diff fail visibly."""


def _run_git(args_list, cwd):
    """Run git, treating exit codes 0/1 as success (1 = "differs", not error)."""
    try:
        proc = subprocess.run(
            ["git", *args_list], capture_output=True, text=True, cwd=cwd
        )
    except OSError as exc:
        raise ReviewDiffError(
            "git {} failed to launch: {}".format(" ".join(args_list), exc)
        ) from exc
    if proc.returncode not in (0, 1):
        raise ReviewDiffError(
            f"git {' '.join(args_list)} failed (exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()[:300]}"
        )
    return proc.stdout or ""


def _untracked_diff(cwd):
    """Synthesize diff text for untracked files (git diff HEAD omits these)."""
    listing = _run_git(["ls-files", "--others", "--exclude-standard"], cwd)
    parts = []
    for path in filter(None, listing.splitlines()):
        numstat = _run_git(
            ["diff", "--no-index", "--numstat", "--", "/dev/null", path], cwd
        )
        if numstat.strip().startswith("-\t-\t"):
            parts.append(f"Binary file {path} (untracked)\n")
            continue
        parts.append(_run_git(["diff", "--no-index", "--", "/dev/null", path], cwd))
    return "".join(parts)


def _scope_diff(diff_args, cwd):
    return _run_git(["diff", *diff_args], cwd) + _untracked_diff(cwd)


def assemble_review_diff(scope, base, cwd=None):
    """Build the review/gate diff: tracked+staged+untracked, fail open visibly.

    Raises ReviewDiffError (developer-visible) instead of silently returning
    an empty diff when any underlying git invocation fails.
    """
    if scope == "working-tree":
        return _scope_diff(["HEAD"], cwd)
    if scope == "branch":
        ref = base or "HEAD~1"
        return _scope_diff([f"{ref}...HEAD"], cwd)
    # auto: prefer working-tree changes; fall back to branch diff against base.
    diff = _scope_diff(["HEAD"], cwd)
    if diff.strip():
        return diff
    ref = base or "HEAD~1"
    return _scope_diff([f"{ref}...HEAD"], cwd)


def _build_review_prompt(args):
    """Build the review prompt (adversarial or standard) from the current diff."""
    diff = assemble_review_diff(args.scope, args.base, cwd=os.getcwd())
    if getattr(args, "adversarial", None) is not None:
        focus = " ".join(args.adversarial).strip()
        return (
            "Adversarial review: challenge the design of the following change.\n"
            "Focus: {}\n\n{}".format(focus or "(none specified)", diff)
        )
    return (
        f"Review the following change for correctness, safety, and quality.\n\n{diff}"
    )


def _dispatch_review(store, args, entry, model_tier, budget, prompt, prompt_bytes):
    """Create the review job record and either background-spawn it or run it synchronously."""
    extra = {
        "kind": "review",
        "write": False,
        "model": model_tier,
        "budget_seconds": budget,
    }
    record = store.create(entry["id"], extra=extra)
    job_dir = store.job_dir(record["job_id"])
    _write_0600(os.path.join(job_dir, "prompt.txt"), prompt)

    print(
        "delegate: dispatching review to backend {!r} (model={})".format(
            entry["id"], model_tier
        ),
        file=sys.stderr,
    )

    if args.background:
        _spawn_worker(store, record["job_id"])
        if args.json:
            print(
                json.dumps(
                    {
                        "job_id": record["job_id"],
                        "backend": entry["id"],
                        "state": "queued",
                    }
                )
            )
        else:
            print("job_id: {}".format(record["job_id"]))
            print("check: delegate.py status {}".format(record["job_id"]))
        return 0

    store.mutate(record["job_id"], lambda rec: dict(rec, state="running"))
    final = _run_backend_foreground(
        store, record["job_id"], entry, record, prompt_bytes
    )
    envelope = final.get("envelope") or {}

    findings = envelope.get("findings")
    if isinstance(findings, list):
        envelope["findings"] = sorted(
            findings,
            key=lambda f: _SEVERITY_RANK.get(
                (f or {}).get("severity"), len(_SEVERITY_RANK)
            ),
        )

    if args.json:
        print(json.dumps(envelope))
    else:
        print("backend: {}".format(entry["id"]))
        print("outcome: {}".format(envelope.get("outcome")))
        for finding in envelope.get("findings") or []:
            print(
                "[{}] {}".format(finding.get("severity", "?"), finding.get("text", ""))
            )
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))

    if final.get("state") == "timeout":
        return 1
    return 0 if envelope.get("outcome") != "failure" else 1


def cmd_review(args, backends, user_config, services_disabled):
    store = JobStore()
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        print(
            f"delegate: unknown backend {backend_name!r} (known: {known})",
            file=sys.stderr,
        )
        return 2

    model_tier = resolve_model_tier(entry, user_config, args.model)
    ready_error, ready_code = _check_task_backend_ready(
        entry, user_config, services_disabled, model_tier
    )
    if ready_error:
        print(ready_error, file=sys.stderr)
        return ready_code

    prompt = _build_review_prompt(args)
    prompt_bytes = prompt.encode("utf-8")
    limit_error = check_payload_limits(entry, prompt_bytes)
    if limit_error:
        print(f"delegate: {limit_error}", file=sys.stderr)
        return 2

    budget = resolve_budget(entry, user_config, args.budget)
    return _dispatch_review(
        store, args, entry, model_tier, budget, prompt, prompt_bytes
    )


def cmd_status(args):
    store = JobStore()
    if not args.job_id:
        rows = []
        for job_id in store.list_job_ids():
            try:
                rows.append(store.reap_if_dead(job_id))
            except (OSError, ValueError):
                continue
        if args.json:
            print(json.dumps(rows))
        else:
            for rec in rows:
                print(
                    "{}  {}  {}  {}".format(
                        rec["job_id"][:12],
                        rec.get("kind", "task"),
                        rec.get("backend"),
                        rec.get("state"),
                    )
                )
        return 0

    resolved, error = _resolve_job_id(store, args.job_id)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    deadline = (
        time.time() + (args.timeout or DEFAULT_BUDGET_SECONDS) if args.wait else None
    )
    record = store.reap_if_dead(resolved)
    while args.wait and record.get("state") not in TERMINAL_STATES:
        if deadline and time.time() >= deadline:
            break
        time.sleep(0.5)
        record = store.reap_if_dead(resolved)

    if args.json:
        print(json.dumps(record))
    else:
        print("job_id: {}".format(record["job_id"]))
        print("backend: {}".format(record.get("backend")))
        print("state: {}".format(record.get("state")))
    return 0


def cmd_result(args):
    store = JobStore()
    if not args.job_id:
        print("delegate: job id or prefix required", file=sys.stderr)
        return 2
    resolved, error = _resolve_job_id(store, args.job_id)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    record = store.reap_if_dead(resolved)
    if record.get("state") not in TERMINAL_STATES:
        print(
            f"delegate: still running; delegate.py status {resolved} --wait",
            file=sys.stderr,
        )
        return 1

    job_dir = store.job_dir(resolved)
    output_path = os.path.join(job_dir, "output.txt")
    envelope = record.get("envelope") or {
        "outcome": "failure",
        "error": record.get("error", "no envelope recorded"),
    }
    if args.json:
        payload = dict(envelope)
        payload["raw_output_path"] = output_path
        print(json.dumps(payload))
    else:
        print("outcome: {}".format(envelope.get("outcome")))
        if envelope.get("error"):
            print("error: {}".format(envelope["error"]))
        print(f"raw_output_path: {output_path}")
    return 0


def _terminate_job_processes(store, job_id, record):
    """Kill every process a cancel could leave running for `job_id`, across all
    race windows. Returns True if any live process/group was killed.

    Order: (1) the recorded backend pgid, (2) the worker itself — but ONLY when
    _worker_alive confirms via the lifetime flock that record['worker_pid'] is
    genuinely our worker, never a recycled pid. If the worker is confirmed dead
    the backend it may have forked is handled independently (record/crash-safe
    pgid); if it is mid-fork before locking, the atomic queued->running claim
    still stops the backend, so skipping the signal is safe. Callers then
    transition state and call _reap_raced_pgid for a pgid that may have been
    persisted after this initial read."""
    killed = False
    pgid = record.get("pgid")
    if pgid and _backend_alive(store, job_id):
        _kill_pgid(store, job_id, pgid)
        killed = True
    # Never SIGKILL a foreground job's worker_pid: it is the interactive CLI
    # process the user is running. Killing its backend group (above) stops the
    # work; the CLI then observes the terminal state and exits cleanly. Only a
    # background worker (a separate process we spawned) is safe to signal.
    if not record.get("foreground") and _worker_alive(store, job_id, record):
        try:
            os.kill(record["worker_pid"], signal.SIGKILL)
        except OSError as exc:
            err(
                "job {}: failed to kill worker pid {}: {}".format(
                    job_id, record["worker_pid"], exc
                )
            )
    return killed


def _reap_raced_pgid(store, job_id, before_pgid):
    """After the cancel state transition, kill a backend pgid that appeared in
    the race — from record.json (worker persisted it late) or the crash-safe
    <job_dir>/backend.pgid file (worker died in the Popen->persist window before
    it could persist). Returns True if a live group was killed."""
    post = store.read(job_id)
    raced = post.get("pgid")
    if raced and raced != before_pgid and _backend_alive(store, job_id):
        _kill_pgid(store, job_id, raced)
        return True
    if not post.get("pgid"):
        file_pgid = _read_pgid_file(store.job_dir(job_id))
        if file_pgid and _backend_alive(store, job_id):
            _kill_pgid(store, job_id, file_pgid)
            return True
    return False


def cmd_cancel(args):
    store = JobStore()
    if args.job_id:
        resolved, error = _resolve_job_id(store, args.job_id)
    else:
        resolved, error = _resolve_sole_active(store)
    if error:
        print(f"delegate: {error}", file=sys.stderr)
        return 2

    record = store.read(resolved)
    if record.get("state") in TERMINAL_STATES:
        if args.json:
            print(json.dumps(record))
        else:
            print(f"job_id: {resolved}")
            print("state: {} (already terminal, no-op)".format(record.get("state")))
        return 0

    before_pgid = record.get("pgid")
    was_alive = _terminate_job_processes(store, resolved, record)

    def _mark_cancelled(rec):
        if rec.get("state") in TERMINAL_STATES:
            return None
        rec["state"] = "cancelled"
        return rec

    record = store.mutate(resolved, _mark_cancelled)
    if _reap_raced_pgid(store, resolved, before_pgid):
        was_alive = True
    # Every backend for this job is now killed; erase the pgid tracking so no
    # later reap/status re-derives the now-dead pgid and SIGKILLs a recycled one.
    _clear_pgid_tracking(store, resolved)
    if args.json:
        payload = dict(record)
        payload["was_alive"] = was_alive
        print(json.dumps(payload))
    else:
        print(f"job_id: {resolved}")
        print("state: {}".format(record.get("state")))
        print(f"process_was_alive: {was_alive}")
    return 0


class ShortHelpParser(argparse.ArgumentParser):
    """ArgumentParser that exits 0 on --help/-h (argparse default) and exits
    2 with a usage message on argument errors, per the CLI exit-code
    contract (0/1/2/3)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(2)


TRANSCRIPT_PATH_ENV = "MANIFEST_TRANSCRIPT_PATH"
TRANSCRIPT_ROOTS = (
    os.path.expanduser("~/.claude/projects"),
    os.path.expanduser("~/.claude/transcripts"),
)


def _validate_transcript_source(path):
    """Canonicalize `path` and require it resolve under an allowed transcript
    root. Returns (real_path, None) on success, (None, error_message) on
    rejection. Path-traversal guard for `transfer --source` (T013)."""
    real = os.path.realpath(os.path.expanduser(path))
    for root in TRANSCRIPT_ROOTS:
        real_root = os.path.realpath(root)
        if real == real_root or real.startswith(real_root + os.sep):
            return real, None
    return None, (
        "source path {!r} does not resolve under an allowed transcript root "
        "({})".format(path, " or ".join(TRANSCRIPT_ROOTS))
    )


def _app_server_import(entry, source_path):
    """Short-lived direct `<backend executable> app-server` external-session
    import call. Executable comes from the registry entry's own `invoke`
    argv (never a hardcoded backend name) so this stays generic to any
    backend declaring `transfer.method == "app_server_import"` (FR-016).
    Returns (thread_id, None) or (None, error_message)."""
    invoke = entry.get("invoke") or []
    if not invoke:
        return None, "backend {!r} has no invoke command configured".format(entry["id"])
    exe = invoke[0]
    argv = [exe, "app-server"]
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "importExternalSession",
        "params": {"path": source_path},
    }
    try:
        proc = subprocess.run(
            argv,
            input=(json.dumps(request) + "\n").encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            timeout=30,
        )
    except FileNotFoundError:
        return None, "backend {!r} executable {!r} not found on PATH".format(
            entry["id"], exe
        )
    except subprocess.TimeoutExpired:
        return None, "app-server import for backend {!r} timed out after 30s".format(
            entry["id"]
        )
    except OSError as exc:
        return None, "app-server import for backend {!r} failed: {}".format(
            entry["id"], exc
        )

    raw = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    thread_id = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        result = obj.get("result")
        if isinstance(result, dict) and result.get("thread_id"):
            thread_id = result["thread_id"]
            break
        if obj.get("thread_id"):
            thread_id = obj["thread_id"]
            break

    if not thread_id:
        return None, (
            "app-server import for backend {!r} returned no thread id (output: {})".format(
                entry["id"], raw[:200]
            )
        )
    return thread_id, None


def cmd_resume_candidate(args, backends, user_config):
    """`resume-candidate` — report the newest resumable job for a backend so
    the delegate skill can offer continue-vs-fresh (T012)."""
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        sys.stderr.write(
            f"delegate: unknown backend {backend_name!r} (known: {known})\n"
        )
        return 2

    store = JobStore()
    record = None
    if entry.get("resume"):
        record = _find_last_job_for_backend(store, entry["id"])

    if record is None:
        result = {
            "available": False,
            "job_id": None,
            "backend": entry["id"],
            "session_ref": None,
            "age": None,
        }
    else:
        updated_at = record.get("updated_at") or record.get("created_at") or time.time()
        result = {
            "available": True,
            "job_id": record.get("job_id"),
            "backend": entry["id"],
            "session_ref": record.get("session_ref"),
            "age": max(0.0, time.time() - float(updated_at)),
        }

    if args.json:
        print(json.dumps(result))
    elif result["available"]:
        print(
            "resumable job {} on backend {} (age {:.0f}s)".format(
                result["job_id"], result["backend"], result["age"]
            )
        )
    else:
        print("no resumable job found for backend {}".format(entry["id"]))
    return 0


def _resolve_transfer_entry(args, backends, user_config):
    """Resolve the backend registry entry for `transfer`. Returns (entry, error_message)."""
    backend_name = args.backend or user_config.get("default_backend") or "codex"
    entry = resolve_backend(backends, backend_name)
    if entry is None:
        known = ", ".join(sorted(b["id"] for b in backends))
        return None, f"delegate: unknown backend {backend_name!r} (known: {known})\n"
    return entry, None


SESSIONS_CAPTURE_FILE = os.path.expanduser("~/.manifest/delegate/sessions.json")


def _session_captured_transcript(cwd=None):
    """Best-effort lookup of the most recent SessionStart-captured transcript
    path for `cwd`, written by session_hook.py's handle_session_start.

    Requires an exact canonical-workspace match (realpath) when `cwd` is
    supplied — fails closed (returns None) rather than leaking the most
    recent transcript from an unrelated workspace. Never raises.
    """
    try:
        with open(SESSIONS_CAPTURE_FILE, encoding="utf-8") as fh:
            sessions = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(sessions, dict) or not sessions:
        return None
    entries = [v for v in sessions.values() if isinstance(v, dict)]
    if not entries:
        return None
    if not cwd:
        return entries[-1].get("transcript_path")
    real_cwd = os.path.realpath(cwd)
    matching = [e for e in entries if os.path.realpath(e.get("cwd") or "") == real_cwd]
    if not matching:
        return None
    return matching[-1].get("transcript_path")


def _resolve_transfer_source(args):
    """Resolve and validate the transcript source path. Returns (real_source, error_message)."""
    source = (
        args.source
        or os.environ.get(TRANSCRIPT_PATH_ENV)
        or _session_captured_transcript(os.getcwd())
    )
    if not source:
        return None, (
            "delegate: --source required (no SessionStart-captured transcript "
            f"path found; set {TRANSCRIPT_PATH_ENV} or pass --source)\n"
        )
    real_source, path_error = _validate_transcript_source(source)
    if path_error:
        return None, f"delegate: {path_error}\n"
    return real_source, None


def _check_transfer_method(entry, args):
    """Verify the backend supports session import. Prints on failure. Returns exit code or None."""
    transfer_cfg = entry.get("transfer")
    if transfer_cfg is None:
        message = (
            "backend {!r} does not support session import; run "
            "`delegate.py task --backend {}` to re-send context fresh".format(
                entry["id"], entry["id"]
            )
        )
        if args.json:
            print(
                json.dumps(
                    {"backend": entry["id"], "supported": False, "message": message}
                )
            )
        else:
            print(f"delegate: {message}")
        return 1

    method = transfer_cfg.get("method")
    if method != "app_server_import":
        sys.stderr.write(
            "delegate: backend {!r} transfer method {!r} not recognized\n".format(
                entry["id"], method
            )
        )
        return 1
    return None


def _print_transfer_result(args, entry, thread_id, resume_cmd):
    """Print the transfer result as JSON or plain text."""
    if args.json:
        print(
            json.dumps(
                {
                    "backend": entry["id"],
                    "supported": True,
                    "thread_id": thread_id,
                    "resume_command": resume_cmd,
                }
            )
        )
    else:
        print("backend: {}".format(entry["id"]))
        print(f"thread_id: {thread_id}")
        print(f"resume: {resume_cmd}")


def cmd_transfer(args, backends, user_config):
    """`transfer` — session handover (FR-015): registry-driven, no
    backend-name branching (FR-016) (T013)."""
    entry, entry_error = _resolve_transfer_entry(args, backends, user_config)
    if entry_error:
        sys.stderr.write(entry_error)
        return 2

    real_source, source_error = _resolve_transfer_source(args)
    if source_error:
        sys.stderr.write(source_error)
        return 2

    method_exit = _check_transfer_method(entry, args)
    if method_exit is not None:
        return method_exit

    if not args.json:
        print(f"source: {real_source}")

    thread_id, import_error = _app_server_import(entry, real_source)
    if import_error:
        sys.stderr.write(f"delegate: {import_error}\n")
        return 1

    mapping = {"output_file": "<job-output-file>"}
    resume_argv = build_resume_argv(entry, thread_id, False, None, mapping)
    resume_cmd = " ".join(resume_argv)
    _print_transfer_result(args, entry, thread_id, resume_cmd)
    return 0


def _run_readiness_probe(argv, timeout=10):
    """Run a readiness probe argv; return (returncode, output).

    returncode is None when the binary is missing, -1 on timeout.
    """
    if not argv:
        return 0, ""
    try:
        proc = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()
    except FileNotFoundError:
        return None, ""
    except subprocess.TimeoutExpired:
        return -1, ""
    except OSError:
        return None, ""


def _init_readiness_row(backend_id):
    """Build the initial (pre-probe) readiness row shape."""
    return {
        "backend": backend_id,
        "state": "error",
        "version": None,
        "fix": "—",
        "identity": None,
        "probe_seconds": 0.0,
    }


def _probe_enabled_state(entry, user_config, services_disabled):
    """Check backend enablement. Returns a state/fix pair, or (None, None) if enabled."""
    enabled, layer = effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if enabled:
        return None, None
    if layer == "workspace services.yml":
        return (
            "disabled_workspace",
            "enable in ~/.claude/config/services.yml (workspace layer outranks user enable)",
        )
    return (
        "disabled_user",
        f"delegate.py setup with an enabled entry in delegation.json/.yml ({layer})",
    )


def _probe_retired_state(readiness):
    """Check the retired_check probe. Returns a state/fix pair, or (None, None) if not retired."""
    retired_check = readiness.get("retired_check")
    if not retired_check:
        return None, None
    rc, _out = _run_readiness_probe(retired_check, timeout=10)
    if rc == 0:
        return "retired", "backend retired; see registry notes"
    return None, None


def _probe_version_and_auth(backend_id, readiness, row):
    """Run version and auth probes, filling in `row` in place."""
    rc, out = _run_readiness_probe(readiness.get("version_cmd"), timeout=10)
    if rc is None or rc != 0:
        row["state"] = "error" if rc == -1 else "not_installed"
        row["fix"] = (
            "version probe timed out"
            if rc == -1
            else readiness.get("install_fix", f"install {backend_id}")
        )
        return
    row["version"] = out.splitlines()[0].strip() if out else None

    auth_rc, auth_out = _run_readiness_probe(
        readiness.get("auth_probe_cmd"), timeout=10
    )
    if auth_rc is None:
        row["state"] = "not_installed"
        row["fix"] = readiness.get("install_fix", f"install {backend_id}")
    elif auth_rc == -1:
        row["state"] = "error"
        row["fix"] = "auth probe timed out"
    elif auth_rc != 0:
        row["state"] = "not_authenticated"
        row["fix"] = readiness.get("login_fix", "login required")
    elif _looks_like_auth_error(auth_out):
        row["state"] = "not_authenticated"
        row["fix"] = readiness.get("login_fix", "login required")
        row["identity"] = auth_out or None
    else:
        row["state"] = "ready"
        row["fix"] = "—"
        row["identity"] = auth_out or None


_AUTH_ERROR_PATTERN = re.compile(
    r"not logged in|not authenticated|unauthorized|unauthenticated|"
    r"login required|please log ?in|please login|auth(?:entication)? error|"
    r"invalid (?:api key|token|credentials)|no (?:api key|credentials) found",
    re.IGNORECASE,
)


def _looks_like_auth_error(auth_out):
    """Detect an error string in an auth probe's output despite exit 0 (US2).

    Some backends' auth probes exit 0 even while printing a not-logged-in
    message (e.g. `devin auth status` — see parallel_agent.yml's devin note).
    Exit code alone is not a sufficient readiness signal; inspect content too.
    """
    if not auth_out:
        return False
    return bool(_AUTH_ERROR_PATTERN.search(auth_out))


def probe_backend_readiness(entry, user_config, services_disabled):
    """Probe one backend's readiness row (US2): state/version/fix/probe_seconds.

    Never blocks on interactive input (US2-AS3): every probe carries
    stdin=DEVNULL and a bounded timeout.
    """
    backend_id = entry["id"]
    readiness = entry.get("readiness", {})
    row = _init_readiness_row(backend_id)
    start = time.time()

    state, fix = _probe_enabled_state(entry, user_config, services_disabled)
    if state is None:
        state, fix = _probe_retired_state(readiness)
    if state is not None:
        row["state"], row["fix"] = state, fix
        row["probe_seconds"] = round(time.time() - start, 3)
        return row

    _probe_version_and_auth(backend_id, readiness, row)
    row["probe_seconds"] = round(time.time() - start, 3)
    return row


def _cmd_setup_gate_toggle(args, user_config=None):
    changes = {}
    if getattr(args, "enable_review_gate", False):
        changes["enabled"] = True
        if getattr(args, "gate_backend", None):
            changes["backend"] = args.gate_backend
    else:
        changes["enabled"] = False

    current = (user_config or {}).get("review_gate", {})
    budget = current.get(
        "budget_seconds", FACTORY_DEFAULTS["review_gate"]["budget_seconds"]
    )
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        budget = FACTORY_DEFAULTS["review_gate"]["budget_seconds"]
    changes["budget_seconds"] = max(1, min(budget, GATE_BUDGET_CAP_SECONDS))

    try:
        path, data = write_review_gate_config(changes)
    except RegistryError as exc:
        err(str(exc))
        return 2
    gate = data.get("review_gate", {})
    if getattr(args, "json", False):
        print(json.dumps({"path": path, "review_gate": gate}))
    else:
        state = "enabled" if gate.get("enabled") else "disabled"
        backend_note = (
            " (backend: {})".format(gate["backend"]) if gate.get("backend") else ""
        )
        print(f"review gate {state}{backend_note} — written to {path}")
    return 0


def _gate_allow(reason=None, json_mode=False, cause=None):
    """Emit the Stop-hook 'allow' outcome, optionally noting why the gate was skipped.

    `reason` is the detailed (possibly dynamic) explanation used for the
    legacy stderr/systemMessage output. `cause` is the coarse, stable label
    (gate disabled / stop-hook-active / no code edits / backend unready)
    reported in --json mode; it defaults to `reason` when omitted.
    """
    if reason:
        sys.stderr.write(f"delegate: review gate skipped: {reason}\n")
        if not json_mode:
            print(json.dumps({"systemMessage": f"review gate skipped: {reason}"}))
    if json_mode:
        print(
            json.dumps(
                {"decision": "allow", "reason": cause or reason or "gate disabled"}
            )
        )
    return 0


def _gate_resolve_backend(gate_cfg, backends, user_config, services_disabled):
    """Resolve and validate the gate backend. Returns (entry, error_reason)."""
    backend_id = gate_cfg.get("backend") or user_config.get("default_backend")
    entry = resolve_backend(backends, backend_id)
    if entry is None:
        return None, f"unknown gate backend {backend_id!r}"
    enabled, layer = effective_backend_enabled(
        entry["id"], user_config, services_disabled
    )
    if not enabled:
        return None, "backend {} disabled at {} layer".format(entry["id"], layer)
    argv_probe = build_invoke_argv(entry, write=False, model_tier=None, mapping={})
    missing = _executable_missing(argv_probe)
    if missing:
        return None, "backend {} unavailable ({})".format(entry["id"], missing)
    return entry, None


_GATE_PROMPT_INSTRUCTIONS = (
    "You are an adversarial code reviewer gating a Stop hook. Review the diff "
    "below for defects that must block the turn from ending: security "
    "vulnerabilities, correctness bugs, swallowed exceptions, and broken "
    "contracts. Do not make edits; only report findings.\n\n"
    "End your final message with exactly one fenced JSON block (```json ... ```), "
    "and nothing after it, matching this shape:\n"
    "```json\n"
    "{\n"
    '  "backend": "<your backend id>",\n'
    '  "model": "<model or null>",\n'
    '  "outcome": "success" | "partial" | "failure",\n'
    '  "attempted": "<what you reviewed>",\n'
    '  "changes": [],\n'
    '  "succeeded": [],\n'
    '  "failed": [],\n'
    '  "follow_ups": [],\n'
    '  "findings": [{"severity": "critical|high|medium|low|info", "text": "<finding>"}]\n'
    "}\n"
    "```\n"
    'Set "findings" to [] when the diff has no blocking issues. Every element of '
    '"findings" MUST have string "severity" and "text" fields.\n\n'
    "Diff to review:\n\n"
)


def _gate_build_prompt(entry):
    """Assemble and size-check the gate review prompt. Returns (prompt, prompt_bytes, error_reason)."""
    try:
        diff = assemble_review_diff("auto", None, cwd=None)
    except (OSError, ValueError, RuntimeError) as exc:
        return None, None, f"could not assemble review diff ({exc})"
    prompt = _GATE_PROMPT_INSTRUCTIONS + diff
    prompt_bytes = prompt.encode("utf-8")
    limit_error = check_payload_limits(entry, prompt_bytes)
    if limit_error:
        return None, None, limit_error
    return prompt, prompt_bytes, None


def _gate_validate_findings(envelope):
    """Validate the gate envelope's outcome/findings shape (G4).

    Returns (findings, error_reason). `error_reason` is set (findings is
    None) when the envelope is missing/malformed so the caller can surface
    an explicit systemMessage instead of silently allowing.
    """
    if envelope.get("outcome") not in ENVELOPE_OUTCOMES:
        return None, "gate review returned an invalid envelope (missing/bad outcome)"
    findings = envelope.get("findings", [])
    if not isinstance(findings, list):
        return None, "gate review returned malformed findings (not a list)"
    for item in findings:
        if not isinstance(item, dict):
            return None, "gate review returned malformed findings (non-object entry)"
        if not isinstance(item.get("severity"), str) or not isinstance(
            item.get("text"), str
        ):
            return None, "gate review returned malformed findings (bad field types)"
    return findings, None


def _gate_format_block(findings):
    """Format ranked findings into a Stop-hook block decision payload."""
    ranked = sorted(
        findings, key=lambda f: _SEVERITY_RANK.get(f.get("severity", "info"), 5)
    )
    lines = [
        "{}: {}".format(f.get("severity", "info"), f.get("text", "")) for f in ranked
    ]
    reason = (
        "Review gate found issues before this turn ends:\n- "
        + "\n- ".join(lines)
        + "\n\nDo not make any tool calls or edits in response to this. "
        "Relay these findings to the developer and ask how to proceed — "
        "developer decides."
    )
    return {"decision": "block", "reason": reason}


def cmd_gate(args, backends, user_config, services_disabled):
    """`gate` — Stop-hook review gate (US4): blocks the turn end on findings."""
    store = JobStore()
    json_mode = getattr(args, "json", False)

    if getattr(args, "stop_hook_active", False):
        return _gate_allow(json_mode=json_mode, cause="stop-hook-active")

    gate_cfg = dict(user_config.get("review_gate", {}))
    if getattr(args, "enable_review_gate_for_test", False):
        gate_cfg["enabled"] = True
    if not gate_cfg.get("enabled"):
        return _gate_allow(json_mode=json_mode, cause="gate disabled")

    try:
        edits_present = _finishing_turn_has_edits(args.transcript)
    except (OSError, ValueError) as exc:
        return _gate_allow(
            f"could not read transcript {args.transcript} ({exc})",
            json_mode=json_mode,
            cause="backend unready",
        )
    if not edits_present:
        return _gate_allow(json_mode=json_mode, cause="no code edits")

    entry, error_reason = _gate_resolve_backend(
        gate_cfg, backends, user_config, services_disabled
    )
    if error_reason:
        return _gate_allow(error_reason, json_mode=json_mode, cause="backend unready")

    prompt, prompt_bytes, error_reason = _gate_build_prompt(entry)
    if error_reason:
        return _gate_allow(error_reason, json_mode=json_mode, cause="backend unready")

    budget = min(
        resolve_budget(entry, user_config, gate_cfg.get("budget_seconds")),
        GATE_BUDGET_CAP_SECONDS,
    )
    return _gate_execute(
        store, entry, prompt, prompt_bytes, budget, json_mode, args.transcript
    )


def _gate_execute(store, entry, prompt, prompt_bytes, budget, json_mode, transcript):
    """Run the gate backend and turn its envelope into an allow/block
    decision. The job record is created here (not earlier in cmd_gate) so a
    gate that short-circuits on an early check never leaves a queued job
    behind (G8)."""
    record = store.create("gate", extra={"kind": "gate", "transcript": transcript})
    job_id = record["job_id"]
    _write_0600(os.path.join(store.job_dir(job_id), "prompt.txt"), prompt)

    def _claim_running(rec):
        rec["state"] = "running"
        rec["backend"] = entry["id"]
        rec["budget_seconds"] = budget
        return rec

    record = store.mutate(job_id, _claim_running)

    final = _run_backend_foreground(store, job_id, entry, record, prompt_bytes)
    if final.get("state") == "timeout":
        return _gate_allow(
            f"gate review timed out after {budget}s",
            json_mode=json_mode,
            cause="backend unready",
        )

    envelope = final.get("envelope") or {}
    if envelope.get("error"):
        return _gate_allow(
            "gate review failed ({})".format(envelope["error"]),
            json_mode=json_mode,
            cause="backend unready",
        )

    findings, error_reason = _gate_validate_findings(envelope)
    if error_reason:
        return _gate_allow(error_reason, json_mode=json_mode, cause="backend unready")
    if not findings:
        return _gate_allow(json_mode=json_mode, cause="no findings")

    print(json.dumps(_gate_format_block(findings)))
    return 0


def _finishing_turn_has_edits(transcript_path):
    """Deterministic finishing-turn edit detection per contracts/delegate-cli.md.

    The finishing turn is every entry after the last user message that is not a
    tool-result carrier. Returns True iff any assistant tool_use in that window
    names Edit, Write, MultiEdit, or NotebookEdit. Bash is deliberately not
    classified. Scanned in a SINGLE streaming pass holding only one line and a
    boolean at a time (no whole-transcript list), so a very long session cannot
    exhaust memory: a non-carrier user message resets the running edit flag; an
    edit tool_use after it sets it; the flag at EOF is the answer.
    """
    edit_tool_names = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

    def _is_tool_result_carrier(entry):
        content = entry.get("message", {}).get("content")
        if isinstance(content, list):
            return any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
        return False

    def _has_edit_tool_use(entry):
        content = entry.get("message", {}).get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(b, dict)
            and b.get("type") == "tool_use"
            and b.get("name") in edit_tool_names
            for b in content
        )

    edits_since_boundary = False
    with open(transcript_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = entry.get("type")
            if etype == "user" and not _is_tool_result_carrier(entry):
                edits_since_boundary = False  # a new finishing turn begins here
            elif etype == "assistant" and _has_edit_tool_use(entry):
                edits_since_boundary = True
    return edits_since_boundary


def cmd_setup(args, backends, user_config, services_disabled):
    if getattr(args, "enable_review_gate", False) or getattr(
        args, "disable_review_gate", False
    ):
        return _cmd_setup_gate_toggle(args, user_config)

    targets = backends
    if getattr(args, "backend", None):
        entry = resolve_backend(backends, args.backend)
        if entry is None:
            sys.stderr.write(
                "delegate: unknown backend {!r}; known backends: {}\n".format(
                    args.backend, ", ".join(b["id"] for b in backends)
                )
            )
            return 2
        targets = [entry]

    rows = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, len(targets))
    ) as pool:
        futures = [
            pool.submit(probe_backend_readiness, entry, user_config, services_disabled)
            for entry in targets
        ]
        for future in futures:
            rows.append(future.result())

    if args.json:
        print(json.dumps(rows))
        return 0

    print(f"{'backend':<12} {'state':<18} {'version':<9} fix")
    for row in rows:
        print(
            f"{row['backend']:<12} {row['state']:<18} "
            f"{row.get('version') or '—':<9} {row.get('fix') or '—'}"
        )
    return 0


_SUBCOMMAND_HELP = {
    "task": "Delegate a task (optionally --second-opinion, --write, --resume).",
    "review": "Run a standalone read-only review (optionally --adversarial).",
    "status": "Show a job's current state.",
    "result": "Print a job's normalized result envelope.",
    "cancel": "Cancel a queued/running job.",
    "setup": "Check backend readiness and write user config.",
    "transfer": "Transfer a session to another surface (backend-declared).",
    "gate": "Internal: invoked by the Stop hook for the review gate.",
    "resume-candidate": "Find the most recent resumable job for a backend.",
}
_IMPLEMENTED_SUBCOMMANDS = {
    "task",
    "review",
    "status",
    "result",
    "cancel",
    "transfer",
    "resume-candidate",
    "setup",
    "gate",
}


def _positive_int_arg(raw):
    """argparse `type=` for --budget: reject non-positive/non-integer values."""
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--budget must be an integer, got {raw!r}"
        ) from exc
    # Reuse the config-layer rule so the CLI and config agree on "positive int".
    if not _is_positive_int(value):
        raise argparse.ArgumentTypeError(
            f"--budget must be a positive integer, got {raw!r}"
        )
    return value


def _add_task_args(p):
    """Add `task` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--background", action="store_true", help="run detached, print job_id"
    )
    group.add_argument(
        "--wait", action="store_true", help="run in foreground (default)"
    )
    p.add_argument("--write", action="store_true", help="allow sandboxed writes")
    p.add_argument("--model", help="model tier")
    p.add_argument(
        "--budget", type=_positive_int_arg, help="budget in seconds (positive integer)"
    )
    resume_group = p.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume", metavar="JOB_ID", help="resume a prior job's session"
    )
    resume_group.add_argument(
        "--resume-last", action="store_true", help="resume the newest resumable job"
    )
    resume_group.add_argument(
        "--fresh", action="store_true", help="skip resume, start fresh"
    )
    p.add_argument(
        "--second-opinion",
        action="store_true",
        help="get a second opinion on a prior job",
    )
    p.add_argument("--of", metavar="JOB_ID", help="job id the second opinion is about")
    p.add_argument("--prompt-file", metavar="FILE", help="read the prompt from FILE")
    p.add_argument(
        "prompt", nargs="?", default=None, help="prompt text, or - for stdin"
    )


def _add_review_args(p):
    """Add `review` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    p.add_argument(
        "--adversarial",
        nargs="*",
        default=None,
        metavar="FOCUS",
        help="challenge-the-design review; optional free-text focus",
    )
    p.add_argument(
        "--base", metavar="REF", default=None, help="base ref to diff against"
    )
    p.add_argument(
        "--scope",
        choices=["auto", "working-tree", "branch"],
        default="auto",
        help="diff scope (default: auto)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--background", action="store_true", help="run detached, print job_id"
    )
    group.add_argument(
        "--wait", action="store_true", help="run in foreground (default)"
    )
    p.add_argument("--model", help="model tier")
    p.add_argument(
        "--budget", type=_positive_int_arg, help="budget in seconds (positive integer)"
    )


def _add_setup_args(p):
    """Add `setup` subcommand arguments."""
    p.add_argument("--backend", help="backend id or alias")
    p.add_argument(
        "--enable-review-gate",
        action="store_true",
        help="enable the finish-time review gate",
    )
    p.add_argument("--gate-backend", help="backend id for the review gate")
    p.add_argument(
        "--disable-review-gate",
        action="store_true",
        help="disable the finish-time review gate",
    )


def _add_subcommand_args(name, p):
    """Dispatch to the per-subcommand argument builder for `name`."""
    if name == "task":
        _add_task_args(p)
    elif name == "status":
        p.add_argument(
            "job_id", nargs="?", default=None, help="job id or unique prefix"
        )
        p.add_argument("--all", action="store_true", help="show all jobs")
        p.add_argument(
            "--wait", action="store_true", help="poll until terminal or timeout"
        )
        p.add_argument(
            "--timeout", type=int, default=None, help="max seconds to --wait"
        )
    elif name in ("result", "cancel"):
        p.add_argument(
            "job_id", nargs="?", default=None, help="job id or unique prefix"
        )
    elif name == "transfer":
        p.add_argument("--backend", help="backend id or alias")
        p.add_argument(
            "--source", metavar="TRANSCRIPT", help="transcript path to import"
        )
    elif name == "review":
        _add_review_args(p)
    elif name == "resume-candidate":
        p.add_argument("--backend", help="backend id or alias")
    elif name == "setup":
        _add_setup_args(p)
    elif name == "gate":
        p.add_argument(
            "--transcript",
            required=True,
            metavar="PATH",
            help="path to the session transcript JSONL",
        )
        p.add_argument(
            "--stop-hook-active",
            action="store_true",
            help="harness re-entry indicator (at-most-once)",
        )
        # Hidden: force the gate enabled without writing config, for smoke tests.
        p.add_argument(
            "--enable-review-gate-for-test", action="store_true", help=argparse.SUPPRESS
        )


def build_parser():
    """Build the top-level argparse parser and all delegate.py subcommands."""
    parser = ShortHelpParser(
        prog="delegate.py",
        description="Delegate tasks/reviews to a backend registry (codex, claude, antigravity).",
        add_help=True,
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable JSON output"
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    for name in SUBCOMMANDS:
        p = sub.add_parser(name, help=_SUBCOMMAND_HELP.get(name, ""))
        if name not in _IMPLEMENTED_SUBCOMMANDS:
            continue
        p.add_argument(
            "--json", action="store_true", help="machine-readable JSON output"
        )
        _add_subcommand_args(name, p)

    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "_worker":
        if len(argv) < 3:
            sys.stderr.write("delegate.py _worker: missing job_id/workspace_dir\n")
            return 2
        return cmd_worker(argv[1], argv[2])

    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        sys.stderr.write(
            "delegate: unrecognized arguments: {}\n".format(" ".join(unknown))
        )
        return 2
    if args.command is None:
        parser.print_help()
        return 0

    if args.command in ("task", "review", "status", "result", "cancel", "setup"):
        backends = load_registry_or_exit(_registry_path_override())
        user_config = load_user_config()
        services_disabled = load_services_disabled()
        if args.command == "setup":
            return cmd_setup(args, backends, user_config, services_disabled)
        if args.command == "task":
            return cmd_task(args, backends, user_config, services_disabled)
        if args.command == "review":
            return cmd_review(args, backends, user_config, services_disabled)
        if args.command == "status":
            return cmd_status(args)
        if args.command == "result":
            return cmd_result(args)
        if args.command == "cancel":
            return cmd_cancel(args)

    if args.command in ("transfer", "resume-candidate"):
        backends = load_registry_or_exit(_registry_path_override())
        user_config = load_user_config()
        if args.command == "transfer":
            return cmd_transfer(args, backends, user_config)
        if args.command == "resume-candidate":
            return cmd_resume_candidate(args, backends, user_config)

    if args.command == "gate":
        backends = load_registry_or_exit(_registry_path_override())
        user_config = load_user_config()
        services_disabled = load_services_disabled()
        return cmd_gate(args, backends, user_config, services_disabled)

    # Phase 2 only implements registry/config/job-store/envelope plumbing;
    # remaining subcommand behaviors are scaffolded stubs (Phase 3+ user stories).
    sys.stderr.write(f"delegate.py {args.command}: not yet implemented (Phase 3+)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
