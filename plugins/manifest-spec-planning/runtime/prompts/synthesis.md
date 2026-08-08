# Disagreement Synthesis Task

Synthesize multiple agents' analyses into a unified recommendation: identify agreements, categorize
disagreements, score positions with weighted evidence, and apply the resolution strategy per category.

## Original Context

{ORIGINAL_TASK}

## Agent Outputs

{AGENT_OUTPUTS}

## Synthesis Instructions

### Step 1: Identify Agreements

List points where agents converge. Independent convergence = high-confidence guidance.

### Step 2: Categorize Each Disagreement

Classify by **disagreement type** and **domain category**.

| Type | Resolution Strategy |
|------|---------------------|
| **Factual** (verifiable facts: API behavior, language semantics, tool capabilities, documented behavior) | **Verify** against official docs, specs, or source; the verifiably correct agent wins. If unverifiable here, flag for human verification and name the claim to check. |
| **Methodological** (same problem, different proposed approaches) | **Compare** on safety, correctness, maintainability, and project conventions; select the highest scorer or a compatible hybrid; document why. |
| **Scope** (different coverage — one finds issues others missed, or analyzes deeper in a narrower area) | **Merge**: not a true conflict. Combine all unique findings; credit each agent. Only a disagreement if findings contradict. |

| Domain Category | Resolution Notes |
|----------|----------------------------|
| **Security** (implications/mitigations) | Take the more conservative (safer) position regardless of evidence score |
| **Architectural** (design patterns, module structure, system boundaries) | Evaluate trade-offs; present options to user if impact is significant |
| **Correctness** (logic errors, bugs) | Prefer the agent citing specific code paths and edge cases |
| **Performance** (impact, optimization approach) | Prefer measurable evidence; note if benchmarking is needed |
| **Stylistic** (style, naming, formatting) | Defer to project conventions; if none, note as low-priority |

### Step 3: Weighted Evidence Evaluation

Score each agent's position on each disagreement:

- **Specificity** (0-3): 0 = assertion only; 1 = general reasoning; 2 = references specific patterns, standards,
  or file regions; 3 = cites exact file:line, documentation links, or benchmarks
- **Reasoning depth** (0-3): 0 = surface observation; 1 = issue without implications; 2 = implications and
  trade-offs; 3 = full reasoning chain with edge cases
- **Confidence signal** (0-2): 0 = hedges heavily or self-contradicts; 1 = no strong conviction; 2 = clear
  conviction with supporting reasoning
- **Consistency** (0-2): 0 = contradicts the agent's other findings; 1 = neutral/independent; 2 = reinforced by other findings

Dimension weights by disagreement type:

| Dimension | Factual | Methodological | Scope |
|-----------|---------|----------------|-------|
| Specificity | **x2** | x1 | x1 |
| Reasoning depth | x1 | **x2** | x1 |
| Confidence signal | x1 | x1 | x1 |
| Consistency | x1 | x1 | **x2** |

**Weighted score** = sum of (dimension x weight). Max: Factual 13, Methodological 13, Scope 12.

Higher score wins, with overrides:

- **Security domain**: safer position wins regardless of score
- **Factual type**: verifiably correct agent wins regardless of score
- **Scope type**: merge rather than pick a winner unless findings conflict

### Step 4: Determine Priority

Per disagreement assess: safety (safer position?), correctness (more technically correct?), practicality
(easier to implement/maintain?), alignment (matches project conventions?).

### Step 5: Synthesize Unified Recommendation

Incorporate agreements as baseline; resolve each disagreement with clear rationale; note caveats where the
alternative might be better; flag remaining uncertainties for human judgment.

## Output Format

Return ONLY the following JSON object. No commentary outside the JSON block.

```json
{
  "consensus_score": 0.75,
  "total_findings": 12,
  "agreements": 9,
  "disagreements": [
    {
      "id": 1,
      "topic": "Error handling approach",
      "disagreement_type": "methodological",
      "domain_category": "architectural",
      "resolution_strategy": "compare",
      "gemini_position": "Use try-catch with specific exceptions",
      "cursor_position": "Use Result type pattern",
      "claude_position": "Use try-catch for external calls, Result for internal",
      "evidence_scores": {
        "gemini": {"specificity": 2, "reasoning": 2, "confidence_signal": 1, "consistency": 1, "weights_applied": "methodological", "weighted_total": 7},
        "cursor": {"specificity": 1, "reasoning": 2, "confidence_signal": 2, "consistency": 2, "weights_applied": "methodological", "weighted_total": 8},
        "claude": {"specificity": 3, "reasoning": 3, "confidence_signal": 2, "consistency": 2, "weights_applied": "methodological", "weighted_total": 12}
      },
      "resolution": "Use try-catch for external calls, Result for internal logic",
      "preferred_agent": "claude",
      "rationale": "Combines both approaches based on context; cites specific code paths",
      "override_applied": null
    }
  ],
  "scope_contributions": {
    "gemini_unique_findings": ["Found deprecated API usage in utils.py"],
    "cursor_unique_findings": ["Identified missing null check in parser.go:88"],
    "claude_unique_findings": ["Flagged race condition in worker pool initialization"]
  },
  "unified_recommendation": "Final synthesized guidance combining the best of all analyses",
  "caveats": [
    "Uncertainty remains about Z — recommend benchmarking",
    "User should verify assumption about W"
  ],
  "confidence": 0.85,
  "action_items": [
    {"priority": "high", "action": "Fix SQL injection in auth.py:42", "source_agents": ["gemini", "claude"]},
    {"priority": "medium", "action": "Refactor error handling in service layer", "source_agents": ["claude"]},
    {"priority": "low", "action": "Consider renaming variables for clarity", "source_agents": ["cursor"]}
  ]
}
```

Set `"override_applied"` to a string (e.g. `"security_domain: safer position preferred"`) when an override
decided the resolution, else `null`.

## Scoring Guide

- consensus_score >= 0.80: High agreement — proceed with unified recommendation
- consensus_score 0.50-0.79: Moderate agreement — highlight key differences to user
- consensus_score < 0.50: Low agreement — escalate for human review
