"""Compatibility facade for the installed shared model-aware skill runner."""

try:
    from manifest_agent._model_policy.skill_run import (
        TASK_LIMIT,
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
except ModuleNotFoundError as error:
    if error.name != "manifest_agent._model_policy":
        raise
    from manifest_model_policy.skill_run import (
        TASK_LIMIT,
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
    "TASK_LIMIT",
    "SkillCommandOutcome",
    "SkillRecoveryStore",
    "SkillRunExecutionError",
    "SkillRunReport",
    "execute_skill_command",
    "load_policy_config",
    "read_task",
    "resolve_skill_path",
    "run_skill",
]
