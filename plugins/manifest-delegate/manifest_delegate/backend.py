"""manifest-delegate: backend."""

import json
import os
import re
import sys

from . import config, constants

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


REGISTRY_PATH_ENV = "MANIFEST_DELEGATE_REGISTRY_PATH"
DEFAULT_BUDGET_SECONDS = 600


def _registry_path_override():
    return os.environ.get(REGISTRY_PATH_ENV)


def _substitute_argv(tokens, mapping):
    out = []
    for tok in tokens:
        if constants.PLACEHOLDER_RE.match(tok):
            out.append(mapping.get(tok[1:-1], tok))
        else:
            out.append(tok)
    return out


def map_model_tier(entry, tier):
    """Map a tier name through parallel_agent.yml model_tiers (D3/D4/D5 contract).

    Consults `model_tiers.<entry["tier_source-keyed backend id]>.<tier>` only
    when PyYAML is importable and the deployed config + key + tier are all
    present; any of those being absent falls back to verbatim passthrough
    (the devin precedent — never an error).
    """
    if not tier:
        return tier
    tier_source = entry.get("tier_source")
    if tier_source:
        tiers = config.load_model_tiers()
        backend_tiers = tiers.get(entry["id"]) if isinstance(tiers, dict) else None
        if isinstance(backend_tiers, dict) and tier in backend_tiers:
            return backend_tiers[tier]
    return tier


def resolve_model_tier(entry, user_config, model_arg):
    if model_arg:
        tier = model_arg
    else:
        backend_cfg = (user_config.get("backends") or {}).get(entry["id"], {})
        tier = backend_cfg.get("model") or entry.get("default_tier")
    return map_model_tier(entry, tier)


def resolve_budget(entry, user_config, budget_arg):
    if budget_arg is not None:
        return budget_arg
    backend_cfg = (user_config.get("backends") or {}).get(entry["id"], {})
    if isinstance(backend_cfg.get("budget_seconds"), int):
        return backend_cfg["budget_seconds"]
    return DEFAULT_BUDGET_SECONDS


def build_invoke_argv(entry, write, model_tier, mapping):
    argv = list(entry.get("invoke") or [])
    sandbox = entry.get("sandbox") or {}
    argv += list(
        (sandbox.get("write_args") if write else sandbox.get("read_only_args")) or []
    )
    if model_tier:
        argv += [
            tok.replace("{model}", model_tier)
            for tok in (entry.get("model_args") or [])
        ]
    return _substitute_argv(argv, mapping)


def build_resume_argv(entry, session_ref, write, model_tier, mapping):
    argv = list(entry.get("resume") or [])
    sandbox = entry.get("sandbox") or {}
    argv += list(
        (sandbox.get("write_args") if write else sandbox.get("read_only_args")) or []
    )
    if model_tier:
        argv += [
            tok.replace("{model}", model_tier)
            for tok in (entry.get("model_args") or [])
        ]
    full_mapping = dict(mapping)
    full_mapping["session_ref"] = session_ref
    return _substitute_argv(argv, full_mapping)


def extract_session_ref(entry, raw_output):
    """Extract a resumable session pointer per the registry's
    session_id_capture method. Never raises; unmatched input -> None."""
    cap = entry.get("session_id_capture") or {}
    method = cap.get("method")
    raw_output = raw_output or ""
    if method == "jsonl_event":
        event_name = cap.get("event")
        field = cap.get("field")
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == event_name:
                return obj.get(field)
        return None
    if method == "json_field":
        field = cap.get("field")
        try:
            obj = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            return None
        return obj.get(field) if isinstance(obj, dict) else None
    if method == "output_scan":
        pattern = cap.get("pattern")
        if not pattern:
            return None
        match = re.search(pattern, raw_output)
        return match.group(1) if match else None
    return None


def extract_response_text(entry, raw_output):
    """Return the assistant text to scan for the result envelope.

    Some backends wrap their assistant message in a structured envelope on
    stdout — e.g. `claude -p --output-format json` emits a top-level JSON object
    whose `result` field holds the text, with the fenced envelope inside it
    JSON-escaped (newlines/quotes escaped) so the fence scanner cannot recover
    it. When the registry entry declares `response_capture` (json_field), decode
    that field first so normalization sees real newlines. No declaration, or
    undecodable output, returns raw_output unchanged (backends that already
    print the fenced block directly on stdout). Never raises."""
    cap = entry.get("response_capture") or {}
    if cap.get("method") == "json_field":
        field = cap.get("field")
        try:
            obj = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            return raw_output
        if isinstance(obj, dict) and isinstance(obj.get(field), str):
            return obj[field]
    return raw_output


def check_payload_limits(entry, payload_bytes):
    input_cfg = entry.get("input") or {}
    max_payload = input_cfg.get("max_payload_bytes")
    if max_payload is not None and len(payload_bytes) > max_payload:
        return (
            f"prompt exceeds input.max_payload_bytes "
            f"({len(payload_bytes)} > {max_payload})"
        )
    max_context = input_cfg.get("max_context_bytes")
    if max_context is not None and len(payload_bytes) > max_context:
        return (
            f"prompt exceeds input.max_context_bytes "
            f"({len(payload_bytes)} > {max_context})"
        )
    return None


def _read_prompt(args):
    """Read the effective prompt text. Returns (text, error_message_or_None);
    never raises (D3: a bad --prompt-file must exit 2, not traceback)."""
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        if os.path.isdir(prompt_file):
            return (
                None,
                f"delegate: cannot read --prompt-file {prompt_file}: is a directory",
            )
        try:
            with open(prompt_file, encoding="utf-8") as fh:
                return fh.read(), None
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"delegate: cannot read --prompt-file {prompt_file}: {exc}"
    if args.prompt in (None, "-"):
        return sys.stdin.read(), None
    return args.prompt, None


def _executable_missing(argv):
    if not argv:
        return "empty invoke command"
    exe = argv[0]
    if os.path.dirname(exe):
        return None if os.access(exe, os.X_OK) else f"not executable: {exe}"
    from shutil import which

    return None if which(exe) else f"not found on PATH: {exe}"
