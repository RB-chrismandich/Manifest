#!/usr/bin/env python3
"""Bounded backend process-output capture tests."""

import json
import os
import sys

import pytest
from _delegate_inproc import delegate
from manifest_model_policy import FailureClass, FailureEvidence, classify_failure


class TestSpawnBackendStdoutCapture:
    @pytest.mark.parametrize("size", (49_152, 49_153, 50_000, 65_536, 70_000))
    def test_stdout_head_tail_capture_has_no_overlap(self, tmp_path, size):
        stub = tmp_path / "sized-output.py"
        stub.write_text(
            "import sys\n"
            f"sys.stdout.buffer.write(bytes(65 + i % 26 for i in range({size})))\n",
            encoding="utf-8",
        )
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        expected = bytes(65 + index % 26 for index in range(size))

        captured = delegate._spawn_backend(
            {"input": {"transport": "devnull"}},
            [sys.executable, str(stub)],
            b"",
            str(job_dir),
            budget=10,
        )

        _returncode, stdout, _stderr, *_rest, truncated = captured
        retained = stdout.encode("utf-8")
        if size <= 65_536:
            assert retained == expected
            assert truncated is False
        else:
            assert retained == expected[:16_384] + expected[-49_152:]
            assert truncated is True

    def test_argv_prompt_is_redacted_from_job_log(self, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        secret_prompt = "review private-token-123"

        captured = delegate._spawn_backend(
            {"input": {"transport": "argv"}},
            [
                sys.executable,
                "-c",
                "pass",
                "--print",
                secret_prompt,
                "--model",
                "mini",
            ],
            secret_prompt.encode("utf-8"),
            str(job_dir),
            budget=10,
        )

        assert captured[0] == 0
        log = (job_dir / "job.log").read_text(encoding="utf-8")
        assert secret_prompt not in log
        assert "<prompt>" in log

    def test_symlinked_provider_output_path_is_rejected(self, tmp_path):
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        target = tmp_path / "foreign.txt"
        target.write_text("must survive", encoding="utf-8")
        (job_dir / "output.txt").symlink_to(target)

        with pytest.raises(ValueError, match="backend output path"):
            delegate._spawn_backend(
                {"input": {"transport": "stdin"}},
                [sys.executable, "-c", "print('unused')"],
                b"",
                str(job_dir),
                budget=10,
            )

        assert target.read_text(encoding="utf-8") == "must survive"

    def test_stub_stdout_only_envelope_survives_output_file_combine(self, tmp_path):
        """Preserve stdout envelopes when a provider output file stays empty."""
        envelope = {
            "backend": "stub",
            "model": "auto",
            "outcome": "success",
            "attempted": "did the thing",
            "changes": [],
            "succeeded": ["ok"],
            "failed": [],
            "follow_ups": [],
        }
        stub = tmp_path / "stub.py"
        stub.write_text(
            "import sys\n"
            f"sys.stdout.write('```json\\n' + {json.dumps(envelope)!r} + '\\n```\\n')\n"
        )
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        argv = [
            sys.executable,
            str(stub),
            "--output-last-message",
            os.path.join(str(job_dir), "output.txt"),
            "-",
        ]
        entry = {"input": {"transport": "stdin"}}
        (
            returncode,
            combined,
            stderr,
            _pgid,
            timed_out,
            _session_ref,
            truncated,
        ) = delegate._spawn_backend(entry, argv, b"", str(job_dir), budget=10)
        assert not timed_out
        assert stderr == ""
        assert not truncated
        assert returncode == 0
        result = delegate.normalize_envelope(combined, "stub", "auto")
        assert result["outcome"] == "success"
        assert result["backend"] == "stub"

    def test_provider_streams_are_drained_but_retained_at_64_kib(self, tmp_path):
        stub = tmp_path / "noisy.py"
        stub.write_text(
            "import sys\n"
            "sys.stdout.write('o' * 70000)\n"
            "sys.stderr.write('e' * 70000)\n"
            "raise SystemExit(1)\n"
        )
        job_dir = tmp_path / "job"
        job_dir.mkdir()

        captured = delegate._spawn_backend(
            {"input": {"transport": "stdin"}},
            [sys.executable, str(stub)],
            b"",
            str(job_dir),
            budget=10,
        )
        returncode, stdout, stderr, *_rest, truncated = captured

        assert returncode == 1
        assert len(stdout.encode()) <= 64 * 1024
        assert len(stderr.encode()) <= 64 * 1024
        assert truncated is True
        evidence = FailureEvidence(
            "codex", "codex", exit_status=returncode, truncated=truncated
        )
        assert classify_failure(evidence) is FailureClass.UNKNOWN

    def test_provider_output_file_is_read_at_most_64_kib(self, tmp_path):
        stub = tmp_path / "file-noisy.py"
        stub.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            "Path(sys.argv[1]).write_text('x' * 70000)\n"
        )
        job_dir = tmp_path / "job"
        job_dir.mkdir()
        output = job_dir / "output.txt"

        captured = delegate._spawn_backend(
            {"input": {"transport": "devnull"}},
            [sys.executable, str(stub), str(output)],
            b"",
            str(job_dir),
            budget=10,
        )
        returncode, combined, _stderr, *_rest, truncated = captured

        assert returncode == 0
        assert len(combined.encode()) <= 64 * 1024 + 1
        assert truncated is True
