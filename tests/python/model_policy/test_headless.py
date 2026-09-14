import sys
from pathlib import Path

import pytest
from manifest_model_policy import (
    build_provider_invocation,
    resolve_cli_route,
    run_headless_prompt,
)


def test_headless_prompt_passes_resolved_model_over_stdin() -> None:
    policy = {
        "provider_order": ["fixture"],
        "model_tiers": {"fixture": {"flash": "fixture-model"}},
        "cli_agents": {
            "fixture": {
                "binary": sys.executable,
                "base_args": [
                    "-c",
                    "import sys; print(sys.argv[-1] + ':' + sys.stdin.read())",
                ],
                "model_args": ["{model}"],
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": [],
            }
        },
        "timeouts": {"default": 1},
    }
    route = resolve_cli_route(policy)

    assert route is not None
    assert (
        run_headless_prompt(route, "prompt", policy, model_tier="flash")
        == "fixture-model:prompt\n"
    )


def test_headless_prompt_rejects_empty_provider_output() -> None:
    policy = {
        "provider_order": ["fixture"],
        "cli_agents": {
            "fixture": {
                "binary": sys.executable,
                "base_args": ["-c", "import sys; sys.stdout.write(' \\n')"],
                "skill_prompt_transport": "stdin",
                "skill_prompt_args": [],
            }
        },
    }
    route = resolve_cli_route(policy)

    assert route is not None
    with pytest.raises(RuntimeError, match="returned empty output"):
        run_headless_prompt(route, "prompt", policy)


def test_provider_invocation_preserves_placeholder_like_prompt_text(
    tmp_path: Path,
) -> None:
    prompt = "literal {prompt_file} and {model}"
    argv, stdin_bytes = build_provider_invocation(
        {
            "binary": "fixture",
            "skill_prompt_transport": "argv",
            "skill_prompt_args": ["--print", "{prompt}"],
        },
        "model",
        prompt,
        tmp_path / "output",
        tmp_path / "prompt",
    )

    assert argv == ("fixture", "--print", prompt)
    assert stdin_bytes is None


def test_provider_invocation_uses_bounded_stdin_transport(tmp_path: Path) -> None:
    output_file = tmp_path / "output"
    prompt_file = tmp_path / "prompt"
    argv, stdin_bytes = build_provider_invocation(
        {
            "binary": "fixture",
            "skill_prompt_transport": "stdin",
            "skill_prompt_args": ["-p"],
        },
        "model",
        "message",
        output_file,
        prompt_file,
    )

    assert argv == ("fixture", "-p")
    assert stdin_bytes == b"message"
