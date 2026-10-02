# manifest-security eval plan

One case directory per input, prefixed by skill. Every case: `model: sonnet`, `runs: 3`,
`allowed_tools: [Skill, Read, Glob, Grep]` (all inputs inline — no files created, so no Write/Bash).
Judge: `--judge-model opus` (≠ agent model). Fire cases carry a display-only `tool_used: Skill`
trigger check; neg cases carry `tool_used` min 0 / max 0 / `arm: both` plus outcome graders.

Run: `claude plugin eval . --ablation with-without --judge-model opus` (headline = Δ).

## 1. security-review-diff (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| srd-01-ssrf-preview | new endpoint, SSRF | regex SSRF · llm source→sink + fix, no nits |
| srd-02-robustness-noise-only | robustness-only diff | regex "no findings" (0.5) · llm rejects throttle / fail-closed / trusted-config each |
| srd-03-fail-open-auth | except swallows auth | regex fail-open/bypass · llm mechanism + fail-closed fix |
| srd-04-sibling-gate-omission | bulk path skips gate | regex IDOR/authz · llm sibling omission + impact + fix |
| srd-05-secret-logging | "safe to merge?" | regex key-in-logs · llm not-safe, 5xx not flagged |
| srd-06-neg-performance-review (neg) | perf review | regex N+1 · llm stays on perf · not_fired |

## 2. security-triage-findings (240 s / 8 turns)
| case | refutation gate exercised | graders |
|---|---|---|
| stf-01-self-victim-cli | attacker-only victim | regex idx1 survives (0.5) · llm per-idx |
| stf-02-preexisting-context | PRE-EXISTING | llm per-idx · regex pre-existing (0.5) |
| stf-03-comment-claims-delegated | comment ≠ traced call path | llm idx0 survives |
| stf-04-ssrf-from-env | SSRF exempt from no-privilege | llm idx0 survives |
| stf-05-offdiff-no-enabling-line | off_diff stricter bar | llm per-idx |
| stf-06-neg-no-candidates (neg) | plain review, no candidate list | regex traversal · llm direct review · not_fired |

## 3. security-refute-findings — deprecated alias (240 s / 8 turns)
| case | gate | graders |
|---|---|---|
| srf-01-frontend-gate-backend-enforced | frontend-only gate | llm refuted · regex backend (0.5) |
| srf-02-throwaway-dev-script | throwaway dev dir | llm idx0/1 refuted, idx2 survives · regex SSTI |
| srf-03-hardcoded-url-sink | non-dangerous sink | llm refuted · regex hardcoded (0.5) |
| srf-04-data-exposure-not-refuted | data-exposure exemption | llm survives |
| srf-05-neg-refute-argument (neg) | "refute" non-security | regex PEP8/spaces · llm · not_fired |

## 4. code-audit (240 s / 8 turns)
| case | trigger | graders |
|---|---|---|
| ca-01-explicit-review-secrets-pickle | explicit request | regex pickle · regex hardcoded key · llm severity+location |
| ca-02-jwt-verify-disabled | auth boundary change | regex signature · llm not-ok + fix |
| ca-03-yaml-shell-injection | explicit request | regex yaml · regex shell · llm both critical |
| ca-04-password-hash-change | crypto change | regex md5 · llm regression + bcrypt/argon2 |
| ca-05-neg-cache-hash-refactor (neg) | nonsecurity_cache_hash non-trigger | regex keeps sha1 · llm · not_contains audit header · not_fired |

## 5. ci-audit-triggers (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| cat-01-prt-pwn-request | pull_request_target + head checkout | regex pwn-request · llm path + structural fix |
| cat-02-comment-expression-injection | `${{ comment.body }}` in run | regex injection · llm env-bind fix + gate |
| cat-03-author-association-gap | commenter≠author, not write check | llm gaps · regex permission check (0.5) |
| cat-04-safe-workflow-no-overreport | clean workflow | llm no high findings |
| cat-05-gitlab-mr-title-injection | GitLab vocabulary | llm GitLab concepts · regex eval |
| cat-06-neg-write-new-ci (neg) | build request | regex yaml+pytest · llm · not_fired |

## 6. ci-harden-workflow (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| chw-01-build-comment-agent | build from scratch | regex author_association · llm 5 controls |
| chw-02-protect-control-file | governance Q | regex CODEOWNERS · llm branch protection + sole-maintainer |
| chw-03-harden-deploy-workflow-run | harden pasted YAML | llm 4 controls · regex environment: |
| chw-04-gate-test-default-branch | debugging Q | regex default branch · llm |
| chw-05-neg-matrix-explain (neg) | generic Actions Q | regex matrix example · llm · not_contains CODEOWNERS · not_fired |

