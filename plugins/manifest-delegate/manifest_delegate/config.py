"""manifest-delegate: config."""

import json
import os
import re

from . import constants, jobstore, registry

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
    env_dir = os.environ.get(constants.CONFIG_DIR_ENV)
    if env_dir:
        dirs.append(env_dir)
    dirs.append(constants.XDG_CONFIG_DIR)
    # Legacy bootstrap home, last: Stage 6 (#789) deletes it, and searching it
    # after XDG means that deletion degrades to the new location rather than
    # silently reverting every user to factory defaults.
    dirs.append(constants.HOME_CONFIG_DIR)
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
    """Resolve the user's delegation.{json,yml} per D3.

    Precedence: explicit_dir > $MANIFEST_CONFIG_DIR > $XDG_CONFIG_HOME/manifest
    > ~/.claude/config (legacy, retired by Stage 6 / #789).
    Within a directory: delegation.json always wins if present; otherwise
    delegation.yml is honored only when PyYAML is importable. Any parse
    failure is reported (never raised) and factory defaults are returned —
    this is a deliberate divergence from agents-config's ConfigError (D3).
    """
    report = reporter or (lambda msg: constants.err(msg))
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
        raise registry.RegistryError(
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
    jobstore._atomic_write_0600(yaml_path, content)
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
            raise registry.RegistryError(
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
    jobstore._atomic_write_0600(json_path, content)
    return json_path, data


def write_review_gate_config(changes, explicit_dir=None, reporter=None):
    """Write review_gate.* changes to the user config per D3.

    Canonical write target: delegation.json (created with factory defaults +
    the change when no config exists). An existing delegation.yml is updated
    in place only when PyYAML is importable; a .yml present without PyYAML is
    reported unreadable and delegation.json is written and takes precedence.
    Returns (path_written, dict_written).
    """
    report = reporter or (lambda msg: constants.err(msg))
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


def load_model_policy(config_dir=None):
    """Read the shared tier registry and fallback defaults as one mapping."""
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
        return data if isinstance(data, dict) else {}
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
