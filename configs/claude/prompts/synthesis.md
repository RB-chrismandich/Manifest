# Disagreement Synthesis Task

Multiple AI agents have provided analyses that need synthesis into a unified recommendation.
Evaluate each agent's output using weighted evidence scoring, categorize disagreements by
type, and apply explicit resolution strategies per category.

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

For each disagreement, first classify it by **disagreement type** (what kind of
disagreement it is), then by **domain category** (what area it concerns).

#### Disagreement Types

| Type               | Description                                                                                                          | Resolution Strategy                                                                                                                                                                                                                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Factual**        | Agents disagree on verifiable facts: API behavior, language semantics, tool capabilities, documented behavior        | **Verify**: Check official documentation, language specs, or source code. The verifiably correct agent wins. If unverifiable in this context, flag for human verification and note which claim to check.                                           |
| **Methodological** | Agents agree on the problem but propose different approaches or solutions                                            | **Compare**: Evaluate each approach on safety, correctness, maintainability, and alignment with project conventions. Select the approach that scores highest, or synthesize a hybrid if compatible. Document why the chosen approach is preferred. |
| **Scope**          | Agents cover different aspects -- one finds issues the others missed, or one analyzes more deeply in a narrower area | **Merge**: This is not a true conflict. Combine all unique findings into the unified recommendation. Credit each agent for its unique contributions. Only flag as a disagreement if the findings contradict each other.                            |

#### Domain Categories

| Category          | Description                                          | Additional Resolution Notes                                                     |
| ----------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Security**      | Security implications or mitigations                 | Always take the more conservative (safer) position regardless of evidence score |
| **Architectural** | Design patterns, module structure, system boundaries | Evaluate trade-offs; present options to user if impact is significant           |
| **Correctness**   | Logic errors, bugs, incorrect behavior               | Prefer the agent that cites specific code paths and edge cases                  |
| **Performance**   | Performance impact or optimization approach          | Prefer measurable evidence; note if benchmarking is needed                      |
| **Stylistic**     | Code style, naming, formatting, or preference        | Defer to project conventions; if none exist, note as low-priority               |

### Step 3: Weighted Evidence Evaluation

For each disagreement, score each agent's position across four dimensions.
Dimension weights vary by disagreement type to reflect what matters most for
each kind of conflict.

#### Scoring Dimensions

- **Specificity** (0-3): How precisely does the agent identify the issue?
  - 0 = No evidence, just assertion
  - 1 = General reasoning without specifics
  - 2 = References specific patterns, standards, or file regions
  - 3 = Cites exact code locations (file:line), documentation links, or benchmarks
- **Reasoning depth** (0-3): How thorough is the analysis?
  - 0 = Surface-level observation
  - 1 = Identifies the issue but not the implications
  - 2 = Analyzes implications and trade-offs
  - 3 = Full chain of reasoning with edge cases considered
- **Confidence signal** (0-2): How certain is the agent in its own finding?
  - 0 = Hedges heavily or contradicts itself
  - 1 = States finding without strong conviction
  - 2 = States finding with clear conviction and supporting reasoning
- **Consistency** (0-2): Does the position align with the agent's other findings?
  - 0 = Contradicts other findings from the same agent
  - 1 = Neutral / independent finding
  - 2 = Consistent with and reinforced by other findings

#### Dimension Weights by Disagreement Type

| Dimension         | Factual | Methodological | Scope  |
| ----------------- | ------- | -------------- | ------ |
| Specificity       | **x2**  | x1             | x1     |
| Reasoning depth   | x1      | **x2**         | x1     |
| Confidence signal | x1      | x1             | x1     |
| Consistency       | x1      | x1             | **x2** |

**Weighted score** = (specificity _weight) + (reasoning_ weight) + (confidence _weight) + (consistency_ weight).
Maximum possible score varies by type (Factual: 13, Methodological: 13, Scope: 12).

The higher-scoring position is preferred, with these overrides:

- **Security domain**: The safer position wins regardless of score
- **Factual type**: If one agent is verifiably correct, it wins regardless of score
- **Scope type**: Merge rather than pick a winner unless findings conflict

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

Return ONLY the following JSON object. Do not include commentary outside the JSON block.

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
        "gemini": {
          "specificity": 2,
          "reasoning": 2,
          "confidence_signal": 1,
          "consistency": 1,
          "weights_applied": "methodological",
          "weighted_total": 7
        },
        "cursor": {
          "specificity": 1,
          "reasoning": 2,
          "confidence_signal": 2,
          "consistency": 2,
          "weights_applied": "methodological",
          "weighted_total": 8
        },
        "claude": {
          "specificity": 3,
          "reasoning": 3,
          "confidence_signal": 2,
          "consistency": 2,
          "weights_applied": "methodological",
          "weighted_total": 12
        }
      },
      "resolution": "Use try-catch for external calls, Result for internal logic",
      "preferred_agent": "claude",
      "rationale": "Combines both approaches based on context; cites specific code paths",
      "override_applied": null
    },
    {
      "id": 2,
      "topic": "Input validation coverage",
      "disagreement_type": "scope",
      "domain_category": "security",
      "resolution_strategy": "merge",
      "gemini_position": "Validates query params only",
      "cursor_position": "Validates query params and headers",
      "claude_position": "Validates query params, headers, and request body",
      "evidence_scores": {
        "gemini": {
          "specificity": 1,
          "reasoning": 1,
          "confidence_signal": 1,
          "consistency": 1,
          "weights_applied": "scope",
          "weighted_total": 5
        },
        "cursor": {
          "specificity": 2,
          "reasoning": 2,
          "confidence_signal": 1,
          "consistency": 2,
          "weights_applied": "scope",
          "weighted_total": 8
        },
        "claude": {
          "specificity": 3,
          "reasoning": 3,
          "confidence_signal": 2,
          "consistency": 2,
          "weights_applied": "scope",
          "weighted_total": 12
        }
      },
      "resolution": "Validate all input surfaces: query params, headers, and request body",
      "preferred_agent": "claude",
      "rationale": "Most comprehensive coverage; scope disagreements merge unique findings",
      "override_applied": "security_domain: safer position preferred"
    }
  ],
  "scope_contributions": {
    "gemini_unique_findings": ["Found deprecated API usage in utils.py"],
    "cursor_unique_findings": ["Identified missing null check in parser.go:88"],
    "claude_unique_findings": [
      "Flagged race condition in worker pool initialization"
    ]
  },
  "unified_recommendation": "Final synthesized guidance combining the best of all analyses",
  "caveats": [
    "Uncertainty remains about Z — recommend benchmarking",
    "User should verify assumption about W"
  ],
  "confidence": 0.85,
  "action_items": [
    {
      "priority": "high",
      "action": "Fix SQL injection in auth.py:42",
      "source_agents": ["gemini", "claude"]
    },
    {
      "priority": "medium",
      "action": "Refactor error handling in service layer",
      "source_agents": ["claude"]
    },
    {
      "priority": "low",
      "action": "Consider renaming variables for clarity",
      "source_agents": ["cursor"]
    }
  ]
}
```

## Scoring Guide

- consensus_score >= 0.80: High agreement — proceed with unified recommendation
- consensus_score 0.50-0.79: Moderate agreement — highlight key differences to user
- consensus_score < 0.50: Low agreement — escalate for human review
