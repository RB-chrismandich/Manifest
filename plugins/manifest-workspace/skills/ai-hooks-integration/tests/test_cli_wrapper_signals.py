#!/usr/bin/env python3
"""Signal and cancellation contracts for generated Python CLI wrappers."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from runtime.cli_wrapper import generate_wrapper


class _ProcessGroupTestHelpers:
    """Shared readiness and cleanup helpers for process-group tests."""

    def _wait_for_file(self, path: Path, process: subprocess.Popen[bytes]) -> bool:
        deadline = time.monotonic() + 3
        while not path.exists() and process.poll() is None:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return path.exists()

    def _kill_hook_group_from_pid_file(self, pid_file: Path) -> None:
        try:
            process_group = int(pid_file.read_text())
        except FileNotFoundError:
            return
        with suppress(ProcessLookupError):
            os.killpg(process_group, signal.SIGKILL)


@unittest.skipUnless(os.name == "posix", "process-group behavior requires POSIX")
class TestPythonWrapperSignals(_ProcessGroupTestHelpers, unittest.TestCase):
    """Verify cancellation lifecycle and signal scope in generated wrappers."""

    def test_sigterm_during_popen_launch_kills_and_reaps_hook_group(self):
        """A signal received before Popen returns must still reap the hook group."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook = root / "hook"
            marker = root / "late-marker"
            hook.write_text(
                '#!/bin/sh\n(sleep 0.4; touch "$MARKER") &\nexec sleep 10\n'
            )
            hook.chmod(0o700)
            cli = root / "cli"
            cli.write_text("#!/bin/sh\nexit 0\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper("test", str(cli), str(hook), template="python")
            )
            wrapper.chmod(0o700)

            sitecustomize = root / "sitecustomize.py"
            sitecustomize.write_text(
                "import os, signal, subprocess\n"
                "_real_popen = subprocess.Popen\n"
                "def _interrupt_after_child(*args, **kwargs):\n"
                "    process = _real_popen(*args, **kwargs)\n"
                "    if args and args[0] and os.path.basename(args[0][0]) == 'hook':\n"
                "        os.kill(os.getpid(), signal.SIGTERM)\n"
                "    return process\n"
                "subprocess.Popen = _interrupt_after_child\n"
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)
            env["MARKER"] = str(marker)
            proc = subprocess.run(
                [sys.executable, str(wrapper)],
                capture_output=True,
                env=env,
                timeout=5,
            )
            time.sleep(0.6)
            self.assertEqual(proc.returncode, 143, proc.stderr)
            self.assertFalse(marker.exists(), "hook descendant survived cancellation")
            self.assertNotIn(b"Traceback", proc.stderr)

    def test_python_cancellation_kills_signal_ignoring_hook_descendants(self):
        """SIGINT and SIGTERM must kill descendants that ignore both signals."""
        for signum in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signum=signum), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                marker = root / "late-marker"
                hook_pid = root / "hook.pid"
                hook = root / "hook"
                hook.write_text(
                    "#!/bin/sh\n"
                    "trap '' INT TERM\n"
                    f"echo $$ > '{hook_pid}'\n"
                    f"(sleep 0.5; touch '{marker}') >/dev/null 2>&1 &\n"
                    "exec sleep 10\n"
                )
                hook.chmod(0o700)
                cli = root / "cli"
                cli.write_text("#!/bin/sh\nexit 0\n")
                cli.chmod(0o700)
                wrapper = root / "wrapper"
                wrapper.write_text(
                    generate_wrapper("test", str(cli), str(hook), template="python")
                )
                wrapper.chmod(0o700)
                proc = subprocess.Popen(
                    [str(wrapper)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                try:
                    self.assertTrue(
                        self._wait_for_file(hook_pid, proc), "hook did not start"
                    )
                    proc.send_signal(signum)
                    _, stderr = proc.communicate(timeout=5)
                    self.assertEqual(proc.returncode, 128 + signum, stderr)
                    self.assertNotIn(b"Traceback", stderr)
                    time.sleep(0.7)
                    self.assertFalse(marker.exists(), "hook descendant survived")
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.communicate()
                    self._kill_hook_group_from_pid_file(hook_pid)

    def test_python_cli_signal_after_pre_hook_uses_default_handling(self):
        """The original CLI must not inherit the hook-only signal handlers."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            started = root / "cli.started"
            pre_hook = root / "pre-hook"
            pre_hook.write_text('#!/bin/sh\nprintf \'{"decision":"allow"}\'\n')
            pre_hook.chmod(0o700)
            cli = root / "cli"
            cli.write_text(f"#!/bin/sh\ntouch '{started}'\nexec sleep 10\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), pre_hook=str(pre_hook), template="python"
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.Popen(
                [sys.executable, str(wrapper)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                self.assertTrue(
                    self._wait_for_file(started, proc), "original CLI did not start"
                )
                os.killpg(proc.pid, signal.SIGTERM)
                _, stderr = proc.communicate(timeout=3)
                self.assertEqual(proc.returncode, -signal.SIGTERM, stderr)
                self.assertNotIn(b"Traceback", stderr)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)

    def test_python_post_hook_cancellation_preserves_signal_status(self):
        """A post-hook cancellation must not be downgraded to the CLI status."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            hook_pid = root / "hook.pid"
            hook = root / "hook"
            hook.write_text(f"#!/bin/sh\necho $$ > '{hook_pid}'\nexec sleep 10\n")
            hook.chmod(0o700)
            cli = root / "cli"
            cli.write_text("#!/bin/sh\nexit 0\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test", str(cli), post_hook=str(hook), template="python"
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.Popen(
                [sys.executable, str(wrapper)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                self.assertTrue(
                    self._wait_for_file(hook_pid, proc), "post-hook did not start"
                )
                proc.send_signal(signal.SIGTERM)
                _, stderr = proc.communicate(timeout=3)
                self.assertEqual(proc.returncode, 128 + signal.SIGTERM, stderr)
                self.assertNotIn(b"Traceback", stderr)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate()
                self._kill_hook_group_from_pid_file(hook_pid)


@unittest.skipUnless(os.name == "posix", "process-group behavior requires POSIX")
class TestShellWrapperSignals(_ProcessGroupTestHelpers, unittest.TestCase):
    """Verify Bash and minimal wrappers reap hooks when cancelled."""

    def _assert_hook_cancellation(
        self, template: str, phase: str, signum: signal.Signals
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "late-marker"
            hook_pid = root / "hook.pid"
            hook = root / "hook"
            hook.write_text(
                "#!/bin/sh\n"
                "trap '' INT TERM\n"
                f"echo $$ > '{hook_pid}'\n"
                f"(sleep 0.5; touch '{marker}') >/dev/null 2>&1 &\n"
                "exec sleep 10\n"
            )
            hook.chmod(0o700)
            cli = root / "cli"
            cli.write_text("#!/bin/sh\nexit 0\n")
            cli.chmod(0o700)
            wrapper = root / "wrapper"
            wrapper.write_text(
                generate_wrapper(
                    "test",
                    str(cli),
                    pre_hook=str(hook) if phase == "pre" else "",
                    post_hook=str(hook) if phase == "post" else "",
                    template=template,
                )
            )
            wrapper.chmod(0o700)
            proc = subprocess.Popen(
                [str(wrapper)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            try:
                self.assertTrue(
                    self._wait_for_file(hook_pid, proc), f"{phase}-hook did not start"
                )
                # Repeated wrapper signals must preserve the first signal status.
                deadline = time.monotonic() + 0.02
                proc.send_signal(signum)
                while proc.poll() is None and time.monotonic() < deadline:
                    proc.send_signal(signum)
                    time.sleep(0.001)
                _, stderr = proc.communicate(timeout=5)
                time.sleep(0.7)
                self.assertFalse(marker.exists(), "hook descendant survived")
                self.assertEqual(proc.returncode, 128 + signum, stderr)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)
                self._kill_hook_group_from_pid_file(hook_pid)

    def test_bash_and_minimal_cancellation_cleans_pre_and_post_hooks(self):
        for template in ("bash", "minimal"):
            for phase in ("pre", "post"):
                for signum in (signal.SIGINT, signal.SIGTERM):
                    with self.subTest(template=template, phase=phase, signum=signum):
                        self._assert_hook_cancellation(template, phase, signum)
