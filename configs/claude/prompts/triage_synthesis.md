# Issue Triage Disagreement Synthesis

Agents produced conflicting triage recommendations. Synthesize them into one unified recommendation under conservative
triage principles.

## Triage Context

**Scenario**: {SCENARIO_TYPE}
**Issue(s)**: {ISSUE_NUMBERS}
**Original Query**: {ORIGINAL_TASK}

## Agent Outputs

### Cursor Analysis

{CURSOR_OUTPUT}

### Gemini Analysis

{GEMINI_OUTPUT}

### Claude Analysis

{CLAUDE_OUTPUT}

## Resolution Priority Order

Break ties with this hierarchy:

1. **Conservatism**: Prefer keeping issues open over closing. False negatives (missing a stale issue) < false positives
   (closing active work). When in doubt, flag for human review rather than auto-close.
2. **Evidence**: Concrete over speculative — verified file deletion > inferred; explicit staleness
   criteria > heuristic patterns; direct label checks > description parsing. Verify file-deletion
   claims against the filesystem, not heuristics.
3. **User impact**: Respect "planned" labels absolutely; verify duplicate relationships are bidirectional in intent;
   check for recent comments even if last update was months ago.
4. **Process compliance**: Never auto-close issues with protective labels (planned, blocked, waiting); follow
   team-specific priority conventions; maintain an audit trail for all mutations.

## Disagreement Resolution Rules

**Duplicate detection (similarity 70-85%):**

- ≥2 agents say "duplicate" AND similarity ≥80% → Mark as duplicate
- 1 agent says "duplicate" OR similarity <80% → Flag for human review
- Never auto-close duplicates with <85% consensus

**Staleness (inactive but has labels):**

- ANY agent detects a protected label → Do NOT auto-close
- File deletion verified by ≥2 agents → Mark as stale (but still no auto-close if labeled)
- Always err on the side of caution for labeled issues

**Priority scoring (disagreement ≥2 levels):**

- ≥2 agents agree on a priority level → Use that level
- All 3 disagree → Use the median priority (middle value)
- Security mentioned by any agent → Never downgrade below Medium (P3)
- Variance >1 level → Recommend manual review

## Output Format

Return **valid JSON** with the following structure:

```json
{
  "unified_recommendation": {
    "action": "mark_duplicate | close_stale | update_priority | manual_review",
    "target_issue": "ISSUE-123",
    "related_issue": "ISSUE-456",
    "parameters": {
      "new_priority": 3,
      "close_comment": "Closing as stale: ...",
      "duplicate_of": "ISSUE-456"
    }
  },
  "confidence": "high | medium | low",
  "consensus_score": 75,
  "requires_user_approval": true,
  "reasoning": "Brief explanation of why this recommendation was chosen (2-3 sentences)",
  "caveats": [
    "Caveat 1: Remaining uncertainty about file deletion",
    "Caveat 2: One agent noted recent comment activity"
  ],
  "agent_agreement": {
    "areas_of_consensus": ["All agree issue is inactive", "All agree files are deleted"],
    "areas_of_disagreement": ["Whether 'planned' label is still valid", "Urgency of closure"]
  },
  "escalate_to_user": false,
  "recommended_next_steps": [
    "Verify 'planned' label intent with team lead",
    "Check if blocked issue dependency still exists"
  ]
}
```

## Validation Rules

Before finalizing, verify:

- [ ] **Conservatism**: No false-positive closures (when uncertain, flag for review)
- [ ] **Evidence**: All claims backed by concrete data (file checks, label presence, date comparisons)
- [ ] **Protected labels**: Absolute respect for "planned", "blocked", "waiting"
- [ ] **Consensus threshold**: ≥85% required for auto-close/auto-actions; <85% requires approval
- [ ] **Audit trail**: Action includes clear reasoning and timestamp

## Example: Stale with Protected Label

**Input:** Cursor: "Stale - 150 days inactive, all files deleted"; Gemini: "Has 'planned' label -
do NOT close"; Claude: "Stale but labeled - manual review required"

**Output:**

```json
{
  "unified_recommendation": {
    "action": "manual_review",
    "target_issue": "ENG-200"
  },
  "confidence": "medium",
  "consensus_score": 66,
  "requires_user_approval": true,
  "reasoning": "Issue meets staleness criteria but has 'planned' label. Conservative approach: flag for human review.",
  "caveats": ["Gemini correctly identified protected label", "Files are confirmed deleted"],
  "escalate_to_user": true,
  "recommended_next_steps": ["Verify if 'planned' work is still roadmapped", "Consider removing label if no longer
  planned"]
}
```

---

**Now synthesize the agent outputs above and return valid JSON following this template.**
