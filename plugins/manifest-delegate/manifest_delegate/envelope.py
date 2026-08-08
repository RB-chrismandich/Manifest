"""manifest-delegate: envelope."""

import json
import re

# ---------------------------------------------------------------------------
# Result-envelope normalization (result-envelope.schema.json)
# ---------------------------------------------------------------------------

REQUIRED_ENVELOPE_FIELDS = [
    "backend",
    "model",
    "outcome",
    "attempted",
    "changes",
    "succeeded",
    "failed",
    "follow_ups",
]

FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def _extract_last_json_block(text):
    matches = FENCE_RE.findall(text or "")
    for block in reversed(matches):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


ENVELOPE_OUTCOMES = ("success", "partial", "failure")
ENVELOPE_ARRAY_FIELDS = ("changes", "succeeded", "failed", "follow_ups")


def _envelope_type_errors(parsed):
    """Return a list of schema type/enum violations in `parsed` (empty if valid)."""
    errors = []
    outcome = parsed.get("outcome")
    if outcome not in ENVELOPE_OUTCOMES:
        errors.append(
            f"outcome must be one of {list(ENVELOPE_OUTCOMES)}, got {outcome!r}"
        )
    if not isinstance(parsed.get("attempted"), str):
        errors.append("attempted must be a string")
    for field in ENVELOPE_ARRAY_FIELDS:
        value = parsed.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            errors.append(f"{field} must be an array of strings")
    model = parsed.get("model")
    if model is not None and not isinstance(model, str):
        errors.append("model must be a string or null")
    return errors


def _failure_envelope(backend_id, model, error, parsed=None, raw_output=""):
    """Build a failure envelope, salvaging only well-typed fields from `parsed`."""
    parsed = parsed or {}

    def _safe_list(field):
        value = parsed.get(field)
        return (
            value
            if isinstance(value, list) and all(isinstance(v, str) for v in value)
            else []
        )

    attempted = parsed.get("attempted")
    return {
        "backend": backend_id,
        "model": model,
        "outcome": "failure",
        "attempted": attempted if isinstance(attempted, str) else "",
        "changes": _safe_list("changes"),
        "succeeded": _safe_list("succeeded"),
        "failed": _safe_list("failed"),
        "follow_ups": _safe_list("follow_ups"),
        "error": error,
        "raw_output": raw_output,
    }


def normalize_envelope(raw_output, backend_id, model):
    """Mechanically extract and strictly validate the last fenced JSON block.

    Never derives fields from prose. Empty/malformed/no-block/invalid output is
    a `failure` outcome with the raw output preserved (SC-004) — the dispatcher
    must never fabricate a summary. `backend`/`model` are always overwritten
    with dispatcher-known provenance; a backend can never self-report identity.
    """
    parsed = _extract_last_json_block(raw_output)
    if parsed is None:
        return _failure_envelope(
            backend_id, model, "backend returned nothing usable", raw_output=raw_output
        )

    missing = [f for f in REQUIRED_ENVELOPE_FIELDS if f not in parsed]
    if missing:
        return _failure_envelope(
            backend_id,
            model,
            "backend envelope invalid: missing required fields: {}".format(
                ", ".join(missing)
            ),
            parsed=parsed,
            raw_output=raw_output,
        )

    type_errors = _envelope_type_errors(parsed)
    if type_errors:
        return _failure_envelope(
            backend_id,
            model,
            "backend envelope invalid: {}".format("; ".join(type_errors)),
            parsed=parsed,
            raw_output=raw_output,
        )

    if parsed.get("outcome") == "failure" and not parsed.get("error"):
        parsed["error"] = "backend reported failure without an error message"

    parsed["backend"] = backend_id
    parsed["model"] = model
    return parsed
