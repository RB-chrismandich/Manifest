"""manifest-delegate dispatcher package.

Split out of a single scripts/delegate.py once that file passed the Code
Constitution size ceiling (CON-002); research.md D5 records the revised
placement. Still stdlib-only, still one process — only the file layout changed.

Cross-module references are qualified (`registry.load_registry`, not
`from .registry import load_registry`) so the import graph tolerates the cycles
the original single file had for free, and so a test patching a module-level
constant patches the module that OWNS it.

This module re-exports the flat names so `delegate.load_registry` keeps working.
Note the asymmetry: a re-exported function is the same object, but a re-exported
CONSTANT is a copy — rebinding `delegate.SESSIONS_CAPTURE_FILE` would not change
what `transfer._captured_sessions_for_cwd` reads. Patch the owning module:
`delegate.transfer.SESSIONS_CAPTURE_FILE`.
"""

from . import (  # noqa: F401  (submodules are the patch targets)
    backend,
    cli,
    config,
    constants,
    envelope,
    gate,
    jobs_cli,
    jobstore,
    process,
    readiness,
    registry,
    review,
    setup,
    task,
    transfer,
    worker,
)
from .backend import (  # noqa: F401  (flat re-export)
    DEFAULT_BUDGET_SECONDS,
    REGISTRY_PATH_ENV,
    _executable_missing,
    _read_prompt,
    _registry_path_override,
    _substitute_argv,
    build_invoke_argv,
    build_resume_argv,
    check_payload_limits,
    extract_session_ref,
    map_model_tier,
    resolve_budget,
    resolve_model_tier,
)
from .cli import (  # noqa: F401  (flat re-export)
    _IMPLEMENTED_SUBCOMMANDS,
    _SUBCOMMAND_HELP,
    _add_review_args,
    _add_setup_args,
    _add_subcommand_args,
    _add_task_args,
    _positive_int_arg,
    build_parser,
    main,
)
from .config import (  # noqa: F401  (flat re-export)
    FACTORY_DEFAULTS,
    GATE_BUDGET_CAP_SECONDS,
    _config_search_dirs,
    _find_user_config_path,
    _is_positive_int,
    _merge_review_gate,
    _merge_user_config_data,
    _parse_user_config_file,
    _validate_backend_entry,
    _write_review_gate_json,
    _write_review_gate_yaml,
    _yaml_module,
    effective_backend_enabled,
    load_model_tiers,
    load_services_disabled,
    load_user_config,
    write_review_gate_config,
)
from .constants import (  # noqa: F401  (flat re-export)
    CONFIG_DIR_ENV,
    DANGEROUS_TOKEN_RE,
    DEFAULT_REGISTRY_PATH,
    DELEGATIONS_DIR_ENV,
    HOME_CONFIG_DIR,
    KEEP_LAST_N,
    PLACEHOLDER_RE,
    PLUGIN_DIR,
    SCRIPT_DIR,
    SHELL_METACHAR_RE,
    SUBCOMMANDS,
    err,
)
from .envelope import (  # noqa: F401  (flat re-export)
    ENVELOPE_ARRAY_FIELDS,
    ENVELOPE_OUTCOMES,
    FENCE_RE,
    REQUIRED_ENVELOPE_FIELDS,
    _envelope_type_errors,
    _extract_last_json_block,
    _failure_envelope,
    normalize_envelope,
)
from .gate import (  # noqa: F401  (flat re-export)
    _GATE_PROMPT_INSTRUCTIONS,
    _finishing_turn_has_edits,
    _gate_allow,
    _gate_build_prompt,
    _gate_execute,
    _gate_format_block,
    _gate_resolve_backend,
    _gate_validate_findings,
    cmd_gate,
)
from .jobs_cli import (  # noqa: F401  (flat re-export)
    _reap_raced_pgid,
    _terminate_job_processes,
    cmd_cancel,
    cmd_result,
    cmd_status,
)
from .jobstore import (  # noqa: F401  (flat re-export)
    FALLBACK_PENDING_EXPIRES_AFTER_SECONDS,
    FALLBACK_PENDING_RESOLUTION_ACTIONS,
    NON_TERMINAL_STATES,
    RESOLVABLE_STATES,
    SETTLED_STATES,
    TERMINAL_STATES,
    JobStore,
    _atomic_write_0600,
    _mkdir_0700,
    _write_0600,
    delegations_root,
    workspace_slug,
)
from .process import (  # noqa: F401  (flat re-export)
    _WORKER_LOCK_FDS,
    BACKEND_LOCK_FILENAME,
    BACKEND_PGID_FILENAME,
    DRAIN_GRACE_SECONDS,
    MAX_CAPTURED_OUTPUT_BYTES,
    SESSION_CAPTURE_HEAD_BYTES,
    WORKER_LOCK_FILENAME,
    WORKER_STARTUP_GRACE_SECONDS,
    _acquire_worker_lifetime_lock,
    _backend_alive,
    _backend_preexec,
    _BoundedHead,
    _BoundedTail,
    _clear_pgid_tracking,
    _drain_into,
    _feed_stdin,
    _has_pgid_tracking,
    _kill_pgid,
    _launch_backend,
    _make_pgid_persister,
    _read_bounded_file,
    _read_pgid_file,
    _reap_cancelled_orphan,
    _spawn_backend,
    _worker_alive,
)
from .readiness import (  # noqa: F401  (flat re-export)
    _AUTH_ERROR_PATTERN,
    _cmd_setup_gate_toggle,
    _init_readiness_row,
    _looks_like_auth_error,
    _probe_enabled_state,
    _probe_retired_state,
    _probe_version_and_auth,
    _run_readiness_probe,
    probe_backend_readiness,
)
from .registry import (  # noqa: F401  (flat re-export)
    RegistryError,
    _load_registry_raw,
    _validate_argv_template,
    _validate_registry_aliases,
    _validate_registry_argv_fields,
    _validate_registry_entry,
    _validate_registry_input_shape,
    _walk_strings,
    load_registry,
    load_registry_or_exit,
    resolve_backend,
)
from .review import (  # noqa: F401  (flat re-export)
    _SEVERITY_RANK,
    ReviewDiffError,
    _build_review_prompt,
    _dispatch_review,
    _run_git,
    _scope_diff,
    _untracked_diff,
    assemble_review_diff,
    cmd_review,
)
from .setup import (  # noqa: F401  (flat re-export)
    cmd_setup,
)
from .task import (  # noqa: F401  (flat re-export)
    _PROMPT_SUMMARY_MAX_CHARS,
    _build_task_extra,
    _build_task_prompt,
    _check_task_backend_ready,
    _dispatch_task,
    _find_last_job_for_backend,
    _resolve_job_id,
    _resolve_sole_active,
    _resolve_task_backend_entry,
    _resolve_task_resume,
    _resolve_task_second_opinion,
    _warn_if_second_opinion_same_backend,
    cmd_task,
)
from .transfer import (  # noqa: F401  (flat re-export)
    SESSIONS_CAPTURE_FILE,
    TRANSCRIPT_PATH_ENV,
    TRANSCRIPT_ROOTS,
    ShortHelpParser,
    _app_server_import,
    _captured_sessions_for_cwd,
    _check_transfer_method,
    _print_transfer_result,
    _resolve_transfer_entry,
    _resolve_transfer_source,
    _session_captured_transcript,
    _validate_transcript_source,
    cmd_resume_candidate,
    cmd_transfer,
)
from .worker import (  # noqa: F401  (flat re-export)
    _run_backend_and_finish,
    _run_backend_foreground,
    _spawn_worker,
    cmd_worker,
)

# `from manifest_delegate import *` in scripts/delegate.py must carry the
# underscore-prefixed helpers too — tests and hooks reach for them by name on
# the facade, and star-import drops every `_`-prefixed name unless __all__ says
# otherwise. Derived from the namespace rather than written out: a hand-listed
# copy would be a 180-line data table that silently rots as modules change.
__all__ = [_n for _n in dir() if not _n.startswith("__")]
