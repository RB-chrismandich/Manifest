"""Isolation tests for the installed stitch-design bundle."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml

from manifest_agent.contracts import CapabilityTier, load_contract


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def stitch_bundle(repo_root: Path, tmp_path: Path) -> Path:
    installed = tmp_path / "stitch-design"
    shutil.copytree(
        repo_root / "plugins/stitch-design",
        installed,
        ignore=shutil.ignore_patterns("node_modules"),
    )
    return installed


def _offline_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    agent_root = tmp_path / "agent"
    home.mkdir(exist_ok=True)
    agent_root.mkdir(exist_ok=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "OMP_CONFIG_DIR": str(tmp_path / "omp-config"),
        "PI_CODING_AGENT_DIR": str(agent_root),
        "npm_config_offline": "true",
        "NO_PROXY": "*",
        "UV_NO_NETWORK": "1",
    }


def _run_node(
    script: Path, *args: str, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None
    return subprocess.run(
        [node, str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_omp(
    *args: str,
    cwd: Path,
    env: dict[str, str],
    stdin: str = "",
    timeout: float = 10,
) -> subprocess.CompletedProcess[str]:
    omp = shutil.which("omp")
    if omp is None:
        pytest.skip("omp executable is unavailable; cannot verify plugin linking")
    return subprocess.run(
        [omp, *args],
        cwd=cwd,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def test_stitch_bundle_declares_an_installable_omp_package(
    stitch_bundle: Path,
) -> None:
    package_path = stitch_bundle / "package.json"
    assert package_path.is_file()

    package = json.loads(package_path.read_text(encoding="utf-8"))

    assert package["name"] == "stitch-design"
    assert package["version"] == "0.4.0"
    assert package["private"] is True
    assert package["omp"] == {"extensions": ["./extensions/ui-delivery-policy.ts"]}


def test_stitch_omp_mcp_definition_is_safe_and_streamable_http(
    stitch_bundle: Path,
) -> None:
    mcp_path = stitch_bundle / ".mcp.json"
    assert mcp_path.is_file()

    definition = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert definition == {
        "$schema": (
            "https://raw.githubusercontent.com/can1357/oh-my-pi/main/"
            "packages/coding-agent/src/config/mcp-schema.json"
        ),
        "mcpServers": {
            "stitch": {
                "type": "http",
                "url": "https://stitch.googleapis.com/mcp",
                "enabled": True,
            }
        },
    }


def test_stitch_omp_extension_registers_deterministic_read_only_status_tool(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    extension = stitch_bundle / "extensions/ui-delivery-policy.ts"
    assert extension.is_file()
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("bun executable is unavailable; cannot load an OMP extension")

    probe = tmp_path / "extension-probe.mjs"
    probe.write_text(
        textwrap.dedent(
            """\
            const extensionPath = process.argv[2];
            const registeredTools = [];
            const emptyObjectSchema = {
              strict: () => emptyObjectSchema,
            };
            const api = {
              zod: { object: () => emptyObjectSchema },
              registerTool(tool) {
                registeredTools.push(tool);
              },
            };
            const module = await import(extensionPath);
            if (typeof module.default !== "function") {
              throw new Error("extension default export is not a factory");
            }
            await module.default(api);
            const statusTool = registeredTools.find(
              (tool) => tool.name === "ui_delivery_status",
            );
            if (!statusTool) {
              throw new Error("ui_delivery_status tool was not registered");
            }
            const first = await statusTool.execute(
              "first", {}, new AbortController().signal, () => {}, {},
            );
            const second = await statusTool.execute(
              "second", {}, new AbortController().signal, () => {}, {},
            );
            console.log(JSON.stringify({ count: registeredTools.length, first, second }));
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [bun, str(probe), extension.resolve().as_uri()],
        cwd=tmp_path,
        env=_offline_env(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["first"] == observed["second"]
    assert observed["first"]["content"][0]["type"] == "text"


def test_stitch_contract_inventories_omp_delivery_assets(
    stitch_bundle: Path,
) -> None:
    contract_path = stitch_bundle / "manifest-capabilities.yml"
    document = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime = {item["id"]: item for item in document["components"]["runtime"]}

    assert {
        "stitch-omp-package",
        "stitch-omp-extension",
        "stitch-omp-mcp-definition",
    } <= runtime.keys()
    assert runtime["stitch-omp-package"]["path"] == "package.json"
    assert runtime["stitch-omp-extension"]["path"] == (
        "extensions/ui-delivery-policy.ts"
    )
    assert runtime["stitch-omp-mcp-definition"]["path"] == ".mcp.json"
    extension_inventory = runtime["stitch-omp-extension"]
    compatibility = extension_inventory.get("compatibility")
    assert compatibility is not None
    assert set(compatibility) == {
        "claude",
        "codex",
        "gemini",
        "cursor",
        "antigravity",
        "devin",
    }
    assert all(status["mode"] != "native" for status in compatibility.values())


def test_omp_plugin_link_isolated_from_real_home_registers_package(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    env = _offline_env(tmp_path)
    plugin_root = Path(env["HOME"]) / ".omp/plugins"
    real_registry = Path.home() / ".omp/plugins"
    real_registry_before = (
        tuple(sorted(path.relative_to(real_registry).as_posix() for path in real_registry.rglob("*")))
        if real_registry.exists()
        else ()
    )

    linked = _run_omp(
        "plugin",
        "link",
        str(stitch_bundle),
        "--scope",
        "user",
        cwd=tmp_path,
        env=env,
    )

    assert linked.returncode == 0, linked.stderr
    registered_package = plugin_root / "node_modules/stitch-design"
    assert registered_package.is_symlink()
    assert registered_package.resolve() == stitch_bundle.resolve()
    listed = _run_omp(
        "plugin",
        "list",
        "--json",
        cwd=tmp_path,
        env=env,
    )
    assert listed.returncode == 0, listed.stderr
    npm_packages = json.loads(listed.stdout)["npm"]
    package = next(
        item for item in npm_packages if item["name"] == "stitch-design"
    )
    assert Path(package["path"]) == registered_package
    assert package["version"] == "0.4.0"
    assert package["enabled"] is True
    assert package["manifest"]["extensions"] == ["./extensions/ui-delivery-policy.ts"]
    real_registry_after = (
        tuple(
            sorted(
                path.relative_to(real_registry).as_posix()
                for path in real_registry.rglob("*")
            )
        )
        if real_registry.exists()
        else ()
    )
    assert real_registry_after == real_registry_before



def test_generated_validators_run_offline_without_node_modules(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    component = tmp_path / "Card.tsx"
    component.write_text(
        "export interface CardProps { readonly title: string }\n"
        "export function Card(props: CardProps) { return <section>{props.title}</section> }\n",
        encoding="utf-8",
    )
    validator = stitch_bundle / "skills/react-components/scripts/validate.js"
    result = _run_node(
        validator, str(component), cwd=tmp_path, env=_offline_env(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    assert "COMPONENT VALID" in result.stdout
    assert not (stitch_bundle / "node_modules").exists()


def test_generated_native_validator_runs_offline_without_node_modules(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    component = tmp_path / "Card.tsx"
    component.write_text(
        "export interface CardProps { readonly title: string }\n"
        "export function Card(props: CardProps) { return <Text>{props.title}</Text> }\n",
        encoding="utf-8",
    )
    validator = stitch_bundle / "skills/react-native/scripts/validate.js"
    result = _run_node(
        validator, str(component), cwd=tmp_path, env=_offline_env(tmp_path)
    )

    assert result.returncode == 0, result.stderr
    assert "COMPONENT VALID" in result.stdout


@pytest.mark.parametrize(
    "artifact",
    ("extract-inline-html", "post-process", "snapshot", "validate-react"),
)
def test_generated_artifacts_are_standalone_and_include_notices(
    stitch_bundle: Path, tmp_path: Path, artifact: str
) -> None:
    script = stitch_bundle / f"runtime/dist/{artifact}.mjs"
    source = script.read_text(encoding="utf-8")
    assert "THIRD-PARTY LICENSE NOTICES" in source
    result = _run_node(script, "--help", cwd=tmp_path, env=_offline_env(tmp_path))
    assert result.returncode == 0, result.stderr
    if artifact in {"extract-inline-html", "post-process", "snapshot"}:
        assert f"node runtime/dist/{artifact}.mjs" in result.stdout
        assert "<BUNDLE_ROOT>" not in result.stdout


def test_snapshot_reports_missing_optional_chromium(
    stitch_bundle: Path, tmp_path: Path
) -> None:
    snapshot = stitch_bundle / "runtime/dist/snapshot.mjs"
    result = _run_node(
        snapshot,
        "--url",
        "http://127.0.0.1:65534",
        "--chromium",
        str(tmp_path / "missing-chromium"),
        "--output",
        str(tmp_path / "page.html"),
        cwd=tmp_path,
        env={**_offline_env(tmp_path), "PATH": "/usr/bin:/bin"},
    )

    assert result.returncode != 0
    assert "chromium" in result.stderr.lower()
    assert "download" not in result.stderr.lower()


def test_stitch_build_dependencies_are_exact_and_checked_in(
    stitch_bundle: Path,
) -> None:
    package = json.loads((stitch_bundle / "runtime/node/package.json").read_text())
    lock = json.loads((stitch_bundle / "runtime/node/package-lock.json").read_text())

    assert set(package["devDependencies"]) == {
        "@babel/generator",
        "@babel/parser",
        "@babel/traverse",
        "esbuild",
        "puppeteer-core",
    }
    assert all(
        not version.startswith(("^", "~", ">", "<"))
        for version in package["devDependencies"].values()
    )
    assert lock["lockfileVersion"] == 3
    assert not list(stitch_bundle.rglob("node_modules"))
    assert not (stitch_bundle / "skills/react-components/package.json").exists()
    assert not (stitch_bundle / "skills/react-components/package-lock.json").exists()
    assert not (stitch_bundle / "skills/react-native/package.json").exists()


def test_stitch_docs_use_bundle_paths_and_qualified_skills(stitch_bundle: Path) -> None:
    forbidden = (
        "configs/claude",
        "stitch-utilities",
        "stitch-skills/plugins",
        "npx skills add",
        "manifest parallel-agent",
    )
    for document in [
        *stitch_bundle.glob("skills/*/SKILL.md"),
        *stitch_bundle.glob("skills/*/README.md"),
    ]:
        source = document.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{document}: forbidden marker {marker}"

    shadcn_readme = (stitch_bundle / "skills/shadcn-ui/README.md").read_text()
    assert "../../CONTRIBUTING.md" not in shadcn_readme
    assert "../../LICENSE" not in shadcn_readme
    assert (stitch_bundle / "manifest-capabilities.yml").is_file()


def test_stitch_contract_declares_generated_runtime(stitch_bundle: Path) -> None:
    contract = load_contract(stitch_bundle / "manifest-capabilities.yml")
    runtime_paths = {component.path for component in contract.components.runtime}

    assert runtime_paths == {
        ".mcp.json",
        "extensions/ui-delivery-policy.ts",
        "package.json",
        "runtime/dist",
        "runtime/node/build.mjs",
        "runtime/node/package-lock.json",
        "runtime/node/package.json",
        "skills/extract-static-html/scripts",
        "skills/react-components/scripts",
        "skills/react-native/scripts",
    }
    assert contract.capabilities.mcp[CapabilityTier.OPTIONAL] == ("stitch",)
    assert contract.capabilities.executables[CapabilityTier.OPTIONAL] == (
        "chromium",
        "curl",
    )
