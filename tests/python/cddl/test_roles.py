"""Foundational — role-definition loading/validation (T003, FR-013).

Contract: specs/482-critic-dev-loop/contracts/role-definition.md.
"""

import pytest
from cddl import PreflightError
from cddl.roles import ROLE_FILES, load_role, load_roles


def test_valid_roles_load(roles_dir):
    roles = load_roles(roles_dir)
    assert set(roles) == {"implementer", "qa_critic", "arch_critic"}
    qa = roles["qa_critic"]
    assert qa.name == "qa-critic"
    assert qa.model == "sonnet"
    assert qa.prompt_body.strip()
    assert qa.source_path.endswith("qa-critic.md")


def test_role_files_fixed_set():
    assert ROLE_FILES == {
        "implementer": "implementer.md",
        "qa_critic": "qa-critic.md",
        "arch_critic": "arch-critic.md",
    }


def test_missing_file_fails_preflight(roles_dir):
    (roles_dir / "qa-critic.md").unlink()
    with pytest.raises(PreflightError, match=r"qa-critic\.md"):
        load_roles(roles_dir)


import os


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unreadable_file_fails_preflight(roles_dir):
    path = roles_dir / "qa-critic.md"
    path.chmod(0o000)
    try:
        with pytest.raises(PreflightError, match=r"qa-critic\.md"):
            load_role("qa_critic", roles_dir)
    finally:
        path.chmod(0o644)


def test_unparseable_frontmatter(roles_dir):
    (roles_dir / "qa-critic.md").write_text("---\nname: [broken\n---\nbody\n")
    with pytest.raises(PreflightError, match=r"qa-critic\.md"):
        load_role("qa_critic", roles_dir)


def test_missing_frontmatter_delimiters(roles_dir):
    (roles_dir / "qa-critic.md").write_text("no frontmatter at all\n")
    with pytest.raises(PreflightError, match="frontmatter"):
        load_role("qa_critic", roles_dir)


def test_name_must_equal_file_stem(roles_dir, write_role_file):
    write_role_file(roles_dir, "qa-critic", name="qa-critic-v2")
    with pytest.raises(PreflightError, match="stem"):
        load_role("qa_critic", roles_dir)


@pytest.mark.parametrize("field", ["name", "description", "model"])
def test_empty_required_field(roles_dir, write_role_file, field):
    kwargs = {"name": "qa-critic", "description": "d", "model": "sonnet"}
    kwargs[field] = ""
    write_role_file(roles_dir, "qa-critic", **kwargs)
    with pytest.raises(PreflightError, match=field):
        load_role("qa_critic", roles_dir)


@pytest.mark.parametrize("model", ["claude-3-5-sonnet-20241022", "gpt-4o", "SONNET"])
def test_non_alias_model_rejected(roles_dir, write_role_file, model):
    # Contract: alias only (haiku|sonnet|opus) — a dated model ID or foreign
    # model must fail pre-flight, not surface as a runtime CLI error (FR-013).
    write_role_file(roles_dir, "qa-critic", model=model)
    with pytest.raises(PreflightError, match="alias"):
        load_role("qa_critic", roles_dir)


@pytest.mark.parametrize("model", ["haiku", "sonnet", "opus"])
def test_allowed_model_aliases_accepted(roles_dir, write_role_file, model):
    write_role_file(roles_dir, "qa-critic", model=model)
    assert load_role("qa_critic", roles_dir).model == model


def test_empty_body(roles_dir, write_role_file):
    write_role_file(roles_dir, "qa-critic", body="   \n")
    with pytest.raises(PreflightError, match="body"):
        load_role("qa_critic", roles_dir)


def test_reserved_provider_key_rejected(roles_dir, write_role_file):
    write_role_file(roles_dir, "qa-critic", extra_frontmatter="provider: openai\n")
    with pytest.raises(PreflightError, match="provider"):
        load_role("qa_critic", roles_dir)


def test_unknown_keys_warn_and_load(roles_dir, write_role_file, capsys):
    write_role_file(roles_dir, "qa-critic", extra_frontmatter="temperature: 0.2\n")
    role = load_role("qa_critic", roles_dir)
    assert role.name == "qa-critic"
    assert "temperature" in capsys.readouterr().err
