"""Prompt construction and base job metadata for delegate tasks."""

import json
import sys

from . import backend

_PROMPT_SUMMARY_MAX_CHARS = 2000

_TASK_OUTPUT_CONTRACT = (
    "\n\nEnd your final message with exactly one fenced JSON block "
    "(```json ... ```), and nothing after it, matching this shape:\n"
    "```json\n"
    "{\n"
    '  "backend": "<your backend id>",\n'
    '  "model": "<model or null>",\n'
    '  "outcome": "success",\n'
    '  "attempted": "<what you attempted>",\n'
    '  "changes": [],\n'
    '  "succeeded": [],\n'
    '  "failed": [],\n'
    '  "follow_ups": [],\n'
    '  "findings": [{"severity": "critical|high|medium|low|info", "text": "<finding>"}]\n'
    "}\n"
    "```\n"
    'Set "findings" to [] when there are no conclusions for a second opinion. '
    'Use "partial" or "failure" when the task is incomplete or failed, and '
    'include a non-empty string "error" for failure. Every other array field '
    "must be an array of strings.\n"
)


def _build_task_prompt(args, second_opinion_record):
    """Build validated prompt text and its effective write flag."""
    if second_opinion_record is not None:
        has_task_file = bool(
            getattr(args, "task_file", None) or getattr(args, "prompt_file", None)
        )
        if not has_task_file and getattr(args, "prompt", None) is None:
            return (
                None,
                False,
                "delegate: second opinion requires fresh task text via explicit '-' stdin or --task-file",
            )
        if not has_task_file and getattr(args, "prompt", None) not in {None, "-"}:
            return (
                None,
                False,
                "delegate: second opinion requires fresh task text via stdin or --task-file",
            )
    prompt, prompt_error = backend._read_prompt(args)
    if prompt_error:
        return None, False, prompt_error
    if not prompt.strip():
        return None, False, "delegate: task text must be non-empty"
    if second_opinion_record is None:
        return prompt.rstrip() + _TASK_OUTPUT_CONTRACT, bool(args.write), None
    prompt = (
        "Second opinion requested on job {}.\n"
        "Prior findings (task-free): {}\n\n"
        "Freshly resubmitted task:\n{}".format(
            second_opinion_record["job_id"],
            json.dumps(
                second_opinion_record["findings"],
                sort_keys=True,
                ensure_ascii=False,
            ),
            prompt,
        )
    )
    return prompt.rstrip() + _TASK_OUTPUT_CONTRACT, False, None


def _build_task_extra(
    args, entry, resume_record, second_opinion_record, model_tier, budget, write
):
    """Assemble stable base metadata and warn on unsupported resume."""
    resume_from_session_ref = None
    if resume_record is not None and not getattr(args, "fresh", False):
        if entry.get("resume"):
            resume_from_session_ref = resume_record.get("session_ref")
        else:
            print(
                "delegate: backend {!r} does not support resume; sending "
                "context fresh".format(entry["id"]),
                file=sys.stderr,
            )
    extra = {
        "kind": "task",
        "write": write,
        "model": model_tier,
        "budget_seconds": budget,
    }
    if resume_from_session_ref:
        extra["resume_from_session_ref"] = resume_from_session_ref
    if second_opinion_record is not None:
        extra.update(
            {
                "second_opinion_of": second_opinion_record["job_id"],
                "second_opinion_source_version": second_opinion_record["version"],
                "second_opinion_attempt_id": second_opinion_record["attempt_id"],
                "second_opinion_findings_digest": second_opinion_record[
                    "findings_digest"
                ],
            }
        )
    return extra
