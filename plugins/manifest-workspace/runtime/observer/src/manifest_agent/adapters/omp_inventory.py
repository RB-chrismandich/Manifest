"""OMP inventory compatibility exports and receipt hashing helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from manifest_agent.codex_plugin_backup import (
    CodexPluginBackupError,
    plugin_tree_sha256,
)
from manifest_agent.omp_readonly.inventory import OMP_MARKETPLACE as OMP_MARKETPLACE
from manifest_agent.omp_readonly.inventory import OmpInventoryError as OmpInventoryError
from manifest_agent.omp_readonly.inventory import (
    cache_directory_name as cache_directory_name,
)
from manifest_agent.omp_readonly.inventory import (
    cross_checked_plugin as cross_checked_plugin,
)
from manifest_agent.omp_readonly.inventory import omp_native_root as omp_native_root
from manifest_agent.omp_readonly.inventory import plugin_cli_rows as plugin_cli_rows
from manifest_agent.omp_readonly.inventory import plugin_path as plugin_path
from manifest_agent.omp_readonly.inventory import (
    read_installed_plugins as read_installed_plugins,
)
from manifest_agent.omp_readonly.inventory import read_marketplaces as read_marketplaces
from manifest_agent.omp_readonly.inventory import read_object as read_object
from manifest_agent.omp_readonly.inventory import (
    read_runtime_document as read_runtime_document,
)
from manifest_agent.omp_readonly.inventory import regular_chain as regular_chain
from manifest_agent.omp_readonly.inventory import runtime_name as runtime_name


def skill_file_path(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("[Skill file: ") and line.endswith("]"):
            return line[len("[Skill file: ") : -1]
    return None


def directory_sha256(path: Path) -> str:
    regular_chain(path)
    try:
        return plugin_tree_sha256(path)
    except (OSError, ValueError, CodexPluginBackupError) as error:
        raise OmpInventoryError(f"native tree is unreadable: {path}") from error


def document_sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
