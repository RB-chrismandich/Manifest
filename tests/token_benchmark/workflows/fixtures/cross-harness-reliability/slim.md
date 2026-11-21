# Cross-harness reliability

Return a structured assessment for the supplied sanitized scenario. Report completion state, required
interventions, factual corrections, retained constraints, and evidence as separate fields. Distinguish
blocked, stale, unknown, not-run, and complete outcomes. Counts and source revisions must match the
supplied evidence exactly; do not infer success from empty evidence or connector capability. Preserve
authorization scope and evidence provenance on resume. For GitLab, use only GitLab-supported commands,
preserve unrelated staged and unstaged changes, reuse an existing source-to-target merge request,
and treat an empty diff as no successful publication.
