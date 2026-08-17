"""Durable state for resumable Codex uninstallation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from manifest_agent.adapters.codex_catalog import receipt_identity
from manifest_agent.models import HarnessReceipt
from manifest_agent.state import _write_private_json_atomic


def uninstall_saga_path(receipt: HarnessReceipt, env: Mapping[str, str] | None) -> Path:
    values = os.environ if env is None else env
    state = Path(
        values.get(
            "XDG_STATE_HOME",
            str(Path(values.get("HOME", str(Path.home()))) / ".local/state"),
        )
    )
    return state / "manifest" / "codex-uninstall" / f"{receipt_identity(receipt)}.json"


def load_or_create_uninstall_saga(
    path: Path, receipt: HarnessReceipt, plugin_ids: Sequence[str]
) -> dict[str, Any]:
    identity = receipt_identity(receipt)
    if path.exists():
        document = json.loads(path.read_text(encoding="utf-8"))
        if not _valid_saga(document, identity, plugin_ids):
            raise ValueError("schema or receipt identity mismatch")
        return document
    document = {
        "schema_version": 1,
        "receipt_identity": identity,
        "plugin_ids": list(plugin_ids),
        "steps": {},
    }
    _write_private_json_atomic(path, document)
    return document


def _valid_saga(document: Any, identity: str, plugin_ids: Sequence[str]) -> bool:
    return (
        isinstance(document, dict)
        and set(document)
        == {"schema_version", "receipt_identity", "plugin_ids", "steps"}
        and document.get("schema_version") == 1
        and document.get("receipt_identity") == identity
        and tuple(document.get("plugin_ids", ())) == tuple(plugin_ids)
        and isinstance(document.get("steps"), dict)
        and all(value in {"prepared", "done"} for value in document["steps"].values())
    )


def checkpoint_uninstall(
    path: Path, saga: dict[str, Any], step: str, phase: str
) -> None:
    saga["steps"][step] = phase
    _write_private_json_atomic(path, saga)
