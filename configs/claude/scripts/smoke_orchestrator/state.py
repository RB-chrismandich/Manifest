"""StateManager — named state across steps and runs (T009).

Resolves ``${state.<name>}`` (captured this run) and ``${env.<NAME>}`` (process
environment) references just before a step executes (FR-012). Sensitive values
come only from the environment and are never persisted (FR-013); a sensitive
reference with no environment source is a hard error (no plaintext fallback).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from pathlib import Path
from typing import Any

from .redact import Redactor

_REF = re.compile(r"\$\{(state|env)\.([A-Za-z0-9_]+)\}")


class StateError(RuntimeError):
    pass


class StateManager:
    def __init__(
        self, persist: bool = False, state_dir: str | os.PathLike | None = None
    ) -> None:
        self._mem: dict[str, Any] = {}
        self._persist = persist
        self._state_dir = Path(state_dir) if state_dir else _default_state_dir()

    # --- resolution ---------------------------------------------------------
    def has(self, name: str) -> bool:
        return name in self._mem

    def satisfies(self, needs: list[str]) -> bool:
        return all(self.has(n) for n in (needs or []))

    def resolve_value(
        self, raw: str, redactor: Redactor, sensitive: bool = False
    ) -> str:
        """Substitute every ${state.*}/${env.*} reference in a string."""

        def _sub(m: re.Match) -> str:
            kind, key = m.group(1), m.group(2)
            if kind == "state":
                if key not in self._mem:
                    raise StateError(f"unresolved state reference: ${{state.{key}}}")
                val = str(self._mem[key])
                if (
                    sensitive
                ):  # in a sensitive step, every resolved ref is treated as secret
                    redactor.register(val)
                return val
            # env
            if key not in os.environ:
                raise StateError(f"unresolved env reference: ${{env.{key}}}")
            val = os.environ[key]
            if sensitive:
                redactor.register(val)
            return val

        return _REF.sub(_sub, raw)

    def resolve(self, obj: Any, redactor: Redactor, sensitive: bool = False) -> Any:
        """Recursively resolve references inside strings/lists/dicts."""
        if isinstance(obj, str):
            return self.resolve_value(obj, redactor, sensitive)
        if isinstance(obj, list):
            return [self.resolve(v, redactor, sensitive) for v in obj]
        if isinstance(obj, dict):
            return {k: self.resolve(v, redactor, sensitive) for k, v in obj.items()}
        return obj

    # --- capture ------------------------------------------------------------
    def capture(
        self,
        name: str,
        value: Any,
        *,
        app: str,
        sensitive: bool = False,
        scope: str = "run",
        redactor: Redactor | None = None,
    ) -> None:
        self._mem[name] = value
        if sensitive and redactor is not None:
            redactor.register(value)
        # Persisted scope writes only NON-secret values (FR-013).
        if self._persist and scope == "persisted" and not sensitive:
            self._write_persisted(app, name, value)

    # --- persistence (non-secret only) --------------------------------------
    def _state_file(self, app: str) -> Path:
        return self._state_dir / f"{app}.json"

    def load_persisted(self, app: str) -> None:
        path = self._state_file(app)
        if path.exists():
            self._mem.update(json.loads(path.read_text(encoding="utf-8")))

    def _write_persisted(self, app: str, name: str, value: Any) -> None:
        path = self._state_file(app)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Owner-only: persisted (non-secret) ids/urls still shouldn't be world-readable
        # on a shared CI host (Tier-1 review B-3, defense-in-depth).
        with contextlib.suppress(OSError):
            path.parent.chmod(0o700)
        # ⚡ Bolt: Single read avoids TOCTOU and double filesystem overhead vs path.exists() + read_text()
        try:
            raw = path.read_text(encoding="utf-8")
            current = json.loads(raw)
        except FileNotFoundError:
            current = {}
        current[name] = value
        path.write_text(json.dumps(current), encoding="utf-8")
        with contextlib.suppress(OSError):
            path.chmod(0o600)


def _default_state_dir() -> Path:
    root = os.environ.get("MANIFEST_STATE_ROOT", os.path.expanduser("~/.manifest"))
    return Path(root) / "smoke" / "state"