## 7. docker-audit-firewall (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| daf-01-input-chain-wrong | INPUT chain on published port | regex DOCKER-USER · llm |
| daf-02-traefik-auth-replaced | compose diff drops auth | llm regression · regex auth-loss |
| daf-03-fail-open-install | `2>/dev/null` | llm fail-open, no false wrong-chain claim · regex |
| daf-04-write-rules-postgres | write rules | regex DOCKER-USER · llm order + don't-publish |
| daf-05-neg-host-ssh (neg) | no Docker | regex INPUT · llm no DOCKER-USER derail · not_fired |

## 8. llm-audit-traversal (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| lat-01-regex-name-mkdir | regex capture → Path join | regex escape · llm 5 claims |
| lat-02-json-filename-osjoin | JSON field → os.path.join | regex · llm |
| lat-03-allowlist-without-containment | half-fixed | regex containment · llm keep-both, no false exploit |
| lat-04-both-guards-clean | fully fixed | llm clean · regex not_contains high (0.5) |
| lat-05-neg-missing-parent-dir (neg) | FileNotFoundError | regex parents=True · llm · not_fired |

## 9. mcp-audit (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| mca-01-bind-noauth-rw | all four holes | regex 0.0.0.0 · llm 4 checks |
| mca-02-error-leak-focus | error leakage only | llm · regex request id |
| mca-03-test-bypasses-factory | test honesty | llm · regex mode=ro |
| mca-04-well-configured | clean server | llm no high |
| mca-05-neg-add-tool (neg) | how-to | regex decorator · llm · not_fired |

## 10. security-harden-proxy (240 s / 8 turns)
| case | shape | graders |
|---|---|---|
| shp-01-build-github-proxy | build (600 s / 15 turns) | regex generic 502 (0.5) · llm observable token exposure |
| shp-02-review-leaky-proxy | review | regex key leak · llm |
| shp-03-leak-test | write test | regex `not in` · llm |
| shp-04-unbounded-buffer | review | regex stream/cap · llm |
| shp-05-neg-public-api (neg) | keyless API | regex open-meteo · llm no scaffolding · not_fired |

## Side-channels
Recorded per run by the runner: cost, latency, tool-count. Ceilings: 240 s / 8 turns
(fire; shp-01 600 s / 15), 120–180 s / 4–6 turns (neg). Pilot actuals: 53 cases × 2 arms in
3750 s, $8.91 total (~$0.08/run; shp-01 ~$0.50/run), typically 1–4 turns per run.
After calibration (larger budgets on shp-01/shp-03/chw-01): ~$11.3 agent cost per 1-run suite
(+ Opus judge) → full `runs: 3` suite ≈ $35–40.

## Full suite (runs: 3, Opus judge, 2026-09-26) — $34.19
| skill | with | without | Δ | cases below 1.00 with-plugin |
|---|---|---|---|---|
| mcp-audit | 1.00 | 0.63 | +0.37 | — |
| ci-audit-triggers | 1.00 | 0.65 | +0.35 | — |
| security-harden-proxy | 1.00 | 0.76 | +0.24 | — |
| llm-audit-traversal | 1.00 | 0.77 | +0.23 | — |
| security-review-diff | 1.00 | 0.81 | +0.19 | — |
| ci-harden-workflow | 0.87 | 0.70 | +0.17 | chw-01 0.67 (unpinned npx), chw-02 0.83, chw-03 0.83 |
| security-triage-findings | 0.98 | 0.83 | +0.15 | stf-01 0.89 |
| docker-audit-firewall | 0.80 | 0.67 | +0.13 | daf-01 0.50, daf-02 0.83, daf-04 0.67 (rule-order bug) |
| security-refute-findings | 1.00 | 0.93 | +0.07 | — |
| code-audit | 0.88 | 0.87 | +0.01 | ca-01 0.89, ca-02 0.67, ca-05 0.83 |
| **overall (53 cases)** | **0.95** | **0.76** | **+0.19** | |

