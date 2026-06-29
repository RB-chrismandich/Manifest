# Contract: Enforcement test

**File**: `tests/bats/subagent_policy.bats` (preferred — matches `context_budget.bats`,
`commands_doc_drift.bats`) or `tests/python/test_subagent_policy.py` if assertions grow complex.
**Wired into**: the same CI job that runs `bats tests/bats/` / `pytest tests/python/`.

## Inputs (read at test time)

- Live listing of `.skillshare/skills/*/` directories that contain a `SKILL.md` (counted
  **dynamically** — no hardcoded total).
- Parsed `tool_policies` from `configs/claude/config/command_config.yml`.
- The body text of each `SKILL.md`.

## Assertions

| ID | Assertion | Spec link |
|----|-----------|-----------|
| T1 | Every skill dir with a `SKILL.md` has a `tool_policies` entry containing `subagents`. | SC-001, VR-1 |
| T2 | `subagents` value ∈ {`always`,`conditional`,`never`}. | data-model |
| T3 | `subagents: conditional` ⇒ non-empty `subagent_trigger`. | VR-2 |
| T4 | `subagents: never` ⇒ rationale present (`subagent_rationale` or SKILL.md body marker). | SC-003, VR-3 |
| T5 | `subagents: always|conditional` ⇒ SKILL.md body contains a dispatch trigger that links the shared rules. | SC-002, VR-4 |
| T6 | No `subagents: never` skill body instructs dispatch (no contradiction). | SC-004, VR-5 |
| T7 | (advisory) `subagent_trigger` uses `>= 3` or a recognized scale gate. | VR-6 |

## Exit behavior

- Any failed assertion → non-zero exit (blocks CI), naming the offending skill(s).
- New skill added without a `subagents` disposition → T1 fails → forces the author to classify it.

## Out of scope for the test

- It does NOT evaluate whether a disposition is "correct" (a judgment call), only that it exists, is
  well-formed, and is internally consistent with the prose.
