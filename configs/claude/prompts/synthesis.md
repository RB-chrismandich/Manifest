# Disagreement Synthesis Task

Multiple AI agents have provided analyses that need synthesis into a unified recommendation.
Evaluate each agent's output using weighted evidence and categorize disagreements.

## Original Context

{ORIGINAL_TASK}

## Agent Outputs

### Gemini Output

{GEMINI_OUTPUT}

### Cursor Output

{CURSOR_OUTPUT}

### Claude Output

{CLAUDE_OUTPUT}

## Synthesis Instructions

### Step 1: Identify Agreements

List all points where agents converge. Agreements carry higher weight — if all three
agents independently reach the same conclusion, treat it as high-confidence guidance.

### Step 2: Identify and Categorize Disagreements

For each disagreement, classify it into one of these categories:

| Category | Description | Resolution Strategy |
|----------|-------------|---------------------|
| **Factual** | Agents disagree on verifiable facts (API behavior, language semantics, tool capabilities) | Verify against documentation; the correct agent wins |
| **Stylistic** | Agents disagree on code style, naming, formatting, or preference | Defer to project conventions; if none exist, note as low-priority |
| **Architectural** | Agents disagree on design patterns, module structure, or system boundaries | Evaluate trade-offs; present options to user if impact is significant |
| **Security** | Agents disagree on security implications or mitigations | Always take the more conservative (safer) position |
| **Performance** | Agents disagree on performance impact or optimization approach | Prefer measurable evidence; note if benchmarking is needed |

### Step 3: Weighted Evidence Evaluation

For each disagreement, score each agent's position:

- **Evidence quality** (0-3): Does the agent cite specific code, documentation, or standards?
  - 0 = No evidence, just assertion
  - 1 = General reasoning without specifics
  - 2 = References specific patterns or standards
  - 3 = Cites exact code locations, documentation links, or benchmarks
- **Reasoning depth** (0-3): How thorough is the analysis?
  - 0 = Surface-level observation
  - 1 = Identifies the issue but not the implications
  - 2 = Analyzes implications and trade-offs
  - 3 = Full chain of reasoning with edge cases considered
- **Consistency** (0-2): Does the position align with the agent's other findings?
  - 0 = Contradicts other findings from the same agent
  - 1 = Neutral / independent finding
  - 2 = Consistent with and reinforced by other findings

Total score per position = evidence + reasoning + consistency (max 8).
The higher-scoring position is preferred unless the disagreement is security-related
(in which case the safer position wins regardless of score).

### Step 4: Determine Priority

For each disagreement, assess:

1. **Safety**: Which position is safer from a security standpoint?
2. **Correctness**: Which position is more technically correct?
3. **Practicality**: Which position is easier to implement and maintain?
4. **Alignment**: Which position better matches project conventions and standards?

### Step 5: Synthesize Unified Recommendation

Produce guidance that:

- Incorporates all agreements as baseline recommendations
- Resolves each disagreement with a clear rationale
- Notes any caveats or conditions where the alternative position might be better
- Flags any remaining uncertainties that require human judgment

## Output Format

```json
{
  "consensus_score": 0.75,
  "total_findings": 12,
  "agreements": 9,
  "disagreements": [
    {
      "id": 1,
      "topic": "Error handling approach",
      "category": "architectural",
      "gemini_position": "Use try-catch with specific exceptions",
      "cursor_position": "Use Result type pattern",
      "claude_position": "Use try-catch for external calls, Result for internal",
      "evidence_scores": {
        "gemini": {"evidence": 2, "reasoning": 2, "consistency": 1, "total": 5},
        "cursor": {"evidence": 1, "reasoning": 2, "consistency": 2, "total": 5},
        "claude": {"evidence": 3, "reasoning": 3, "consistency": 2, "total": 8}
      },
      "resolution": "Use try-catch for external calls, Result for internal logic",
      "preferred_agent": "claude",
      "rationale": "Combines both approaches based on context; cites specific code paths"
    }
  ],
  "unified_recommendation": "Final synthesized guidance combining the best of all analyses",
  "caveats": [
    "Uncertainty remains about Z — recommend benchmarking",
    "User should verify assumption about W"
  ],
  "confidence": 0.85,
  "action_items": [
    {"priority": "high", "action": "Fix SQL injection in auth.py:42"},
    {"priority": "medium", "action": "Refactor error handling in service layer"},
    {"priority": "low", "action": "Consider renaming variables for clarity"}
  ]
}
```

## Scoring Guide

- consensus_score >= 0.80: High agreement — proceed with unified recommendation
- consensus_score 0.50-0.79: Moderate agreement — highlight key differences to user
- consensus_score < 0.50: Low agreement — escalate for human review
