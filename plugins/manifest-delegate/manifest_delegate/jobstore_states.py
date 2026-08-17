"""Lifecycle state sets shared by delegate job-store responsibilities."""

TERMINAL_STATES = {
    "completed",
    "failed",
    "timeout",
    "cancelled",
    "fallback_rejected",
    "dispatch_unknown",
}
RESOLVABLE_STATES = {"fallback_pending", "fallback_prepared"}
SETTLED_STATES = TERMINAL_STATES | RESOLVABLE_STATES
NON_TERMINAL_STATES = {"queued", "running", "fallback_prepared"}
FALLBACK_PENDING_RESOLUTION_ACTIONS = frozenset({"approve", "reject", "cancel"})
FALLBACK_PENDING_EXPIRES_AFTER_SECONDS = None
