"""Strict portable model policy parsing for skill frontmatter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import yaml

SUPPORTED_HARNESSES = frozenset(
    {"claude", "codex", "gemini", "cursor", "antigravity", "devin"}
)
PORTABLE_TIERS = frozenset(
    {"auto", "mini", "flash", "advanced", "haiku", "sonnet", "opus", "pro"}
)


class ModelPolicyError(ValueError):
    """Skill model metadata is malformed or cannot be represented safely."""


class ModelFallbackMode(StrEnum):
    AUTO = "auto"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class SkillModelPolicy:
    chains: Mapping[str, tuple[str, ...]]
    fallback_mode: ModelFallbackMode | None = None


def normalize_harness(name: str) -> str:
    if not isinstance(name, str):
        raise ModelPolicyError("harness name must be a string")
    normalized = (
        "antigravity" if name.strip().lower() == "agy" else name.strip().lower()
    )
    if normalized not in SUPPORTED_HARNESSES:
        raise ModelPolicyError(f"unknown harness {name!r}")
    return normalized


def _frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ModelPolicyError(f"unable to read skill frontmatter: {error}") from error
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ModelPolicyError("unterminated skill frontmatter")
    try:
        value = yaml.safe_load(text[4:end])
    except yaml.YAMLError as error:
        raise ModelPolicyError(f"invalid skill frontmatter YAML: {error}") from error
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ModelPolicyError("skill frontmatter must be a mapping")
    return value


def parse_skill_model_policy(path: Path) -> SkillModelPolicy:
    document = _frontmatter(path)
    raw_models = document.get("models")
    raw_fallback = document.get("model_fallback")
    if raw_models is None and raw_fallback is None:
        return SkillModelPolicy(MappingProxyType({}))
    if raw_models is None:
        raw_models = {}
    if not isinstance(raw_models, dict):
        raise ModelPolicyError("models must be a mapping")
    chains: dict[str, tuple[str, ...]] = {}
    for raw_harness, raw_chain in raw_models.items():
        harness = normalize_harness(raw_harness)
        if harness in chains:
            raise ModelPolicyError(f"duplicate harness model chain for {harness}")
        if not isinstance(raw_chain, list) or not raw_chain or len(raw_chain) > 4:
            raise ModelPolicyError(
                f"{raw_harness} model chain must contain 1 to 4 tiers"
            )
        if any(
            not isinstance(tier, str) or tier not in PORTABLE_TIERS
            for tier in raw_chain
        ):
            raise ModelPolicyError(
                f"{raw_harness} model chain contains an unknown tier"
            )
        if len(set(raw_chain)) != len(raw_chain):
            raise ModelPolicyError(
                f"{raw_harness} model chain contains duplicate tiers"
            )
        if "auto" in raw_chain and raw_chain[-1] != "auto":
            raise ModelPolicyError("auto must be the final model tier")
        chains[harness] = tuple(raw_chain)
    fallback_mode = None
    if raw_fallback is not None:
        if not isinstance(raw_fallback, dict) or set(raw_fallback) != {"mode"}:
            raise ModelPolicyError("model_fallback must contain only mode")
        try:
            fallback_mode = ModelFallbackMode(raw_fallback["mode"])
        except (TypeError, ValueError) as error:
            raise ModelPolicyError(
                "model_fallback.mode must be auto or confirm"
            ) from error
    return SkillModelPolicy(MappingProxyType(chains), fallback_mode)
