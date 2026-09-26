"""Receipt, installation, and pin inspection stages."""
# ruff: noqa: F405

from __future__ import annotations

from health_report_common import *  # noqa: F403


def _receipt_expectations(
    document: dict[str, Any],
    source_root: Path | None,
    findings: list[dict[str, str]],
) -> tuple[tuple[str, ...], dict[str, set[str]]]:
    bundles = _canonical_bundles(source_root) if source_root is not None else None
    if bundles is None:
        _add_finding(findings, "contract_catalog_unavailable", "receipt")
        return (), {}
    expected_bundles, addons = bundles
    expectations: dict[str, set[str]] = {}
    selected = set(document["selected_optional"])
    for bundle in (*expected_bundles, *addons):
        expected = _contract_expectations(source_root, bundle, selected)
        if expected is None:
            _add_finding(findings, "contract_unparseable", "receipt")
            continue
        expectations[bundle] = expected
    return expected_bundles, expectations


def _check_receipt_harnesses(
    document: dict[str, Any],
    expected_bundles: tuple[str, ...],
    expectations: dict[str, set[str]],
    findings: list[dict[str, str]],
) -> None:
    for harness, record in sorted(document["harnesses"].items()):
        if not record["verified"]:
            _add_finding(findings, "harness_unverified", "receipt", harness)
        if record["errors"]:
            _add_finding(findings, "harness_receipt_error", "receipt", harness)
        installed = _normalized_plugins(record["plugin_ids"])
        if installed is None:
            _add_finding(findings, "inventory_unparseable", "receipt", harness)
            installed = set()
        for bundle in expected_bundles:
            if bundle not in installed:
                _add_finding(findings, "bundle_missing", "receipt", harness)
        capabilities = record["capabilities"]
        for state in capabilities.values():
            if _capability_is_bad(state):
                _add_finding(findings, "capability_blocked", "receipt", harness)
        for bundle in installed:
            for identity in expectations.get(bundle, set()):
                if identity not in capabilities:
                    _add_finding(findings, "capability_missing", "receipt", harness)


def _inspect_receipt(
    receipt_path: Path,
    source_root: Path | None,
    requested: Sequence[str],
    now: datetime,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any] | None, tuple[str, ...]]:
    document, error = _load_coordinator_receipt(receipt_path)
    summary: dict[str, Any] = {
        "status": "ok",
        "present": document is not None,
        "age_days": None,
        "release_version": None,
        "source_dirty": None,
        "installation": "unknown",
    }
    if error:
        code = "receipt_missing" if error == "missing" else "receipt_malformed"
        _add_finding(findings, code, "receipt")
        summary["status"] = "degraded"
        return summary, None, ()
    assert document is not None
    try:
        modified = datetime.fromtimestamp(receipt_path.stat().st_mtime, UTC)
        age = (now.astimezone(UTC) - modified).total_seconds()
    except (OSError, OverflowError, ValueError):
        age = MAX_RECEIPT_AGE_SECONDS + 1
        _add_finding(findings, "receipt_unavailable", "receipt")
    summary["age_days"] = round(max(0.0, age) / 86400, 2)
    summary["release_version"] = document["release_version"]
    summary["source_dirty"] = document["source_dirty"]
    if age > MAX_RECEIPT_AGE_SECONDS:
        _add_finding(findings, "receipt_stale", "receipt")
    if age < -300:
        _add_finding(findings, "receipt_future", "receipt")

    expected_bundles, expectations = _receipt_expectations(
        document, source_root, findings
    )
    _check_receipt_harnesses(document, expected_bundles, expectations, findings)
    if "claude" in requested and "claude" not in document["harnesses"]:
        _add_finding(findings, "requested_harness_missing", "receipt", "claude")
    summary["status"] = (
        "degraded" if any(item["component"] == "receipt" for item in findings) else "ok"
    )
    return summary, document, expected_bundles


