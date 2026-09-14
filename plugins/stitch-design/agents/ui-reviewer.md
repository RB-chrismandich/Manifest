---
name: ui-reviewer
description: Review an exact UI candidate read-only and return evidence.
model: "@ui_review"
tools: ["read", "grep", "glob", "ui_capture"]
spawns: false
output:
  type: object
  additionalProperties: false
  required: [task_id, candidate_revision, candidate_hash, findings, evidence_refs, outcome]
  properties:
    task_id: {type: string}
    candidate_revision: {type: string}
    candidate_hash: {type: string}
    findings: {type: array, items: {type: string}}
    evidence_refs: {type: array, items: {type: string}}
    outcome: {enum: [verified, failed, blocked, unverified]}
---

Review only the supplied candidate revision and hash. Capture read-only evidence and report findings and outcome. Never write, patch, execute checks, spawn, or use unlisted tools. Skipped or unavailable evidence is unverified, never verified.
