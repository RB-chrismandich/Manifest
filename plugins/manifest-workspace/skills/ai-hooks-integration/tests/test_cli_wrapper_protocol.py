#!/usr/bin/env python3
"""Response parsing and post-hook protocol contracts for CLI wrappers."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from runtime.cli_wrapper import generate_wrapper


class TestWrapperResponseProtocol(unittest.TestCase):
    def test_python_wrapper_whitespace_pre_hook_fails_without_traceback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cli = root / "cli"
            marker = root / "ran"
            cli.write_text(f"#!/bin/sh\ntouch {marker}\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), " ", template="python")
            )
            wrapper.chmod(0o700)
            proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 126, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertFalse(marker.exists())

    def test_python_wrapper_whitespace_post_hook_preserves_cli_status(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cli = root / "cli"
            cli.write_text("#!/bin/sh\nexit 37\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), post_hook=" ", template="python")
            )
            wrapper.chmod(0o700)
            proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 37, proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)

    def test_bash_multiple_json_responses_cannot_bypass_deny(self):
        for output in (
            '{"decision":"deny"}\n{"decision":"allow"}',
            '{"decision":"allow"}\n{"decision":"deny"}',
        ):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "cli-ran"
                hook.write_text(
                    "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' '"
                    + output.replace("'", "'\\''")
                    + "'\n"
                )
                cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template="bash")
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertFalse(marker.exists())

    def test_empty_pre_hook_output_allows_every_template(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook = root / "hook"
                cli = root / "cli"
                marker = root / "markers"
                hook.write_text("#!/bin/sh\ncat >/dev/null\nexit 0\n")
                cli.write_text(f"#!/bin/sh\necho cli >> '{marker}'\nexit 0\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template=template)
                )
                wrapper.chmod(0o700)
                proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(marker.read_text().splitlines(), ["cli"])

    def test_invalid_pre_hook_json_fails_closed_all_templates(self):
        for template in ("bash", "python", "minimal"):
            for output in (
                "not-json",
                "[]",
                '{"decision":"allow"}\n{"decision":"deny"}',
                '{"decision":"deny"}',
            ):
                with (
                    self.subTest(template=template, output=output),
                    tempfile.TemporaryDirectory() as td,
                ):
                    root = Path(td)
                    hook = root / "hook"
                    cli = root / "cli"
                    marker = root / "cli-ran"
                    hook.write_text(
                        "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' '"
                        + output.replace("'", "'\\''")
                        + "'\n"
                    )
                    cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                    hook.chmod(0o700)
                    cli.chmod(0o700)
                    wrapper = root / "wrapper"
                    wrapper.write_text(
                        generate_wrapper("test", str(cli), str(hook), template=template)
                    )
                    wrapper.chmod(0o700)
                    proc = subprocess.run(
                        [str(wrapper)], capture_output=True, text=True
                    )
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertFalse(marker.exists())

    def test_nonstandard_json_constants_fail_closed_all_templates(self):
        for template in ("bash", "python", "minimal"):
            for output in (
                '{"value":NaN}',
                '{"value":Infinity}',
                '{"value":-Infinity}',
            ):
                with (
                    self.subTest(template=template, output=output),
                    tempfile.TemporaryDirectory() as td,
                ):
                    root = Path(td)
                    hook, cli, marker = root / "hook", root / "cli", root / "cli-ran"
                    hook.write_text(
                        "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' '" + output + "'\n"
                    )
                    cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
                    hook.chmod(0o700)
                    cli.chmod(0o700)
                    wrapper = root / "wrapper"
                    wrapper.write_text(
                        generate_wrapper("test", str(cli), str(hook), template=template)
                    )
                    wrapper.chmod(0o700)
                    proc = subprocess.run(
                        [str(wrapper)], capture_output=True, text=True
                    )
                    self.assertEqual(proc.returncode, 1, proc.stderr)
                    self.assertFalse(marker.exists())

    def test_successful_hook_invalid_utf8_fails_closed_all_templates(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                hook, cli, marker = root / "hook", root / "cli", root / "cli-ran"
                hook.write_bytes(
                    b"#!/usr/bin/env python3\nimport sys\n"
                    b"sys.stdin.buffer.read()\nsys.stdout.buffer.write(b'\\xff')\n"
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
                self.assertNotIn(b"Traceback", proc.stderr)
                self.assertFalse(marker.exists())

    def test_bash_rejects_hook_output_with_nul_byte(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook, cli, marker = root / "hook", root / "cli", root / "cli-ran"
            hook.write_bytes(
                b'#!/bin/sh\ncat >/dev/null\nprintf \'{"decision":"allow"}\\000\'\n'
            )
            cli.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), str(hook), template="bash")
            )
            wrapper.chmod(0o700)
            proc = subprocess.run([str(wrapper)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertFalse(marker.exists())


class TestPostHookProtocol(unittest.TestCase):
    def test_post_hook_receives_cli_status_for_all_templates(self):
        for template in ("bash", "python", "minimal"):
            with self.subTest(template=template), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                capture = root / "post-input"
                hook = root / "hook"
                hook.write_text(
                    "#!/bin/sh\n"
                    'if [ "$1" = "--cli" ]; then printf "%s\\n" "$@" > "$CAPTURE"; '
                    'else cat > "$CAPTURE"; fi\n'
                )
                cli = root / "cli"
                cli.write_text("#!/bin/sh\nexit 37\n")
                hook.chmod(0o700)
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), "", str(hook), template=template)
                )
                wrapper.chmod(0o700)
                env = dict(os.environ, CAPTURE=str(capture))
                proc = subprocess.run(
                    [str(wrapper), "alpha"], capture_output=True, text=True, env=env
                )
                self.assertEqual(proc.returncode, 37, proc.stderr)
                if template == "minimal":
                    self.assertEqual(
                        capture.read_text().splitlines(),
                        [
                            "--cli",
                            "test",
                            "--phase",
                            "post",
                            "--exit-code",
                            "37",
                            "--",
                            "alpha",
                        ],
                    )
                else:
                    payload = json.loads(capture.read_text())
                    self.assertEqual(
                        payload,
                        {
                            "cli": "test",
                            "args": ["alpha"],
                            "cwd": os.getcwd(),
                            "exit_code": 37,
                            "phase": "post",
                        },
                    )

    def test_minimal_preserves_positional_pre_hook_protocol(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            capture, hook, cli = root / "calls", root / "hook", root / "cli"
            hook.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$@" >> "$CAPTURE"\n'
                'if [ "$4" = "pre" ]; then printf \'{"decision":"allow"}\\n\'; fi\n'
            )
            cli.write_text("#!/bin/sh\nexit 0\n")
            hook.chmod(0o700)
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), str(hook), str(hook), template="minimal"
                )
            )
            wrapper.chmod(0o700)
            env = dict(os.environ, CAPTURE=str(capture))
            proc = subprocess.run(
                [str(wrapper), "alpha", "beta"], capture_output=True, text=True, env=env
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                capture.read_text().splitlines(),
                [
                    "--cli",
                    "test",
                    "--phase",
                    "pre",
                    "--",
                    "alpha",
                    "beta",
                    "--cli",
                    "test",
                    "--phase",
                    "post",
                    "--exit-code",
                    "0",
                    "--",
                    "alpha",
                    "beta",
                ],
            )
