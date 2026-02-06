# Disagreement Synthesis Task

Two AI agents (Gemini and Cursor) have provided conflicting analyses.
Your task is to synthesize their outputs into a unified recommendation.

## Original Context

{ORIGINAL_TASK}

## Gemini Output

{GEMINI_OUTPUT}

## Cursor Output

{CURSOR_OUTPUT}

## Synthesis Instructions

### Step 1: Identify Core Disagreements

List each specific point where the agents differ in their analysis or recommendations.

### Step 2: Evaluate Reasoning

For each disagreement:

- Assess the strength and validity of each agent's rationale
- Consider which agent has better context or expertise for that specific issue
- Note any factual errors or logical flaws

### Step 3: Determine Priority

For each disagreement:

- Which position is safer from a security standpoint?
- Which position is more correct technically?
- Which position aligns better with best practices?

### Step 4: Synthesize Recommendation

Produce unified guidance that takes the best from both agents.

## Output Format

```json
{
  "consensus_score": 0.75,
  "disagreements": [
    {
      "topic": "Error handling approach",
      "gemini_position": "Use try-catch with specific exceptions",
      "cursor_position": "Use Result type pattern",
      "resolution": "Use try-catch for external calls, Result for internal logic",
      "preferred_agent": "neither",
      "rationale": "Both approaches valid for different contexts"
    }
  ],
  "agreements": [
    "Both agents agree on X",
    "Both agents agree on Y"
  ],
  "unified_recommendation": "Final synthesized guidance combining the best of both analyses",
  "caveats": [
    "Uncertainty remains about Z",
    "User should verify assumption about W"
  ],
  "confidence": 0.85
}
```

## Scoring Guide

- consensus_score >= 0.80: High agreement, proceed with confidence
- consensus_score 0.50-0.79: Moderate agreement, highlight key differences
- consensus_score < 0.50: Low agreement, escalate for human review
