---
type: llm
focus: last_message
weight: 1
---
Score 1 only if the analysis correctly names the mechanism — bare `except:` clauses (ruff E722) catch every exception including ones that should propagate (e.g. KeyboardInterrupt/SystemExit) and hide real errors — AND states a category of `error-handling` AND gives a detection cue (bare `except:`/`except Exception:` with no re-raise) AND a prevention rule that keeps the failure visible: catch a specific exception type and then re-raise (optionally wrapped/with context), return an explicit failure result the caller must check, or route it to a central error handler. Score 0 if the mechanism is described wrong, any of category/detection-cue/prevention-rule is missing, or the prevention rule allows logging and then continuing (log-and-continue is itself the swallowed-error antipattern).
