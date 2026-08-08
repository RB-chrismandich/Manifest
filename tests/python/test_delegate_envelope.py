#!/usr/bin/env python3
"""Envelope normalization edge cases for manifest-delegate.

Split from the fault tests (which hit the 500-line file ceiling) so this
backend-response-shape concern lives in its own module. Shares the in-process
harness via _delegate_inproc.

Run with: uv run --project configs/claude pytest tests/python/test_delegate_envelope.py -q
"""

import json

from _delegate_inproc import delegate


class TestResponseCaptureDecoding:
    def test_claude_json_output_field_is_decoded_before_envelope_scan(self):
        """Codex HIGH: `claude -p --output-format json` wraps the assistant text
        (with the fenced envelope) in a top-level JSON `result` field, escaping
        its newlines so the fence scanner cannot recover the block. The claude
        entry's response_capture must decode `result` FIRST, so a successful
        claude delegation normalizes to success — not failure."""
        inner = (
            "here is the result\n```json\n"
            '{"backend": "claude", "model": "sonnet", "outcome": "success", '
            '"attempted": "x", "changes": [], "succeeded": [], "failed": [], '
            '"follow_ups": []}\n```\n'
        )
        claude_stdout = json.dumps(
            {"type": "result", "result": inner, "session_id": "s1"}
        )
        entry = {
            "id": "claude",
            "response_capture": {"method": "json_field", "field": "result"},
        }

        # Scanning the raw JSON directly fails (the fence's newlines are escaped).
        assert (
            delegate.normalize_envelope(claude_stdout, "claude", "sonnet")["outcome"]
            == "failure"
        )
        # Decoding the result field first recovers the envelope -> success.
        decoded = delegate.backend.extract_response_text(entry, claude_stdout)
        assert (
            delegate.normalize_envelope(decoded, "claude", "sonnet")["outcome"]
            == "success"
        )

    def test_no_response_capture_passes_raw_output_through(self):
        """Backends that print the fenced block directly on stdout (codex, agy)
        declare no response_capture, so extract_response_text is a pass-through."""
        raw = "```json\n{\"outcome\": \"success\"}\n```"
        assert delegate.backend.extract_response_text({"id": "codex"}, raw) == raw

    def test_undecodable_json_field_falls_back_to_raw(self):
        """A declared json_field whose stdout is not JSON must not raise or drop
        the output — it falls back to the raw text unchanged."""
        entry = {"response_capture": {"method": "json_field", "field": "result"}}
        assert delegate.backend.extract_response_text(entry, "not json") == "not json"
