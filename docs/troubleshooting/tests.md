# Python Tests Fail to Collect

> Import and collection errors in the pytest suite.

## Python Tests Fail to Collect

Run the Python suite as:

```bash
PYTHONNOUSERSITE=1 uv run pytest tests/python/ -m "not native"
```

Both parts matter, and each masks a different failure as a code error.

### `ModuleNotFoundError: No module named 'manifest_model_policy'`

Cause: `uv run --project configs/claude pytest` resolves `pytest` from the
**system** interpreter, not the project venv, so the venv's editable installs
are invisible. The package imports fine under `uv run --project configs/claude
python -c 'import manifest_model_policy'`, which makes this look like a
dependency bug rather than an interpreter mismatch.

Confirm it by checking any traceback or warning path for a system prefix such
as `/Library/Frameworks/Python.framework/...`. Fix: run `uv run pytest` from
the repository root, without `--project`.

### `ImportError: ... incompatible architecture (have 'arm64', need 'x86_64')`

Cause: a package in the user site directory (`~/Library/Python/<ver>/lib/...`)
shadows the venv copy — `rpds`, pulled in by `jsonschema`, is the usual one on
Apple Silicon. Fix: prefix with `PYTHONNOUSERSITE=1`.

### Mutation-testing a guard

`uv run` re-syncs the environment before the command, which silently reverts any
mutation applied to an installed distribution. To flip installed state and
observe a test fail, bypass the sync:

```bash
PYTHONNOUSERSITE=1 ./.venv/bin/python -m pytest <target>
```

---

---

[← Troubleshooting](README.md)
