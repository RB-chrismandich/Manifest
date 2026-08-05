"""Regression cases for the PR #699 review findings.

Each test below pins one reported false-negative or over-broad suppression.
Split from test_compose_commandments.py only to stay under the 500-line
file ceiling; the fixtures and the clean baseline are shared from there.
"""

from __future__ import annotations

import pytest
from test_compose_commandments import MINIMAL_CLEAN, findings_for, ids_for


@pytest.fixture(scope="module")
def cfg() -> dict:
    """The shipped rule registry. Declared here rather than imported: an
    imported fixture shadows the same-named test parameter."""
    from compose_check import load_config

    return load_config()


def test_dc001_flags_a_tag_resolved_from_the_environment(tmp_path, cfg):
    """`image: nginx:${TAG}` names no bytes: the committed file cannot say what
    deploys, so it is as unpinned as `latest`."""
    body = MINIMAL_CLEAN.replace("image: myapp:1.0.0", "image: myapp:${APP_TAG}")
    assert "DC-001" in ids_for(tmp_path, cfg, body)


def test_dc001_still_accepts_a_digest_and_a_concrete_tag(tmp_path, cfg):
    digest = MINIMAL_CLEAN.replace("image: myapp:1.0.0", "image: myapp@sha256:abc")
    assert "DC-001" not in ids_for(tmp_path, cfg, digest)
    assert "DC-001" not in ids_for(tmp_path, cfg, MINIMAL_CLEAN)


def _with_env(entry: str) -> str:
    return MINIMAL_CLEAN.replace(
        "    image: myapp:1.0.0",
        f"    image: myapp:1.0.0\n    environment:\n      {entry}",
    )


@pytest.mark.parametrize(
    "entry",
    [
        "DB_PASSWORD: ${DB_PASSWORD:-hunter2}",  # default ships the credential
        "DB_PASSWORD: 123456",  # unquoted scalar parses as int
        "DB_PASSWORD: ${DB_PASSWORD:?required}-suffix",  # reference plus literal
    ],
)
def test_dc002_flags_credentials_an_interpolation_only_appears_to_hide(
    tmp_path, cfg, entry
):
    assert "DC-002" in ids_for(tmp_path, cfg, _with_env(entry))


@pytest.mark.parametrize(
    "entry", ["DB_PASSWORD: ${DB_PASSWORD}", "DB_PASSWORD: $DB_PW"]
)
def test_dc002_accepts_a_pure_environment_reference(tmp_path, cfg, entry):
    assert "DC-002" not in ids_for(tmp_path, cfg, _with_env(entry))


def test_dc003_treats_a_none_test_as_a_disabled_healthcheck(tmp_path, cfg):
    """`test: ["NONE"]` turns the image's healthcheck off, so a dependant's
    `condition: service_healthy` can never be satisfied."""
    body = (
        "services:\n"
        "  web:\n    image: nginx:1.2\n"
        "    depends_on: {db: {condition: service_healthy}}\n"
        "  db:\n    image: postgres:16\n"
        '    healthcheck: {test: ["NONE"]}\n'
    )
    detail = {f.message for f in findings_for(tmp_path, cfg, body) if f.service == "db"}
    assert any("healthcheck is disabled" in message for message in detail)


def test_dc006_flags_an_anonymous_long_form_volume_holding_state(tmp_path, cfg):
    """A long-form mount with no `source:` gets a hash name nothing references —
    the next recreate loses the data."""
    body = (
        "services:\n"
        "  db:\n    image: postgres:16\n"
        "    volumes:\n"
        "      - type: volume\n        target: /var/lib/postgresql/data\n"
    )
    assert "DC-006" in ids_for(tmp_path, cfg, body)


def test_dc006_accepts_a_named_long_form_volume(tmp_path, cfg):
    body = (
        "volumes:\n  pgdata:\n"
        "services:\n"
        "  db:\n    image: postgres:16\n"
        "    volumes:\n"
        "      - type: volume\n        source: pgdata\n"
        "        target: /var/lib/postgresql/data\n"
    )
    assert "DC-006" not in ids_for(tmp_path, cfg, body)


def test_stateful_detection_survives_a_registry_port(tmp_path, cfg):
    """Stripping the tag from the whole reference ate the image path, so every
    private-registry database read as stateless and DC-010 never fired."""
    body = (
        "services:\n"
        "  db:\n    image: registry.local:5000/postgres@sha256:abc\n"
        '    user: "1"\n    networks: [back]\n'
        '    logging: {driver: json-file, options: {max-size: 10m, max-file: "3"}}\n'
        '    deploy: {resources: {limits: {cpus: "1", memory: 1G}}}\n'
        "networks:\n  back:\n    internal: true\n"
    )
    assert "DC-010" in ids_for(tmp_path, cfg, body)


def test_a_bare_marker_does_not_suppress_other_lines_in_the_service(tmp_path, cfg):
    """The docs promise a bare marker is line-scoped. Expanding it to the whole
    service would let one on a `user:` line hide a committed password above."""
    body = (
        "services:\n"
        "  a:\n"
        "    image: nginx:1.2\n"
        "    environment:\n      DB_PASSWORD: hunter2\n"
        "    user: root  # compose-commandments:ignore\n"
    )
    ids = ids_for(tmp_path, cfg, body)
    assert "DC-007" not in ids, "the marked line is still suppressed"
    assert "DC-002" in ids, "a marker on user: must not silence a secret above it"


def test_a_named_marker_does_not_reach_a_keyed_finding_elsewhere(tmp_path, cfg):
    body = (
        "services:\n"
        "  a:\n"
        "    image: nginx:latest\n"
        "    user: root  # compose-commandments:ignore DC-001\n"
    )
    assert "DC-001" in ids_for(tmp_path, cfg, body), (
        "image: has its own line; a DC-001 marker on user: must not cover it"
    )
