# Effective goal creation: evidence ledger

Date: 2026-09-08. Audience: Manifest maintainers.
Purpose: support the goal-compose design and its implementation plan.

## Decision

Compose an observable outcome with authoritative context, explicit boundaries,
and evidence for completion. Keep plans adaptable and host capabilities explicit.
Ship as an opt-in planning skill only after evaluating it. The five-section
contract and validator are engineering proposals, not a research-proven optimum.

## Sources and claim boundaries

Sources below were inspected in the preceding research conversation. Rows marked
reopened were fetched again during this cross-artifact validation. Access date
for this ledger is 2026-09-08; publication dates are included only where established.
R5, R6, R10, and R13 were additionally reopened in the final validation pass;
their table entries retain the original inspection provenance.

| ID | Source / publisher / date | Finding supported | Confidence and limit | Access |
|---|---|---|---|---|
| R1 | [Codex prompt formula, OpenAI Academy, June 9 2026](https://academy.openai.com/public/clubs/higher-education-05x4z/resources/codex-for-faculty-and-researchers-follow-along-guide-2026-06-09) | Goal, context pointers, constraints, done when | High attribution; vendor advice rather than controlled experiment | Reopened |
| R2 | [Codex-maxxing, OpenAI](https://cdn.openai.com/pdf/8a9f00cf-d379-4e20-b06f-dd7ba5196a11/OAI_WhitePaper_Codex-maxxing26.pdf) | Expected behavior and tests improve the clarity of long-running goals | Vendor practice; no causal effect size for this template | Prior PDF inspection, pages 22–23 |
| R3 | [Prompting best practices, Anthropic](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | Direct instructions, context, examples when useful, model-specific calibration | High attribution; changing guidance does not establish host capability | Reopened |
| R4 | [Demystifying evals, Anthropic, January 9 2026](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Repeated trials and actual environment outcomes, distinct from transcript claims | High; graders still require calibration | Reopened |
| R5 | [Effective context engineering, Anthropic, September 29 2025](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Relevant compact context, structured notes, continuation | Engineering guidance, not a fixed context-length threshold | Prior full-page inspection |
| R6 | [Plan-and-Solve, Wang et al., ACL 2023](https://aclanthology.org/2023.acl-long.147/) | Task decomposition improved the studied reasoning baselines | Controlled GPT-3 experiments; no direct evidence for modern coding hosts | Prior primary abstract inspection |
| R7 | [SELFGOAL, Yang et al., NAACL 2025](https://aclanthology.org/2025.naacl-long.36/) | Dynamic subgoal selection and refinement improved interactive tasks | Peer-reviewed benchmark evidence; not a prompt-only plugin comparison | Reopened |
| R8 | [ReAct, Yao et al., ICLR 2023](https://arxiv.org/abs/2210.03629) | Interleave actions with environment observations and plan updates | Architecture evidence; does not mandate exposing private reasoning | Prior paper inspection |
| R9 | [Reflexion, Shinn et al., 2023](https://arxiv.org/abs/2303.11366) | Feedback and episodic reflection can improve subsequent attempts | Reported HumanEval 91% vs 80% is a benchmark-specific comparison, not a current-model promise | Reopened |
| R10 | [Self-Refine, Madaan et al., NeurIPS 2023](https://proceedings.neurips.cc/paper_files/paper/2023/hash/91edff07232fb1b55a505a9e9f6c0ff3-Abstract-Conference.html) | Iterative feedback improved seven studied tasks | About 20 points average reported there; not guaranteed here | Prior primary abstract inspection |
| R11 | [Lost in the Middle, Liu et al., TACL 2024](https://aclanthology.org/2024.tacl-1.9/) | Relevant-information position affects long-context retrieval | Older model population; motivates testing, not a universal length cap | Prior primary paper inspection |
| R12 | [Codex completion workflow, Reddit](https://www.reddit.com/r/codex/comments/1tymp3c/tip_making_codex_actually_finish_stuff/) | Author reports success with plans, measurable acceptance and evidence | Anecdotal, self-selected, no denominator or controlled comparison | Reopened |
| R13 | [Claude workflow discussion, Reddit](https://www.reddit.com/r/ClaudeAI/comments/1vsfygs/how_has_your_claude_code_workflow_evolved_in_the/) | Users report scoped context and real-app checks reducing drift | Anecdotal; retrieved relative dates were inconsistent, so omit popularity/date inferences | Prior thread inspection |
| R14 | [Codex confidence gate, Reddit](https://www.reddit.com/r/codex/comments/1rajwne/small_agentsmd_trick_that_mass_improved_my_codex/) | Demand for test, review and call-path evidence | Arbitrary 84.7% self-score is unsupported; excluded from design | Prior thread inspection |

## Reconciliation and corrections

The original answer overstated exhaustiveness by treating the research goal as
complete without an exhaustive search protocol. This is a focused evidence review,
not “all proven research.” Reddit establishes reported successful practice, not
independently verified success. Exact scores and comparative effect sizes must
not be used as product efficacy claims.

The earlier tentative Delegate placement was superseded by inspection of the
planning bundle. Goal composition is useful without dispatch; Delegate remains
an optional consumer. A missing Claude native-goal reference does not prove that
no host offers the capability. Both profiles must inspect their current host.

Planning and reflection can help but add cost. Keep them proportional: a simple
goal need not become a project plan or a multi-agent workflow. Long-running
results depend on the model, environment, tools, budgets, and verification—not
just the wording of the objective. This reconciles decomposition studies with
vendor guidance favoring simple systems and model-sensitive instructions.

## Search scope and stopping rule

The prior search covered official OpenAI/Codex goal and prompting documentation,
Anthropic prompting/context/harness/evaluation guidance, primary decomposition
and feedback papers, and original Reddit workflow threads. Automated workflow
reposts and promotional claims were not treated as independent corroboration.
This follow-up reopened ten consequential sources, inspected current repository
interfaces, and audited source-to-design-to-task coverage.

Stop when each material design choice has primary support or is explicitly an
engineering hypothesis, and further searches would repeat the same evidence.
The unresolved question is local feature effectiveness; another literature search
cannot answer it. The planned paired pilot must measure that.

## Traceability

| Evidence | Design choice | Plan tasks |
|---|---|---|
| R1–R3 | Shared outcome/context/boundary/criteria contract | T1, T3 |
| R4 | Separate validity, readiness and execution evidence | T1, T3, T5 |
| R5, R11 | Small references and existing checkpoint handoff | T3, T4 |
| R6–R9 | Adapt plans while preserving original outcome | T3, T5 |
| R10 | Evaluate refinement value rather than force retries | T3, T5 |
| R12–R14 | Evidence-focused UX, no confidence numerology | T3, T5 |
| Engineering choices | Atomic persistence, JSON limits, IDs, release gates | T1, T2, T4, T5 |
