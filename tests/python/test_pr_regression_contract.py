from __future__ import annotations

import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = (
    REPO_ROOT
    / "plugins/manifest-workspace/skills/pr-smoke/scripts/run_pr_regression.sh"
)
REAL_GIT = shutil.which("git")
REAL_BASH = shutil.which("bash")
REAL_PYTHON = sys.executable


class PrRegressionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.target = self.base / "target"
        self.home = self.base / "home"
        self.bin = self.base / "bin"
        self.target.mkdir()
        self.home.mkdir()
        self.bin.mkdir()
        if REAL_GIT is None or REAL_BASH is None:
            self.fail("git and bash are required for runner contract tests")
        for name, source in (
            ("git", REAL_GIT),
            ("bash", REAL_BASH),
            ("python3", REAL_PYTHON),
        ):
            (self.bin / name).symlink_to(source)
        for name in ("markdownlint-cli2", "bats", "shellcheck"):
            stub = self.bin / name
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(0o755)
        subprocess.run(
            [REAL_GIT, "init", "-q"], cwd=self.target, check=True, timeout=10
        )
        self.env = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / "config"),
            "XDG_DATA_HOME": str(self.home / "data"),
            "XDG_STATE_HOME": str(self.home / "state"),
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHONPATH": sysconfig.get_path("purelib"),
        }

    def run_runner(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [REAL_BASH, str(RUNNER), *args],
            cwd=self.target,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )

    def write_test(self, relative: str, source: str) -> None:
        path = self.target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def test_missing_local_lint_scripts_warn(self) -> None:
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(
            "WARN (missing tests/lint/check_array_expansion.sh)", result.stdout
        )
        self.assertIn(
            "WARN (missing tests/lint/check_bats_assertions.sh)", result.stdout
        )
        self.assertNotIn("| empty-array expansion lint | FAIL", result.stdout)

    def test_present_local_lint_script_failure_is_fail(self) -> None:
        self.write_test("tests/lint/check_array_expansion.sh", "#!/bin/sh\nexit 7\n")
        path = self.target / "tests/lint/check_array_expansion.sh"
        path.chmod(0o755)
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("| empty-array expansion lint | FAIL |", result.stdout)

    def test_root_tests_directory_is_discovered(self) -> None:
        self.write_test(
            "tests/test_calc.py", "def test_calculation():\n    assert 2 + 2 == 4\n"
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("1 passed", result.stdout)
        self.assertIn("| python tests | PASS |", result.stdout)

    def test_failing_root_test_dominates_missing_script_warnings(self) -> None:
        self.write_test("tests/test_calc.py", "def test_failure():\n    assert False\n")
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("test_failure", result.stdout)
        self.assertRegex(result.stdout, r"1 failed")

    def test_tests_python_layout_is_discovered(self) -> None:
        self.write_test(
            "tests/python/test_target.py", "def test_target():\n    assert True\n"
        )
        result = self.run_runner()
        self.assertIn("1 passed", result.stdout)
        self.assertIn("| python tests | PASS |", result.stdout)

    def test_configured_testpaths_is_honored(self) -> None:
        (self.target / "pytest.ini").write_text(
            "[pytest]\ntestpaths = suite\n", encoding="utf-8"
        )
        self.write_test(
            "suite/test_configured.py", "def test_configured():\n    assert False\n"
        )
        result = self.run_runner()
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("test_configured.py", result.stdout)
        self.assertIn("| python tests | FAIL |", result.stdout)

    def test_missing_pytest_is_warn_not_fail(self) -> None:
        python = self.bin / "python3"
        python.unlink()
        python.write_text(
            '#!/bin/sh\nexec "$PR_SMOKE_TEST_REAL_PYTHON" -S "$@"\n',
            encoding="utf-8",
        )
        python.chmod(0o755)
        self.env["PR_SMOKE_TEST_REAL_PYTHON"] = REAL_PYTHON
        self.env["PYTHONPATH"] = ""

        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("| python tests | WARN (missing pytest) |", result.stdout)
        self.assertNotIn("| python tests | FAIL", result.stdout)

    def test_no_tests_is_warn_not_fail(self) -> None:
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("WARN (no Python tests collected)", result.stdout)
        self.assertNotIn("| python tests | FAIL", result.stdout)

    def test_quick_skips_failing_python_suite(self) -> None:
        self.write_test("tests/test_calc.py", "def test_failure():\n    assert False\n")
        result = self.run_runner("--quick")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("python tests", result.stdout)
        self.assertNotIn("test_failure", result.stdout)


if __name__ == "__main__":
    unittest.main()
