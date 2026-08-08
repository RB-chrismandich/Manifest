"""Auto-discovered fixtures for the delegate CLI-subprocess suite.

`env_factory` is defined in _delegate_harness.py, next to the stub-backend
helpers (`_make_stub_launcher`, `_stub_entry`) it is built from. Re-exporting it
here is what makes pytest inject it by name.

Why the re-export rather than a plain import in each test module: importing a
fixture and then naming it as a test parameter rebinds the module-level name in
every signature, which ruff reports as F811 (redefined-while-unused) once per
test — 35 of them across this suite. Pytest resolves conftest fixtures by name
without an import, so the test modules import only the plain helpers.

Named `env_factory` here and nowhere else; tests/python/agents/conftest.py is a
separate, narrower conftest and does not shadow this one.
"""

from _delegate_harness import env_factory

__all__ = ["env_factory"]
