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
_REEXEC_SENTINEL = "MANIFEST_DELEGATE_RUNTIME_REEXEC"


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


def _trusted_home_source_policy():
    """Load the exact deployed source tree when no distribution is installed."""
    source_policy = _trusted_editable_policy_roots()[1]
    source_init = source_policy / "__init__.py"
    if not source_init.is_file():
        return None, False

    spec = importlib.util.find_spec("manifest_model_policy")
    if spec is None:
        sys.path.insert(0, str(source_policy.parent))
        importlib.invalidate_caches()
        spec = importlib.util.find_spec("manifest_model_policy")
    if spec is None or not spec.origin:
        return None, True
    if Path(spec.origin).resolve() != source_init:
        return None, True
    trusted_runtime = Path(os.path.expanduser("~/.claude/.venv/bin/python"))
    if trusted_runtime.is_file() and os.access(trusted_runtime, os.X_OK):
        # Origin checks still reject shadows before re-exec, but source alone
        # must not bypass the home runtime's installed distribution metadata.
        return None, False
    try:
        # Keep the qualified source policy; supply only its missing dependency
        # from the same byte-pinned archive used by standalone installations.
        if importlib.util.find_spec("yaml") is None:
            _add_bundled_policy_path()
            try:
                importlib.import_module("yaml")
            finally:
                # Do not expose the archive's policy distribution metadata
                # alongside the trusted source on subsequent trust checks.
                sys.path.remove(str(POLICY_ARCHIVE))
        module = importlib.import_module("manifest_model_policy")
    except ModuleNotFoundError as error:
        # The source origin is already trusted. A missing external dependency
        # means this interpreter is incomplete, so let the entry point re-exec
        # into the trusted home runtime rather than report policy tampering.
        if error.name and not (
            error.name == "manifest_model_policy"
            or error.name.startswith("manifest_model_policy.")
        ):
            return None, False
        return None, True
    except (ImportError, OSError, ValueError):
        return None, True
    if Path(module.__file__ or "").resolve() != source_init:
        sys.modules.pop("manifest_model_policy", None)
        return None, True
    return module, False


def _trusted_editable_policy_metadata(distribution, files, module_origin):
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
    except importlib.metadata.PackageNotFoundError:
        return _trusted_home_source_policy()
    try:
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
        installed_runtime = (
            distribution_root.is_relative_to(interpreter_root)
            and module_origin in owned_policy_files
        )
        source_metadata = _trusted_editable_policy_metadata(
            distribution, files, module_origin
        )
        if not installed_runtime and not source_metadata:
            return None, True
        module = importlib.import_module("manifest_model_policy")
        imported_origin = Path(module.__file__ or "").resolve()
        if imported_origin != module_origin:
            sys.modules.pop("manifest_model_policy", None)
            return None, True
        return module, False
    except (ImportError, OSError, ValueError):
        return None, False


def _add_bundled_policy_path():
    """Expose release-owned policy dependencies only after digest validation."""
    if hashlib.sha256(POLICY_ARCHIVE.read_bytes()).hexdigest() != POLICY_SHA256:
        raise ImportError("bundled model policy digest mismatch")
    sys.path.append(str(POLICY_ARCHIVE))
    importlib.invalidate_caches()


def load_bundled_policy():
    """Use only byte-pinned bundle code; never mask an existing policy module."""
    if importlib.util.find_spec("manifest_model_policy") is not None:
        raise ImportError("refusing to replace an existing model policy")
    _add_bundled_policy_path()
    return importlib.import_module("manifest_model_policy")


def ensure_policy():
    """Apply the same trust gate for console, module, and script entry points."""
    policy, invalid = _trusted_model_policy_distribution()
    if invalid:
        raise ImportError("invalid manifest-model-policy distribution")
    return policy if policy is not None else load_bundled_policy()


def ensure_runtime_policy(entry_point):
    """Qualify policy for an executable, re-executing that entry point if needed."""
    policy, invalid = _trusted_model_policy_distribution()
    if policy is not None:
        return policy
    # Keep the symlink: resolving a venv's bin/python loses its site-packages.
    trusted_runtime = Path(os.path.expanduser("~/.claude/.venv/bin/python"))
    runtime_override = os.environ.get("MANIFEST_RUNTIME_PYTHON")
    if runtime_override:
        override = Path(runtime_override).expanduser()
        if not override.is_absolute() or override.resolve(
            strict=False
        ) != trusted_runtime.resolve(strict=False):
            sys.stderr.write(
                "delegate.py: rejected untrusted MANIFEST_RUNTIME_PYTHON override.\n"
            )
            sys.exit(2)
    if invalid:
        sys.stderr.write(
            "delegate.py: trusted Manifest runtime has an invalid "
            "manifest-model-policy distribution.\n"
        )
        sys.exit(2)
    if os.environ.get(_REEXEC_SENTINEL) == "1":
        sys.stderr.write(
            "delegate.py: re-exec into ~/.claude/.venv did not provide "
            "manifest-model-policy; re-run ./bootstrap.sh to converge the "
            "runtime.\n"
        )
        sys.exit(2)
    if trusted_runtime.is_file() and os.access(trusted_runtime, os.X_OK):
        os.environ[_REEXEC_SENTINEL] = "1"
        os.execv(
            str(trusted_runtime),
            [str(trusted_runtime), os.path.abspath(entry_point), *sys.argv[1:]],
        )
    try:
        return load_bundled_policy()
    except (ImportError, OSError) as error:
        sys.stderr.write(f"delegate.py: bundled model policy unavailable: {error}\n")
        sys.exit(2)
