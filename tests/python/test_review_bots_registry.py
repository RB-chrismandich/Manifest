from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "configs/claude/config/review_bots.yml"


def load():
    return yaml.safe_load(REG.read_text())


def test_registry_exists_and_parses():
    data = load()
    assert isinstance(data, dict)
    assert "bots" in data


def test_all_known_bots_present():
    assert set(load()["bots"]) == {"copilot", "jules", "palette", "bolt", "forge"}


def test_every_bot_declares_author_login_key_and_role():
    for name, bot in load()["bots"].items():
        assert "author_login" in bot, name
        assert bot["role"] in ("reviewer", "author"), name


def test_reviewer_bots_have_a_real_author_login():
    # copilot and jules are verified, distinct GitHub bot accounts.
    for name in ("copilot", "jules"):
        bot = load()["bots"][name]
        assert isinstance(bot["author_login"], str) and bot["author_login"], name
        assert bot["identified_by"] == "author_login", name


def test_persona_author_bots_have_no_fabricated_login():
    # palette/bolt/forge are Jules personas with no distinct GitHub identity;
    # asserting a fake "palette[bot]"/"bolt[bot]"/"forge[bot]" login would be a
    # guess, not a fact, so author_login must stay null and identification must
    # fall back to the title/branch prefix instead.
    for name in ("palette", "bolt", "forge"):
        bot = load()["bots"][name]
        assert bot["author_login"] is None, name
        assert bot["identified_by"] == "title_prefix", name
        assert bot["title_prefix"], name
        assert bot["branch_prefix"], name


def test_mention_only_when_invoke_is_mention():
    for name, bot in load()["bots"].items():
        if bot["invoke"] == "mention":
            assert bot.get("mention"), name
        else:
            assert "mention" not in bot, name


def test_every_bot_has_notes():
    for name, bot in load()["bots"].items():
        assert bot.get("notes"), name
