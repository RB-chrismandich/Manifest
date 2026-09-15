"""Shared cross-harness model policy API."""

from .controller import FallbackAction, FallbackController, FallbackDecision
from .failures import (
    FailureClass,
    FailureEvidence,
    classify_failure,
    sdk_failure_evidence,
)
from .frontmatter import (
    ModelFallbackMode,
    ModelPolicyError,
    SkillModelPolicy,
    normalize_harness,
    parse_skill_model_policy,
)
from .headless import (
    CliRoute,
    resolve_cli_route,
    resolve_provider_model,
    resolve_role_model_tier,
    run_headless_prompt,
)
from .policy_config import load_agent_roster, load_default_policy, resolve_policy_path
from .resolver import ResolvedModel, effective_fallback_mode, resolve_chain
from .skill_execution import build_provider_invocation
from .skill_run import (
    SkillCommandOutcome,
    SkillRecoveryStore,
    SkillRunExecutionError,
    SkillRunReport,
    execute_skill_command,
    load_policy_config,
    read_task,
    resolve_skill_path,
    run_skill,
)

__all__ = [
    "CliRoute",
    "FailureClass",
    "FailureEvidence",
    "FallbackAction",
    "FallbackController",
    "FallbackDecision",
    "ModelFallbackMode",
    "ModelPolicyError",
    "ResolvedModel",
    "SkillCommandOutcome",
    "SkillModelPolicy",
    "SkillRecoveryStore",
    "SkillRunExecutionError",
    "SkillRunReport",
    "build_provider_invocation",
    "classify_failure",
    "effective_fallback_mode",
    "execute_skill_command",
    "load_agent_roster",
    "load_default_policy",
    "load_policy_config",
    "normalize_harness",
    "parse_skill_model_policy",
    "read_task",
    "resolve_chain",
    "resolve_cli_route",
    "resolve_policy_path",
    "resolve_provider_model",
    "resolve_role_model_tier",
    "resolve_skill_path",
    "run_headless_prompt",
    "run_skill",
    "sdk_failure_evidence",
]
