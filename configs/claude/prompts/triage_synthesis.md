# Issue Triage Disagreement Synthesis

Multiple AI agents analyzed this issue triage decision and produced conflicting recommendations.
Your task is to synthesize their outputs into a unified recommendation.

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

## Synthesis Instructions

Your goal is to produce a **unified recommendation** that resolves the disagreement while
adhering to conservative triage principles.

### Resolution Priority Order

When agents disagree, apply this hierarchy to break ties:

1. **Conservatism**: Prefer keeping issues open over closing
   - False negatives (missing a stale issue) < False positives (closing active work)
   - When in doubt, mark for human review rather than auto-close

2. **Evidence**: Prefer concrete evidence over speculation
   - File deletion verified > File deletion inferred
   - Explicit staleness criteria > Heuristic patterns
   - Direct label checks > Description parsing

3. **User impact**: Reduce false-positive closures
   - Respect "planned" labels absolutely
   - Verify duplicate relationships are bidirectional in intent
   - Check for recent comments even if last update was months ago

4. **Process compliance**: Respect Linear workflow conventions
   - Never auto-close issues with certain labels (planned, blocked, waiting)
   - Follow team-specific priority conventions
   - Maintain audit trail for all mutations

### Disagreement Patterns

Common disagreement scenarios and how to resolve them:

#### Pattern 1: Duplicate Detection (Similarity 70-85%)

**Example:**

- Cursor: "Not duplicates - different technical approaches"
- Gemini: "Duplicates - same root cause"
- Claude: "Possibly duplicates - mark for human review"

**Resolution:**

- If ≥2 agents say "duplicate" AND similarity ≥80% → Mark as duplicate
- If 1 agent says "duplicate" OR similarity <80% → Flag for human review
- Never auto-close duplicates with <85% consensus

#### Pattern 2: Staleness (Inactive but has labels)

**Example:**

- Cursor: "Stale - no activity for 120 days"
- Gemini: "Not stale - has 'planned' label"
- Claude: "Stale but protected - manual review required"

**Resolution:**

- If ANY agent detects protected label → Do NOT auto-close
- If file deletion verified by ≥2 agents → Mark as stale (but still no auto-close if labeled)
- Always err on side of caution for labeled issues

#### Pattern 3: Priority Scoring (Disagreement ≥2 levels)

**Example:**

- Cursor: "Priority 2 (High) - critical security issue"
- Gemini: "Priority 4 (Low) - no user impact mentioned"
- Claude: "Priority 3 (Medium) - needs security audit first"

**Resolution:**

- If ≥2 agents agree on priority level → Use that level
- If all 3 disagree → Use median priority (middle value)
- If security mentioned by any agent → Never downgrade below Medium (P3)
- Recommend manual review for variance >1 level

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
    "areas_of_consensus": [
      "All agree issue is inactive",
      "All agree files are deleted"
    ],
    "areas_of_disagreement": [
      "Whether 'planned' label is still valid",
      "Urgency of closure"
    ]
  },
  "escalate_to_user": false,
  "recommended_next_steps": [
    "Verify 'planned' label intent with team lead",
    "Check if blocked issue dependency still exists"
  ]
}
```

## Validation Rules

Before finalizing your synthesis, verify:

- [ ] **Conservatism**: No false-positive closures (when uncertain, flag for review)
- [ ] **Evidence**: All claims backed by concrete data (file checks, label presence, date comparisons)
- [ ] **Protected labels**: Absolute respect for "planned", "blocked", "waiting"
- [ ] **Consensus threshold**: ≥85% required for auto-close actions
- [ ] **Audit trail**: Action includes clear reasoning and timestamp

## Examples

### Example 1: High-Confidence Duplicate

**Input:**

- Cursor: "95% duplicate - same title, same description"
- Gemini: "Duplicate - can merge safely"
- Claude: "Clear duplicate - mark relationship"

**Output:**

```json
{
  "unified_recommendation": {
    "action": "mark_duplicate",
    "target_issue": "ENG-124",
    "parameters": { "duplicate_of": "ENG-100" }
  },
  "confidence": "high",
  "consensus_score": 95,
  "requires_user_approval": false,
  "reasoning": "All three agents agree this is a duplicate with >90% similarity. Safe to auto-mark.",
  "caveats": [],
  "escalate_to_user": false
}
```

### Example 2: Stale with Protected Label

**Input:**

- Cursor: "Stale - 150 days inactive, all files deleted"
- Gemini: "Has 'planned' label - do NOT close"
- Claude: "Stale but labeled - manual review required"

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
  "caveats": [
    "Gemini correctly identified protected label",
    "Files are confirmed deleted"
  ],
  "escalate_to_user": true,
  "recommended_next_steps": [
    "Verify if 'planned' work is still roadmapped",
    "Consider removing label if no longer planned"
  ]
}
```

### Example 3: Priority Disagreement

**Input:**

- Cursor: "Priority 1 - security vulnerability"
- Gemini: "Priority 3 - low user impact"
- Claude: "Priority 2 - needs security review first"

**Output:**

```json
{
  "unified_recommendation": {
    "action": "update_priority",
    "target_issue": "ENG-300",
    "parameters": { "new_priority": 2 }
  },
  "confidence": "medium",
  "consensus_score": 60,
  "requires_user_approval": true,
  "reasoning": "Security mention by Cursor requires elevated priority. Using median (P2) given disagreement variance.",
  "caveats": [
    "Cursor sees critical security issue",
    "Gemini disagrees on user impact"
  ],
  "escalate_to_user": true,
  "recommended_next_steps": [
    "Security team review to determine true severity",
    "Update description with threat model"
  ]
}
```

## Critical Reminders

1. **When in doubt, escalate** - It's better to flag for human review than make a wrong decision
2. **Respect protective labels absolutely** - "planned", "blocked", "waiting" are sacrosanct
3. **Verify file deletion claims** - Don't trust heuristics, check filesystem
4. **Conservative thresholds** - ≥85% for auto-actions, <85% requires approval
5. **Audit everything** - Every action must have clear reasoning and timestamp

---

**Now synthesize the agent outputs above and return valid JSON following this template.**
