"""Load the release-owned policy archive without index or home-runtime access."""

import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import sys
from pathlib import Path

POLICY_ARCHIVE = Path(__file__).resolve().parent / "vendor/model-policy.zip"
POLICY_SHA256 = "d8fba2a689783826809843f4897fca069d626596f11fab541fb2ff19a9b27730"
_POLICY_DISTRIBUTION = "manifest-model-policy"
_POLICY_VERSION = "0.1.0"


def _trusted_editable_policy_roots():
    """Directories an editable policy distribution may legitimately live in.

    Two, and only two. The repo checkout that owns this script, for a developer
    running `plugins/.../delegate.py` in place; and the deployed
    `~/.claude/scripts` tree, which is what `~/.claude/pyproject.toml` pins as an
    editable source and therefore what every `uv sync` of the home runtime
    recreates. The home path is anchored to `~`, not to `__file__`, because the
    installed plugin copy sits under `~/.claude/plugins/cache/...` and has no
    repo above it to derive an anchor from.

    This adds no trust root: the gate already re-execs `~/.claude/.venv`, and
    `~/.claude/scripts` is the same bootstrap-owned tree beside it.
    """
    return (
        (
            Path(__file__).resolve().parents[2]
            / "configs/claude/scripts/manifest_model_policy"
        ).resolve(),
        Path(os.path.expanduser("~/.claude/scripts/manifest_model_policy")).resolve(),
    )


def _editable_source_metadata(distribution, files, module_origin):
    """True when the distribution is an editable install of a trusted source."""
    for source_policy in _trusted_editable_policy_roots():
        if module_origin != source_policy / "__init__.py":
            continue
        try:
            direct_url = json.loads(distribution.read_text("direct_url.json") or "")
            return (
                direct_url.get("url") == source_policy.as_uri()
                and direct_url.get("dir_info", {}).get("editable") is True
                and any(str(item) == "_manifest_model_policy.pth" for item in files)
            )
        except (AttributeError, json.JSONDecodeError, ValueError):
            # Unreadable or non-object metadata is untrusted, not absent: the
            # caller turns a False here into a hard exit, while letting the
            # exception reach its own handler would report the distribution as
            # merely missing and allow `--help` to answer normally.
            return False
    return False


def _trusted_model_policy_distribution():
    """Import and pin policy only from the exact distribution-owned package."""
    try:
        distribution = importlib.metadata.distribution(_POLICY_DISTRIBUTION)
        spec = importlib.util.find_spec("manifest_model_policy")
        if distribution.version != _POLICY_VERSION or spec is None or not spec.origin:
            return None, True
        module_origin = Path(spec.origin).resolve()
        if module_origin == POLICY_ARCHIVE / "manifest_model_policy/__init__.py":
            if hashlib.sha256(POLICY_ARCHIVE.read_bytes()).hexdigest() != POLICY_SHA256:
                return None, True
            return importlib.import_module("manifest_model_policy"), False
        distribution_root = Path(str(distribution.locate_file(""))).resolve()
        interpreter_root = Path(sys.prefix).resolve()
        files = distribution.files or ()
        owned_policy_files = {
            Path(str(distribution.locate_file(item))).resolve()
            for item in files
            if item.parts and item.parts[0] == "manifest_model_policy"
        }
        # A distribution rooted outside this interpreter is not the runtime's
        # own copy, so it stays untrusted here and must qualify via the editable
        # source-metadata path below. `is_relative_to` states that directly;
        # catching relative_to's ValueError said the same thing but read as a
        # swallowed error.
        installed_runtime = distribution_root.is_relative_to(interpreter_root) and (
            module_origin in owned_policy_files
        )
        source_metadata = _editable_source_metadata(distribution, files, module_origin)
        if not installed_runtime and not source_metadata:
            return None, True
        module = importlib.import_module("manifest_model_policy")
        imported_origin = Path(module.__file__ or "").resolve()
        if imported_origin != module_origin:
            sys.modules.pop("manifest_model_policy", None)
            return None, True
        return module, False
    except (ImportError, importlib.metadata.PackageNotFoundError, OSError, ValueError):
        return None, False


def load_bundled_policy():
    """Use only byte-pinned bundle code; never mask an existing policy module."""
    if importlib.util.find_spec("manifest_model_policy") is not None:
        raise ImportError("refusing to replace an existing model policy")
    if hashlib.sha256(POLICY_ARCHIVE.read_bytes()).hexdigest() != POLICY_SHA256:
        raise ImportError("bundled model policy digest mismatch")
    sys.path.append(str(POLICY_ARCHIVE))
    importlib.invalidate_caches()
    return importlib.import_module("manifest_model_policy")


def ensure_policy():
    """Apply the same trust gate for console, module, and script entry points."""
    policy, invalid = _trusted_model_policy_distribution()
    if invalid:
        raise ImportError("invalid manifest-model-policy distribution")
    return policy if policy is not None else load_bundled_policy()
