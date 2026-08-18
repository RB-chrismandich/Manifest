"""The docker-compose commandments checker (manifest-docker plugin).

What these tests are actually pinning:

Each rule gets a POSITIVE case (a document that must trip it) and a NEGATIVE
case (the corrected document, which must not). A rule test that only asserts
"finding present" passes just as well against a checker that flags everything,
so the negative half is the half that carries the weight.

Line attribution is pinned separately, because it silently regressed once
already: before per-key lines were recorded, a finding about a MISSING key
resolved to the mapping's first key, which is right only by luck when the key
happens to come first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN = REPO_ROOT / "plugins" / "manifest-ops"
SCRIPTS = PLUGIN / "runtime" / "bin"
CHECKER = SCRIPTS / "compose_check.py"
TEMPLATE = (
    PLUGIN
    / "skills"
    / "docker-compose-commandments"
    / "references"
    / "compose-template.yaml"
)
HOOK = SCRIPTS / "compose_commandments_hook.py"

sys.path.insert(0, str(SCRIPTS))

pytest.importorskip("yaml")

from compose_check import check_file, is_compose_file, load_config
from compose_rules import RULES

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "compose"


def fixture(name: str) -> str:
    """Load a compose fixture. Payloads live in tests/fixtures, never inline."""
    return (FIXTURES / name).read_text(encoding="utf-8")


MINIMAL_CLEAN = fixture("minimal_clean.yaml")
DEPENDS = fixture("depends.yaml.tmpl")
ISOLATION = fixture("isolation.yaml.tmpl")
LINES = fixture("lines.yaml")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config()


def findings_for(
    tmp_path: Path, cfg: dict, body: str, name: str = "docker-compose.yaml"
):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return check_file(path, cfg)


def ids_for(tmp_path: Path, cfg: dict, body: str) -> set[str]:
    return {f.rule_id for f in findings_for(tmp_path, cfg, body)}


# --------------------------------------------------------------------------- #
# Registry integrity
# --------------------------------------------------------------------------- #


def test_every_registry_rule_has_an_implementation(cfg):
    """A rule described in YAML but not implemented would silently never fire."""
    declared = {r["id"] for r in cfg["rules"] if not r.get("retired")}
    assert declared == set(RULES), f"registry {declared} vs implemented {set(RULES)}"


def test_registry_declares_ten_commandments(cfg):
    assert [r["id"] for r in cfg["rules"]] == [f"DC-{n:03d}" for n in range(1, 11)]


def test_every_rule_carries_prose_a_user_can_act_on(cfg):
    for rule in cfg["rules"]:
        assert rule["commandment"].startswith("Thou Shalt"), rule["id"]
        assert rule["fix"].strip(), f"{rule['id']} has no remedy"
        assert rule["severity"] in {"high", "medium", "low"}, rule["id"]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("docker-compose.yaml", True),
        ("docker-compose.yml", True),
        ("compose.yaml", True),
        ("docker-compose.prod.yml", True),
        ("compose-template.yaml", False),  # the shipped reference, not a real stack
        ("values.yaml", False),
        ("Dockerfile", False),
    ],
)
def test_filename_recognition(cfg, name, expected):
    assert is_compose_file(Path(name), cfg) is expected


# --------------------------------------------------------------------------- #
# The shipped template is the negative case for all ten at once
# --------------------------------------------------------------------------- #


def test_shipped_template_is_clean(cfg):
    """The template the skill tells users to copy must satisfy every rule."""
    assert check_file(TEMPLATE, cfg) == []


def test_template_would_not_be_picked_up_by_a_tree_sweep(cfg):
    """It lives in the repo; a sweep of this repo must not report on it."""
    assert not is_compose_file(TEMPLATE, cfg)


# --------------------------------------------------------------------------- #
# Per-rule: positive then negative
# --------------------------------------------------------------------------- #


def test_minimal_clean_document_trips_nothing(tmp_path, cfg):
    """The baseline every single-rule case below mutates. If this is not clean,
    every 'rule X fires' assertion below could be measuring something else."""
    assert ids_for(tmp_path, cfg, MINIMAL_CLEAN) == set()


@pytest.mark.parametrize(
    "rule,break_it",
    [
        ("DC-001", ("image: myapp:1.0.0", "image: myapp:latest")),
        ("DC-004", ('          cpus: "0.5"', "          x: 0")),
        ("DC-007", ('    user: "1000:1000"', "    user: root")),
        ("DC-008", ("        max-size: 10m", "        other: 1")),
    ],
)
def test_single_mutation_trips_exactly_its_rule(tmp_path, cfg, rule, break_it):
    """One edit to the clean baseline must raise that rule and nothing else."""
    old, new = break_it
    assert old in MINIMAL_CLEAN, "fixture drifted from the mutation target"
    assert ids_for(tmp_path, cfg, MINIMAL_CLEAN.replace(old, new)) == {rule}


def test_dc002_flags_a_literal_but_not_an_interpolation(tmp_path, cfg):
    literal = MINIMAL_CLEAN.replace(
        "    image: myapp:1.0.0",
        "    image: myapp:1.0.0\n    environment:\n      DB_PASSWORD: hunter2",
    )
    assert "DC-002" in ids_for(tmp_path, cfg, literal)

    interpolated = literal.replace("hunter2", "${DB_PASSWORD}")
    assert "DC-002" not in ids_for(tmp_path, cfg, interpolated)


def test_dc002_accepts_the_file_convention(tmp_path, cfg):
    """`*_FILE` names a path, not a secret — flagging it would train users to
    bypass the rule on the very pattern the rule wants them to adopt."""
    body = MINIMAL_CLEAN.replace(
        "    image: myapp:1.0.0",
        "    image: myapp:1.0.0\n    environment:\n"
        "      POSTGRES_PASSWORD_FILE: /run/secrets/db_password",
    )
    assert "DC-002" not in ids_for(tmp_path, cfg, body)


def test_dc002_reads_the_list_form_of_environment(tmp_path, cfg):
    body = MINIMAL_CLEAN.replace(
        "    image: myapp:1.0.0",
        "    image: myapp:1.0.0\n    environment:\n      - API_TOKEN=abc123",
    )
    assert "DC-002" in ids_for(tmp_path, cfg, body)


HEALTHCHECK = '    healthcheck: {test: ["CMD", "true"]}'


def test_dc003_short_form_depends_on_is_flagged(tmp_path, cfg):
    body = DEPENDS % ("      - db", HEALTHCHECK)
    assert "DC-003" in ids_for(tmp_path, cfg, body)


def test_dc003_condition_service_healthy_with_a_healthcheck_is_accepted(tmp_path, cfg):
    body = DEPENDS % ("      db:\n        condition: service_healthy", HEALTHCHECK)
    assert "DC-003" not in ids_for(tmp_path, cfg, body)


def test_dc003_condition_started_is_still_flagged(tmp_path, cfg):
    """`service_started` is the default dressed up — it waits for spawn, not ready."""
    body = DEPENDS % ("      db:\n        condition: service_started", HEALTHCHECK)
    assert "DC-003" in ids_for(tmp_path, cfg, body)


def test_dc003_flags_a_dependency_that_has_no_healthcheck(tmp_path, cfg):
    body = DEPENDS % ("      db:\n        condition: service_healthy", "")
    assert "DC-003" in ids_for(tmp_path, cfg, body)


def test_dc005_flags_a_database_on_the_published_network(tmp_path, cfg):
    assert "DC-005" in ids_for(tmp_path, cfg, ISOLATION % ("[app-net]", "[app-net]"))


def test_dc005_accepts_the_edge_bridging_both_networks(tmp_path, cfg):
    """The correct topology: web on both, db on the internal one only."""
    assert "DC-005" not in ids_for(
        tmp_path, cfg, ISOLATION % ("[app-net, db-net]", "[db-net]")
    )


def test_dc005_flags_reliance_on_the_implicit_default_network(tmp_path, cfg):
    body = "services:\n  a:\n    image: a:1\n  b:\n    image: b:1\n"
    assert "DC-005" in ids_for(tmp_path, cfg, body)


def test_dc006_flags_a_bind_mount_of_state_and_accepts_a_named_volume(tmp_path, cfg):
    bind = ISOLATION.replace(
        "[db_data:/var/lib/postgresql/data]", "['./pg:/var/lib/postgresql/data']"
    )
    assert "DC-006" in ids_for(tmp_path, cfg, bind % ("[app-net, db-net]", "[db-net]"))
    assert "DC-006" not in ids_for(
        tmp_path, cfg, ISOLATION % ("[app-net, db-net]", "[db-net]")
    )


def test_dc006_ignores_a_read_only_config_bind_mount(tmp_path, cfg):
    """Bind-mounting config is normal and correct; only stateful paths are the target."""
    body = MINIMAL_CLEAN.replace(
        "    image: myapp:1.0.0",
        "    image: myapp:1.0.0\n    volumes: ['./nginx.conf:/etc/nginx/nginx.conf:ro']",
    )
    assert "DC-006" not in ids_for(tmp_path, cfg, body)


def test_dc008_ignores_drivers_that_do_not_accumulate_on_disk(tmp_path, cfg):
    body = MINIMAL_CLEAN.replace(
        '    logging:\n      driver: json-file\n      options:\n        max-size: 10m\n        max-file: "3"',
        "    logging:\n      driver: gelf\n      options:\n        gelf-address: udp://logs:12201",
    )
    assert "DC-008" not in ids_for(tmp_path, cfg, body)


def _repeated(anchor: bool) -> str:
    block = (
        '    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}'
        if not anchor
        else "    <<: *log"
    )
    head = (
        ""
        if not anchor
        else 'x-log: &log\n  logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}\n'
    )
    services = "".join(
        f'  s{n}:\n    image: i:1\n    user: "1"\n    networks: [n]\n'
        f'    deploy: {{resources: {{limits: {{cpus: "1", memory: 1G}}}}}}\n{block}\n'
        for n in range(3)
    )
    return f"{head}services:\n{services}networks:\n  n: {{driver: bridge}}\n"


def test_dc009_flags_three_copies_and_clears_once_anchored(tmp_path, cfg):
    """Anchors are expanded by the parser, so the parsed tree is identical either
    way — this is the one rule that must read the raw text to tell them apart."""
    assert "DC-009" in ids_for(tmp_path, cfg, _repeated(anchor=False))
    assert "DC-009" not in ids_for(tmp_path, cfg, _repeated(anchor=True))


def test_dc010_applies_to_stateful_services_only(tmp_path, cfg):
    stateful = ISOLATION % ("[app-net, db-net]", "[db-net]")
    assert "DC-010" not in ids_for(tmp_path, cfg, stateful)
    assert "DC-010" in ids_for(
        tmp_path, cfg, stateful.replace("    stop_grace_period: 30s\n", "")
    )
    # A stateless service is not expected to declare one.
    assert "DC-010" not in ids_for(tmp_path, cfg, MINIMAL_CLEAN)


# --------------------------------------------------------------------------- #
# Line attribution — regressed once, pinned here
# --------------------------------------------------------------------------- #


def test_finding_about_a_present_key_points_at_that_key(tmp_path, cfg):
    found = {f.rule_id: f.line for f in findings_for(tmp_path, cfg, LINES)}
    assert found["DC-001"] == 3, "image: is on line 3"
    assert found["DC-002"] == 6, (
        "DB_PASSWORD is on line 6, not the environment: block on 4"
    )


def test_finding_about_a_missing_key_points_at_the_service_header(tmp_path, cfg):
    """Not at the service's first key — that is right only when the missing rule
    happens to concern whatever sorted first."""
    found = {f.rule_id: f.line for f in findings_for(tmp_path, cfg, LINES)}
    assert found["DC-004"] == 2, "web: is on line 2"
    assert found["DC-007"] == 2
    assert found["DC-008"] == 2


# --------------------------------------------------------------------------- #
# Bypass markers
# --------------------------------------------------------------------------- #


def test_bare_marker_suppresses_every_rule_on_its_line(tmp_path, cfg):
    body = "services:\n  a:\n    image: nginx:latest  # compose-commandments:ignore\n"
    assert "DC-001" not in ids_for(tmp_path, cfg, body)


def test_named_marker_suppresses_only_the_named_rule(tmp_path, cfg):
    body = "services:\n  a:\n    image: nginx:latest  # compose-commandments:ignore DC-001\n"
    ids = ids_for(tmp_path, cfg, body)
    assert "DC-001" not in ids
    assert "DC-004" in ids, "a DC-001 bypass must not silence unrelated rules"


def test_marker_anywhere_in_the_block_covers_a_missing_key_finding(tmp_path, cfg):
    """A missing key has no line to annotate, so the whole service block counts."""
    body = (
        "services:\n  a:\n    image: nginx:1.2\n"
        "    user: root  # compose-commandments:ignore DC-004 DC-007\n"
    )
    ids = ids_for(tmp_path, cfg, body)
    assert "DC-004" not in ids and "DC-007" not in ids
    assert "DC-008" in ids


def test_file_marker_exempts_the_whole_file(tmp_path, cfg):
    body = (
        "# compose-commandments:ignore-file\nservices:\n  a:\n    image: nginx:latest\n"
    )
    assert ids_for(tmp_path, cfg, body) == set()


def test_a_marker_in_one_service_does_not_leak_into_the_next(tmp_path, cfg):
    body = (
        "services:\n"
        "  a:\n    image: x:1\n    user: root  # compose-commandments:ignore DC-007\n"
        "  b:\n    image: y:1\n"
    )
    services = {
        f.service for f in findings_for(tmp_path, cfg, body) if f.rule_id == "DC-007"
    }
    assert services == {"b"}


def test_the_line_tracking_loader_refuses_python_object_tags():
    """The C-DANGER exemption in compose_model.py claims LineLoader adds no
    constructible tags. That is a security claim about a `yaml.load()` call, so
    it is enforced here rather than trusted: swapping the base to UnsafeLoader
    makes this payload execute, which is what the exemption promises it cannot.
    """
    from compose_model import load_yaml_with_lines

    with pytest.raises(Exception) as excinfo:
        load_yaml_with_lines("!!python/object/apply:os.system ['echo pwned']\n")
    assert "ConstructorError" in type(excinfo.value).__name__


def test_dc003_flags_a_healthcheck_that_is_explicitly_disabled(tmp_path, cfg):
    """`disable: true` is worse than absent: a dependant waiting on
    service_healthy can never be satisfied, so compose blocks until timeout."""
    disabled = "    healthcheck: {disable: true}"
    body = DEPENDS % ("      db:\n        condition: service_healthy", disabled)
    assert "DC-003" in ids_for(tmp_path, cfg, body)


def test_dc005_flags_host_networking_on_a_stateful_service(tmp_path, cfg):
    """network_mode: host opts out of Docker networking, so `networks:` and
    `internal: true` stop constraining anything."""
    body = (
        "services:\n"
        "  db:\n    image: postgres:16\n    network_mode: host\n"
        '    user: "1"\n    stop_grace_period: 30s\n'
        '    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}\n'
        '    deploy: {resources: {limits: {cpus: "1", memory: 1G}}}\n'
    )
    assert "DC-005" in ids_for(tmp_path, cfg, body)


def test_dc005_leaves_host_networking_alone_for_a_stateless_service(tmp_path, cfg):
    """Host mode is normal for edge proxies and metrics agents; only durable
    state on the host network is the finding."""
    body = (
        "services:\n"
        "  proxy:\n    image: nginx:1.25\n    network_mode: host\n"
        '    user: "1"\n'
        '    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}\n'
        '    deploy: {resources: {limits: {cpus: "1", memory: 1G}}}\n'
    )
    assert "DC-005" not in ids_for(tmp_path, cfg, body)
