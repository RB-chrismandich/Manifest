"""Redact native harness result data before exposing service reports."""

from __future__ import annotations

from dataclasses import replace

from manifest_agent.models import HarnessResult, NativePluginInspection
from manifest_agent.process import names_credential_field, redact_text


def _safe_native_package(package: NativePluginInspection) -> NativePluginInspection:
    return replace(
        package,
        package_id=redact_text(package.package_id),
        package_name=redact_text(package.package_name),
        marketplace=redact_text(package.marketplace) if package.marketplace else None,
        source_uri=redact_text(package.source_uri) if package.source_uri else None,
        source_provenance=(
            redact_text(package.source_provenance)
            if package.source_provenance
            else None
        ),
        version=redact_text(package.version) if package.version else None,
        scope=redact_text(package.scope) if package.scope else None,
        native_root=redact_text(package.native_root) if package.native_root else None,
        install_path=redact_text(package.install_path)
        if package.install_path
        else None,
        status=redact_text(package.status),
    )


def _safe_result(result: HarnessResult) -> HarnessResult:
    capabilities = {}
    for index, (key, value) in enumerate(result.capabilities.items()):
        safe_key = f"[REDACTED-{index}]" if names_credential_field(key) else key
        capabilities[redact_text(safe_key)] = redact_text(value)
    native = result.native_inspection
    if native is not None:
        native = replace(
            native,
            harness=redact_text(native.harness),
            profile=redact_text(native.profile) if native.profile else None,
            native_root=redact_text(native.native_root) if native.native_root else None,
            packages=tuple(
                _safe_native_package(package) for package in native.packages
            ),
            components=tuple(
                replace(
                    component,
                    kind=redact_text(component.kind),
                    identifier=redact_text(component.identifier),
                    status=redact_text(component.status),
                    provenance=redact_text(component.provenance),
                    resolved_path=redact_text(component.resolved_path)
                    if component.resolved_path
                    else None,
                )
                for component in native.components
            ),
            activation=redact_text(native.activation),
            inventory_errors=tuple(map(redact_text, native.inventory_errors)),
        )
    return replace(
        result,
        installed_plugin_ids=tuple(map(redact_text, result.installed_plugin_ids)),
        capabilities=capabilities,
        errors=tuple(map(redact_text, result.errors)),
        warnings=tuple(map(redact_text, result.warnings)),
        declared_degradations=tuple(map(redact_text, result.declared_degradations)),
        owned_entries=(),
        native_inspection=native,
    )