## Re-measure after follow-up fixes (runs: 3, Opus judge, 2026-09-30) — $20.41
Split by `--case '<prefix>-*'`; no session-limit errors. Skill fixes: daf step-2 rule order, shp
exception framing, code-audit / ci-harden-workflow triggers, pasted-input fallbacks, srd
description. Graders unchanged.
| skill | with | without | Δ | cases below 1.00 with-plugin |
|---|---|---|---|---|
| docker-audit-firewall | 1.00 | 0.74 | +0.26 | — (daf-01/daf-04 now 3/3) |
| ci-harden-workflow | 0.93 | 0.73 | +0.20 | chw-01 0.67 (`hardened` judge FAIL 2/3) |
| security-triage-findings | 0.96 | 0.76 | +0.20 | stf-02 0.78 (`verdicts` FAIL 1/3) |
| ci-audit-triggers | 1.00 | 0.82 | +0.18 | — |
| security-harden-proxy | 1.00 | 0.90 | +0.10 | — |
| mcp-audit | 1.00 | 0.93 | +0.07 | — |
| security-review-diff | 1.00 | 0.94 | +0.06 | — |
| llm-audit-traversal | 1.00 | 0.97 | +0.03 | — |
| code-audit | 0.96 | 0.96 | +0.00 | ca-01 0.78 (1 regex + 1 judge miss); ca-02/ca-04 now 1.00 |
| security-refute-findings | 1.00 | 1.00 | +0.00 | — |
| **overall (53 cases)** | **0.99** | **0.87** | **+0.11** | |

With-plugin rose 0.95 → 0.99; Δ fell +0.19 → +0.11 because the **without** arm rose 0.76 → 0.87
(the plugin plays no part in that arm, so it is run-to-run/base-model variance; this run: claude 2.1.285).
Compare with-arm scores across runs, not Δ alone. Fire status per run is unverified: traces live in
deleted temp dirs, so ca-02/ca-04/chw-04 gains are outcome-graded only.

## Partial re-measure after review-gate fixes (2026-10-01) — $6.80
daf/cat/chw only, after docker-audit-firewall precondition checks (backend, trusted_host_interfaces, IPv6 by bridge
mode) and pasted-YAML-first Step 0. docker-audit-firewall 0.97 / 0.83 (daf-02 0.83); ci-audit-triggers 1.00 / 0.79;
ci-harden-workflow 0.90 / 0.73 (chw-01 0.50: `hardened` judge FAIL 3/3, same case as before). skill-did-not-fire 9/9.

## Design decision: inline inputs (known skill-procedure conflicts)
Cases paste code/diffs/YAML inline — the most common real input shape — with read-only tools.
Several skills' procedures assume a repo or extra tools, so the with-arm must deviate. This is
NOT treated as acceptable skill behavior; each is a plugin defect filed as a follow-up. The suite
measures whether the skill still delivers the right answer on pasted input (pilot: it does).
- **ci-audit-triggers / ci-harden-workflow Step 0** mandate `ci_platform.sh` and *stop* on `none`.
  Defect: Step 0 should fall back to pasted workflow content.
- **security-triage-findings / security-refute-findings** mandate one sub-agent per finding at ≥3
  candidates (srf-02). Defect: no inline fallback when native dispatch is unavailable.
- **code-audit** escalates to independent review on auth/crypto changes (ca-02, ca-04) and queries
  `manifest-workspace:learning-capture` (another bundle). Defect: escalation has no degraded path.
- **security-review-diff step 1** requires reading every changed file in full; srd-* give partial
  diffs only. Defect: no guidance for diff-only input.

## Plugin follow-ups surfaced by the pilot
- **docker-audit-firewall SKILL.md step 2** example inserts `-I … RETURN` then `-I … DROP`, which
  leaves DROP above RETURN (blocks everything) — contradicting its own ordering rule. daf-01 and
  daf-04 answers reproduce this bug in all 3 runs of BOTH arms (the base model makes the same
  mistake, so the skill's buggy example reinforces rather than corrects it); the grader correctly
  fails them. The 1-run pilot passed daf-01 only because that judge missed the ordering.
- **security-harden-proxy step 2** claims urllib exceptions carry the Authorization header in their
  traceback; they don't (HTTPError holds URL/status/response headers). shp graders now grade
  observable exposure (response body, logs, echoed exception/URL) instead.
- **Trigger gaps**: code-audit did not fire on implicit "ok to ship?/thoughts?" prompts (ca-02,
  ca-04); ci-harden-workflow did not fire on a gate-debugging question (chw-04).
- **security-review-diff description** points to deprecated `security-refute-findings`.
- Stray untracked `CLAUDE.md` (context-mode routing) in this and sibling plugin dirs.

## Things I'm unsure about
- **security-refute-findings** is a deprecated alias; cases name it explicitly or say "refute". If
  the model routes to `security-triage-findings` instead, outcome graders still pass (intended).
- **srd-02 / cat-04 / mca-04 / lat-04** are "correct answer is no/low findings" cases — the regex
  secondaries are brittle; the llm grader is primary.
- **stf-05 idx 0** (unvalidated timezone) — rubric accepts refute OR survive-with-named-sink.
- **shp-05 neg** — shp's description is narrow, so the without-arm and with-arm likely tie (Δ≈0) — expected.
