#!/usr/bin/env python3
"""Build or verify bundle-local pure-Python dependencies from ``uv.lock``."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import IO

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "uv.lock"
VENDOR_ROOT = ROOT / "plugins/manifest-code-quality/skills/smoke-manage/vendor"
PACKAGE = "pyyaml"
PROJECT_NAME = "PyYAML"
LICENSE_NAME = "LICENSE.PyYAML"
METADATA_NAME = "VENDOR.json"
NATIVE_SUFFIXES = {".dll", ".dylib", ".pyd", ".so"}
EXPECTED_YAML_FILES = {
    "__init__.py",
    "composer.py",
    "constructor.py",
    "cyaml.py",
    "dumper.py",
    "emitter.py",
    "error.py",
    "events.py",
    "loader.py",
    "nodes.py",
    "parser.py",
    "reader.py",
    "representer.py",
    "resolver.py",
    "scanner.py",
    "serializer.py",
    "tokens.py",
}


class VendorError(ValueError):
    """A locked dependency or committed vendor tree is unsafe or inconsistent."""


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _locked_package() -> dict:
    with LOCK_PATH.open("rb") as handle:
        document = tomllib.load(handle)
    matches = [
        package
        for package in document.get("package", [])
        if str(package.get("name", "")).lower() == PACKAGE
    ]
    if len(matches) != 1:
        raise VendorError(
            f"expected one {PROJECT_NAME} lock entry, found {len(matches)}"
        )
    package = matches[0]
    source = package.get("source") or {}
    if source.get("registry") != "https://pypi.org/simple":
        raise VendorError(f"{PROJECT_NAME} must resolve from official PyPI")
    sdist = package.get("sdist") or {}
    url = str(sdist.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise VendorError(f"{PROJECT_NAME} sdist must use files.pythonhosted.org")
    digest = str(sdist.get("hash", ""))
    if not digest.startswith("sha256:"):
        raise VendorError(f"{PROJECT_NAME} sdist lacks a sha256 lock")
    return package


def _locked_hashes(package: dict) -> list[str]:
    artifacts = [package["sdist"], *(package.get("wheels") or [])]
    hashes = {str(artifact["hash"]) for artifact in artifacts}
    if any(not digest.startswith("sha256:") for digest in hashes):
        raise VendorError("every locked PyYAML artifact must use sha256")
    return sorted(hashes)


def _validated_members(
    archive: tarfile.TarFile, source_root: str
) -> dict[str, tarfile.TarInfo]:
    package_prefix = PurePosixPath(source_root) / "lib/yaml"
    license_path = PurePosixPath(source_root) / "LICENSE"
    selected: dict[str, tarfile.TarInfo] = {}
    seen_yaml: set[str] = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise VendorError(f"unsafe archive member: {member.name}")
        if path.suffix.lower() in NATIVE_SUFFIXES:
            raise VendorError(f"native library rejected: {member.name}")
        if path == license_path:
            if not member.isfile():
                raise VendorError("PyYAML license is not a regular file")
            selected[LICENSE_NAME] = member
            continue
        if path.parent != package_prefix:
            continue
        if member.isdir():
            continue
        if not member.isfile() or path.name not in EXPECTED_YAML_FILES:
            raise VendorError(f"unexpected PyYAML package file: {member.name}")
        seen_yaml.add(path.name)
        selected[f"yaml/{path.name}"] = member
    missing = sorted(EXPECTED_YAML_FILES - seen_yaml)
    if missing or LICENSE_NAME not in selected:
        detail = ", ".join(missing) or LICENSE_NAME
        raise VendorError(f"PyYAML sdist is missing required files: {detail}")
    return selected


def _read_member(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle: IO[bytes] | None = archive.extractfile(member)
    if handle is None:
        raise VendorError(f"cannot extract {member.name}")
    return handle.read()


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Manifest-vendor/1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
    except OSError as err:
        raise VendorError(f"cannot download {url}: {err}") from err


def _metadata(package: dict, files: dict[str, str]) -> dict:
    version = str(package["version"])
    digest = str(package["sdist"]["hash"]).removeprefix("sha256:")
    return {
        "files": dict(sorted(files.items())),
        "license": "MIT",
        "locked_hashes": _locked_hashes(package),
        "name": PROJECT_NAME,
        "sdist_sha256": digest,
        "source": f"https://pypi.org/project/{PROJECT_NAME}/{version}/",
        "source_archive": package["sdist"]["url"],
        "version": version,
    }


def build() -> None:
    package = _locked_package()
    version = str(package["version"])
    expected_digest = str(package["sdist"]["hash"]).removeprefix("sha256:")
    with tempfile.TemporaryDirectory(prefix="manifest-vendor-") as temp_dir:
        temp = Path(temp_dir)
        archive_path = temp / f"pyyaml-{version}.tar.gz"
        output = temp / "vendor"
        _download(str(package["sdist"]["url"]), archive_path)
        payload = archive_path.read_bytes()
        if _sha256_bytes(payload) != expected_digest:
            raise VendorError("downloaded PyYAML sdist does not match uv.lock")
        files: dict[str, str] = {}
        with tarfile.open(archive_path, mode="r:gz") as archive:
            selected = _validated_members(archive, f"pyyaml-{version}")
            for relative, member in sorted(selected.items()):
                content = _read_member(archive, member)
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                files[relative] = _sha256_bytes(content)
        (output / METADATA_NAME).write_text(
            json.dumps(_metadata(package, files), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if VENDOR_ROOT.exists():
            shutil.rmtree(VENDOR_ROOT)
        VENDOR_ROOT.parent.mkdir(parents=True, exist_ok=True)
        output.replace(VENDOR_ROOT)
    print(f"vendored {PROJECT_NAME} {version} into {VENDOR_ROOT.relative_to(ROOT)}")


def check() -> None:
    package = _locked_package()
    metadata_path = VENDOR_ROOT / METADATA_NAME
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise VendorError(f"cannot read {metadata_path}: {err}") from err
    declared = metadata.get("files")
    if not isinstance(declared, dict) or not all(
        isinstance(path, str)
        and isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
        for path, digest in declared.items()
    ):
        raise VendorError("VENDOR.json contains invalid file hashes")
    if metadata != _metadata(package, declared):
        raise VendorError("VENDOR.json does not match uv.lock provenance")
    expected_paths = {METADATA_NAME, *declared}
    actual_paths = {
        path.relative_to(VENDOR_ROOT).as_posix()
        for path in VENDOR_ROOT.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise VendorError("vendor tree contains missing or unexpected files")
    for relative, digest in declared.items():
        path = VENDOR_ROOT / relative
        if path.suffix.lower() in NATIVE_SUFFIXES:
            raise VendorError(f"native library rejected: {relative}")
        if _sha256_bytes(path.read_bytes()) != digest:
            raise VendorError(f"vendor hash drift: {relative}")
    print(f"vendored {PROJECT_NAME} {package['version']} is current")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args(argv)
    try:
        check() if args.check else build()
    except VendorError as err:
        print(f"vendor_bundle_dependencies.py: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
