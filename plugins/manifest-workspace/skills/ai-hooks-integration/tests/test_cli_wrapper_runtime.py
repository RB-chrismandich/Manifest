#!/usr/bin/env python3
"""Runtime status, argument, and timeout contracts for generated CLI wrappers."""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from runtime.cli_wrapper import generate_wrapper


class TestWrapperIntegration(unittest.TestCase):
    """Integration tests for wrapper functionality."""

    def test_generated_bash_is_valid_syntax(self):
        """Generated bash should have valid syntax."""
        script = generate_wrapper(
            cli_name="test",
            original_path="/bin/test",
            pre_hook="/hook",
            template="bash",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(script)
            f.flush()

            import subprocess

            result = subprocess.run(
                ["bash", "-n", f.name],
                capture_output=True,
            )
            os.unlink(f.name)

            self.assertEqual(result.returncode, 0, f"Syntax error: {result.stderr}")

    def test_generated_python_is_valid_syntax(self):
        """Generated python should have valid syntax."""
        script = generate_wrapper(
            cli_name="test",
            original_path="/bin/test",
            pre_hook="/hook",
            template="python",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script)
            f.flush()

            import subprocess

            result = subprocess.run(
                [sys.executable, "-m", "py_compile", f.name],
                capture_output=True,
            )
            os.unlink(f.name)

            self.assertEqual(result.returncode, 0, f"Syntax error: {result.stderr}")

    def test_pre_hook_exit_status_blocks_all_templates(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "markers"
                hook.write_text(f"#!/bin/sh\necho hook >> '{marker}'\nexit 23\n")
                cli.write_text(f"#!/bin/sh\necho cli >> '{marker}'\nexit 37\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper(
                        "test", str(cli), str(hook), str(hook), template=template
                    )
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 23, proc.stderr)
                self.assertEqual(marker.read_text().splitlines(), ["hook"])


class TestHookCommandFailureStatuses(unittest.TestCase):
    """Verify hook execution failures block the wrapped CLI."""

    def test_missing_hook_command_returns_127_and_blocks_all_templates(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                missing_hook = root / "missing-hook"
                cli = root / "cli"
                marker = root / "cli-ran"
                cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper(
                        "test", str(cli), str(missing_hook), template=template
                    )
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True)
                self.assertEqual(proc.returncode, 127, proc.stderr)
                self.assertFalse(marker.exists())

    def test_non_executable_hook_returns_126_and_blocks_cli(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "cli-ran"
                hook.write_text("#!/bin/sh\nexit 0\n")
                cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                hook.chmod(0o600)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template=template)
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True)
                self.assertEqual(proc.returncode, 126, proc.stderr)
                self.assertFalse(marker.exists())

    def test_non_ascii_whitespace_is_rejected_all_templates(self):
        invalid_outputs = {
            "nbsp_only": b"\xc2\xa0",
            "nbsp_prefix": b'\xc2\xa0{"decision":"allow"}',
            "nbsp_suffix": b'{"decision":"allow"}\xc2\xa0',
        }
        for template in ("bash", "python", "minimal"):
            for case, output in invalid_outputs.items():
                with (
                    self.subTest(template=template, case=case),
                    tempfile.TemporaryDirectory() as td,
                ):
                    root = Path(td)
                    hook = root / "hook"
                    cli = root / "cli"
                    marker = root / "cli-ran"
                    hook.write_text(
                        "#!/usr/bin/env python3\nimport sys\n"
                        f"sys.stdout.buffer.write({output!r})\n"
                    )
                    cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                    hook.chmod(0o700)
                    cli.chmod(0o700)
                    wrapper = root / "wrapper"
                    wrapper.write_text(
                        generate_wrapper("test", str(cli), str(hook), template=template)
                    )
                    wrapper.chmod(0o700)
                    proc = subprocess.run([str(wrapper)], capture_output=True)
                    self.assertNotEqual(proc.returncode, 0, proc.stderr)
                    self.assertFalse(marker.exists())

    def test_cli_status_survives_post_hook_failure_all_templates(self):
        for template, cli_status in (
            ("bash", 37),
            ("python", 37),
            ("minimal", 37),
            ("bash", 0),
            ("python", 0),
            ("minimal", 0),
        ):
            with (
                self.subTest(template=template, cli_status=cli_status),
                tempfile.TemporaryDirectory() as td,
            ):
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "markers"
                hook.write_text(
                    f"#!/bin/sh\nread input || true\necho post >> '{marker}'\nexit 19\n"
                )
                cli.write_text(
                    f"#!/bin/sh\necho cli >> '{marker}'\nexit {cli_status}\n"
                )
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), "", str(hook), template=template)
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, cli_status, proc.stderr)
                self.assertEqual(marker.read_text().splitlines(), ["cli", "post"])

    def test_minimal_pre_hook_inherits_stdin_and_positional_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook = root / "hook"
            cli = root / "cli"
            marker = root / "markers"
            received = root / "stdin"
            arguments = root / "arguments"
            hook.write_text(
                f"#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" > '{arguments}'\n"
                f"cat > '{received}'\n"
                'printf \'{"decision":"allow"}\'\n'
            )
            cli.write_text(f"#!/bin/sh\necho cli >> '{marker}'\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), str(hook), template="minimal")
            )
            wrapper.chmod(0o700)
            caller_stdin = b"synthetic caller input\\n"
            proc = subprocess.run(
                [str(wrapper), "first", "two words"],
                input=caller_stdin,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(received.read_bytes(), caller_stdin)
            self.assertEqual(
                arguments.read_text().splitlines(),
                ["--cli", "test", "--phase", "pre", "--", "first", "two words"],
            )
            self.assertEqual(marker.read_text().splitlines(), ["cli"])

    def test_minimal_post_hook_inherits_stdin_and_positional_arguments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook = root / "hook"
            cli = root / "cli"
            received = root / "stdin"
            arguments = root / "arguments"
            hook.write_text(
                f"#!/bin/sh\n"
                f"printf '%s\\n' \"$@\" > '{arguments}'\n"
                f"cat > '{received}'\n"
            )
            cli.write_text("#!/bin/sh\nexit 0\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), "", str(hook), template="minimal")
            )
            wrapper.chmod(0o700)
            caller_stdin = b"post-hook caller input\\n"
            proc = subprocess.run(
                [str(wrapper), "first", "two words"],
                input=caller_stdin,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(received.read_bytes(), caller_stdin)
            self.assertEqual(
                arguments.read_text().splitlines(),
                [
                    "--cli",
                    "test",
                    "--phase",
                    "post",
                    "--exit-code",
                    "0",
                    "--",
                    "first",
                    "two words",
                ],
            )


class TestWrapperTimeouts(unittest.TestCase):
    def test_bash_timeout_returns_124_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook = root / "hook"
            cli = root / "cli"
            hook.write_text("#!/bin/sh\nsleep 3\n")
            cli.write_text("#!/bin/sh\nexit 0\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), str(hook), template="bash", hook_timeout=1
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.run(
                [str(wrapper)], capture_output=True, text=True, timeout=5
            )
            self.assertEqual(proc.returncode, 124, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_python_timeout_returns_124_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook = root / "hook"
            cli = root / "cli"
            hook.write_text("#!/bin/sh\nexec sleep 3\n")
            cli.write_text("#!/bin/sh\nexit 0\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), str(hook), template="python", hook_timeout=1
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.run(
                [str(wrapper)], capture_output=True, text=True, timeout=5
            )
            self.assertEqual(proc.returncode, 124, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_timeout_terminates_descendant_processes(self):
        for template in ("bash", "python", "minimal"):
            for phase in ("pre", "post"):
                with (
                    self.subTest(template=template, phase=phase),
                    tempfile.TemporaryDirectory() as td,
                ):
                    root = Path(td)
                    hook = root / "hook"
                    cli = root / "cli"
                    descendant_marker = root / "descendant-ran"
                    hook.write_text(
                        f"#!/bin/sh\n(sleep 1.5; touch '{descendant_marker}') &\nexec sleep 5\n"
                    )
                    cli.write_text("#!/bin/sh\nexit 0\n")
                    hook.chmod(0o700)
                    cli.chmod(0o700)
                    wrapper = root / "wrapper"
                    wrapper.write_text(
                        generate_wrapper(
                            "test",
                            str(cli),
                            str(hook) if phase == "pre" else "",
                            str(hook) if phase == "post" else "",
                            template=template,
                            hook_timeout=1,
                        )
                    )
                    wrapper.chmod(0o700)
                    proc = subprocess.run(
                        [str(wrapper)], capture_output=True, text=True, timeout=5
                    )
                    self.assertEqual(
                        proc.returncode, 124 if phase == "pre" else 0, proc.stderr
                    )
                    time.sleep(2)
                    self.assertFalse(descendant_marker.exists())

    def test_minimal_missing_hook_preserves_127_and_blocks_cli(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "cli-ran"
            cli = root / "cli"
            cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), str(root / "missing-hook"), template="minimal"
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 127, proc.stderr)
            self.assertFalse(marker.exists())

    def test_signal_termination_maps_to_shell_status(self):
        for template in ("bash", "python"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "cli-ran"
                hook.write_text("#!/bin/sh\nkill -TERM 0\nexec sleep 5\n")
                cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template=template)
                )
                wrapper.chmod(0o700)
                proc = subprocess.run(
                    [str(wrapper)], capture_output=True, text=True, timeout=5
                )
                self.assertEqual(proc.returncode, 143, proc.stderr)
                self.assertFalse(marker.exists())

    def test_invalid_utf8_hook_output_preserves_nonzero_status(self):
        for template in ("bash", "python"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "cli-ran"
                hook.write_bytes(
                    b"#!/bin/sh\nprintf '\\377'\nprintf '\\376' >&2\nexit 23\n"
                )
                cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template=template)
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True, timeout=5)
                self.assertEqual(proc.returncode, 23, proc.stderr)
                self.assertFalse(marker.exists())
                self.assertNotIn(b"Traceback", proc.stderr)
