"""Root pytest conftest: keep test runs from writing bytecode into the repo.

pytest resolves this repo's rootdir from the [tool.pytest.ini_options] table in
pyproject.toml, so this file is loaded first for EVERY invocation — CI, the
pr-smoke mirror, and a bare `python3 -m pytest <path>` alike — before any test
module or conftest below it is imported. That is the only hook that reaches the
skill-local suite at .apm/skills/ai-hooks-integration/tests/, which lives
outside `testpaths` and is invoked by path.

Why it matters there specifically: ~/.claude/skills is owned by apm, and apm
declines to adopt a directory holding files it did not place. pytest's assertion
rewriter caches a .pyc per collected test module and the interpreter caches one
per imported runtime module, so one unguarded run left __pycache__/ under
.apm/skills/ai-hooks-integration/{tests,scripts,scripts/runtime}. Those are
gitignored — CI green, `git status` clean — and then deploy silently skipped the
whole skill. tests/bats/skill_bytecode_hygiene.bats is the gate.

Same fix as the `-B` on the hook spawn sites in the skill's own
scripts/install_all.py and scripts/runtime/unified_hook.py, and the
sys.dont_write_bytecode in configs/claude/scripts/constitution_{check,hook}.py:
the process that starts the import decides, because by the time an imported
module could set the flag its own .pyc is already on disk.
"""

import sys

sys.dont_write_bytecode = True