def _valid_owned_row(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = ("source", "destination", "source_sha256", "destination_sha256")
    return all(isinstance(value.get(key), str) for key in required) and all(
        SHA256.fullmatch(str(value[key]))
        for key in ("source_sha256", "destination_sha256")
    )


def _verify_owned_row(
    row: object,
    expected_destination: Path,
) -> bool:
    if not _valid_owned_row(row):
        return False
    assert isinstance(row, dict)
    destination = Path(row["destination"]).expanduser()
    try:
        if destination.resolve(strict=False) != expected_destination.resolve(
            strict=False
        ):
            return False
    except OSError:
        return False
    observed = _sha256(destination) if _safe_regular_file(destination) else None
    return observed == row["destination_sha256"] == row["source_sha256"]


def _inspect_installation(
    environment: Mapping[str, str],
    runtime_dir: Path,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any] | None, Path | None, dict[str, str]]:
    path = _state_home(environment) / "manifest/health/installation.json"
    value, error = _read_json(path)
    if error or not isinstance(value, dict) or value.get("schema_version") != 1:
        _add_finding(findings, "health_installation_missing", "installation")
        return None, None, {}
    source_value = value.get("source_root")
    executables = value.get("executables")
    files = value.get("files")
    if (
        not isinstance(source_value, str)
        or not Path(source_value).is_absolute()
        or not isinstance(executables, dict)
        or not isinstance(files, dict)
    ):
        _add_finding(findings, "health_installation_malformed", "installation")
        return None, None, {}
    clean_executables = {
        key: item
        for key, item in executables.items()
        if key in {"python", "omp", "claude", "coordinator"}
        and isinstance(item, str)
        and Path(item).is_absolute()
    }
    if set(clean_executables) != {"python", "omp", "claude", "coordinator"}:
        _add_finding(findings, "native_cli_missing", "installation")
    if set(files) != EXPECTED_RUNTIME_FILES:
        _add_finding(findings, "health_runtime_incomplete", "installation")
    for name in EXPECTED_RUNTIME_FILES:
        if not _verify_owned_row(files.get(name), runtime_dir / name):
            _add_finding(findings, "health_runtime_drift", "installation")
    agent_root = _agent_root(environment)
    if not _verify_owned_row(
        value.get("omp_extension"), agent_root / "extensions/manifest-health.ts"
    ):
        _add_finding(findings, "omp_extension_drift", "installation", "omp")
    home = Path(environment.get("HOME") or Path.home()).expanduser()
    if not _verify_owned_row(
        value.get("claude_wrapper"), home / ".claude/scripts/mcp_health_check.sh"
    ):
        _add_finding(findings, "claude_wrapper_drift", "installation", "claude")
    source_root = Path(source_value).expanduser()
    if not source_root.is_dir():
        _add_finding(findings, "source_root_unavailable", "installation")
        source_root = None
    return value, source_root, clean_executables


def _safe_pin_path(agent_root: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        return None
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    candidate = agent_root.joinpath(*pure.parts)
    current = agent_root
    try:
        for part in pure.parts:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                return None
    except OSError:
        return None
    return candidate


def _check_package_pins(
    packages: dict[str, str],
    package_version: PackageVersion,
    summary: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    for name, expected in sorted(packages.items()):
        if name not in {"PyYAML", "jsonschema"}:
            _add_finding(findings, "pin_manifest_malformed", "pins")
            continue
        try:
            observed = package_version(name)
        except Exception:
            observed = None
        matched = observed == expected
        summary["packages"][name] = "matched" if matched else "mismatched"
        if not matched:
            _add_finding(findings, "package_pin_mismatch", "pins")


def _check_owned_pins(
    agent_root: Path, owned: dict[str, str], findings: list[dict[str, str]]
) -> tuple[int, int]:
    drifted = 0
    for relative, expected in sorted(owned.items()):
        target = _safe_pin_path(agent_root, relative)
        observed = (
            _sha256(target)
            if target is not None and _safe_regular_file(target)
            else None
        )
        if not SHA256.fullmatch(expected) or observed != expected:
            drifted += 1
            _add_finding(findings, "pin_hash_mismatch", "pins", "omp")
    return len(owned), drifted


def _inspect_pins(
    environment: Mapping[str, str],
    package_version: PackageVersion,
    findings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, str]]:
    agent_root = _agent_root(environment)
    path = agent_root / "ui-workflow/dependencies.lock.json"
    value, error = _read_json(path)
    summary: dict[str, Any] = {
        "status": "ok",
        "omp": "unknown",
        "python": "unknown",
        "packages": {},
        "owned_files": {"checked": 0, "drifted": 0},
    }
    if error or not isinstance(value, dict) or value.get("schema_version") != 1:
        _add_finding(findings, "pin_manifest_unavailable", "pins")
        summary["status"] = "degraded"
        return summary, {}
    omp_pin = value.get("omp_version")
    python_pin = value.get("python_version")
    packages = value.get("python_packages")
    owned = value.get("owned_files")
    if (
        not isinstance(omp_pin, str)
        or not isinstance(python_pin, str)
        or not _valid_string_map(packages)
        or not _valid_string_map(owned)
    ):
        _add_finding(findings, "pin_manifest_malformed", "pins")
        summary["status"] = "degraded"
        return summary, {}
    summary["omp"] = omp_pin
    summary["python"] = python_pin
    if platform.python_version() != python_pin:
        _add_finding(findings, "python_pin_mismatch", "pins")
    _check_package_pins(packages, package_version, summary, findings)
    checked, drifted = _check_owned_pins(agent_root, owned, findings)
    summary["owned_files"] = {"checked": checked, "drifted": drifted}
    summary["status"] = (
        "degraded" if any(item["component"] == "pins" for item in findings) else "ok"
    )
    return summary, {"omp": omp_pin, "python": python_pin}
