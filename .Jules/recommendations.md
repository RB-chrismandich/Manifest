# Manifest Improvement Recommendations
**Generated**: 2026-02-04
**Based on**: .Jules learnings + cookedbooks/.claude patterns

---

## Executive Summary

Based on the learnings captured in `.Jules/` and patterns from the `cookedbooks/.claude` directory, we should make several updates to Manifest to improve:
1. **Security** - Fix command injection vulnerabilities
2. **Performance** - Eliminate unnecessary process forking
3. **User Experience** - Better error messages and diagnostics
4. **Architecture** - Add foundational patterns for complex workflows

---

## Priority 1: Security Fixes (CRITICAL)

### 1.1 Command Injection in parallel_agent.sh

**Issue**: `.Jules/sentinel.md` identifies command injection via `GEMINI_INCLUDE_DIRS` and model names passed to `bash -c`.

**Files to audit**:
- `.claude/scripts/parallel_agent.sh`
- `bootstrap.sh`

**Fix pattern**:
```bash
# BAD
bash -c "command $VAR"

# GOOD
bash -c 'command "$1"' -- "$VAR"
```

**Action**: Search for all `bash -c` calls and apply the safe pattern.

### 1.2 Temporary File Security

**Issue**: `.Jules/sentinel.md` warns about predictable temp file names allowing symlink attacks.

**Files to audit**:
- `.claude/scripts/parallel_agent.sh`
- `bootstrap.sh`

**Fix pattern**:
```bash
# BAD
tmp=/tmp/file_$$.txt

# GOOD
tmp=$(mktemp)
```

**Action**: Replace all `$$` temp file patterns with `mktemp`.

### 1.3 Shell Profile Injection

**Issue**: `.Jules/sentinel.md` warns about API key input being written to shell profiles with insufficient escaping.

**Files to audit**:
- `bootstrap.sh` (anywhere writing to `.bashrc`, `.zshrc`)

**Fix pattern**:
```bash
# BAD
echo "export API_KEY=\"$user_input\"" >> ~/.zshrc

# GOOD
# Use single quotes and escape single quotes in data
safe_input="${user_input//\'/\'\\\'\'}"
echo "export API_KEY='$safe_input'" >> ~/.zshrc
```

**Action**: Audit all shell profile writes for proper escaping.

---

## Priority 2: Performance Optimizations

### 2.1 YAML Parsing Bottleneck

**Issue**: `.Jules/bolt.md` shows O(N*M) parsing using multiple `sed`/`grep` passes.

**Current**: `parallel_agent.sh` parses `services.yml` with ~12 process spawns
**Target**: Single-pass `awk` parsing → 1 process spawn

**Implementation**:
```bash
# Instead of multiple grep/sed calls:
eval "$(awk '
  /^  claude:/{in_claude=1}
  in_claude && /enabled:/{print "CLAUDE_ENABLED="$2; in_claude=0}
  /^  gemini:/{in_gemini=1}
  in_gemini && /enabled:/{print "GEMINI_ENABLED="$2; in_gemini=0}
  /^minimum_agents:/{print "MIN_AGENTS="$2}
' ~/.claude/config/services.yml)"
```

**Files**: `.claude/scripts/parallel_agent.sh`, `.claude/scripts/check_status.sh`

### 2.2 Eliminate Process Forking in Loops

**Issue**: `.Jules/bolt.md` warns about `command -v` and `seq` in loops/functions.

**Patterns to fix**:
- Move `command -v` checks to startup, cache results
- Replace `for i in $(seq 1 10)` with `for ((i=1; i<=10; i++))`
- Cache `json_escape` dependency checks

**Files**: `.claude/scripts/parallel_agent.sh`

### 2.3 Busy Loop Optimization

**Issue**: `.Jules/bolt.md` identifies 30 forks/second from `ps` polling loop.

**Current**: Using `ps` to check process state every 100ms
**Target**: Use `/proc/[pid]/stat` on Linux (native bash), fallback to `ps` on macOS

**Files**: `.claude/scripts/parallel_agent.sh` (if it has a polling loop)

### 2.4 Redundant Validation Logic

**Issue**: `.Jules/bolt.md` warns about running validation twice (summary + JSON output).

**Fix**: Cache validation results in global variables, reuse.

**Files**: `.claude/scripts/parallel_agent.sh`

---

## Priority 3: User Experience Improvements

### 3.1 Shell Aliases for Ergonomics ✅ DONE

**Issue**: `.Jules/palette.md` suggests offering aliases for long paths.

**Status**: Already partially implemented in `bootstrap.sh`, but could be enhanced.

**Enhancement**: Detect user's shell and auto-offer alias at end of installation.

### 3.2 Progress Visualization ✅ DONE

**Issue**: `.Jules/palette.md` suggests ASCII/Unicode progress bars.

**Status**: Already implemented in `parallel_agent.sh` with `draw_bar()` function.

### 3.3 Duration Feedback ✅ DONE

**Issue**: `.Jules/palette.md` suggests execution timers.

**Status**: Already implemented in `parallel_agent.sh` with `format_duration()`.

### 3.4 Liveness Indicators for Long Operations ✅ DONE

**Issue**: `.Jules/palette.md` suggests elapsed time counters for spinners.

**Status**: Already implemented with `Waiting for agents (MM:SS)` display.

### 3.5 Cursor Restoration on Exit ⚠️ NEEDS CHECK

**Issue**: `.Jules/palette.md` warns about failing to restore cursor on Ctrl+C.

**Fix pattern**:
```bash
trap 'tput cnorm' EXIT
tput civis  # hide cursor
# ... do work ...
# cursor auto-restored by trap
```

**Action**: Audit `parallel_agent.sh` for cursor hiding and add trap.

### 3.6 Improved Error Messages ✅ DONE (Today)

**Status**: Already implemented in this session with better guidance on no agents available.

---

## Priority 4: Foundational Patterns from cookedbooks/.claude

These are advanced patterns that could make Manifest more powerful for complex projects.

### 4.1 Headless Orchestration Prompt

**Pattern**: `cookedbooks/.claude/headless_prompt.md`

**What it is**: A top-level orchestration prompt that delegates to sub-agents based on project architecture.

**Value for Manifest**:
- Manifest is about orchestrating parallel agents
- Could offer a template for users to create their own orchestration prompts
- Demonstrates how to structure multi-agent workflows

**Recommendation**:
- Add `templates/orchestration_prompt.md` as an example
- Document in `docs/ADVANCED_USAGE.md`

### 4.2 Project-Specific Validation Overrides

**Pattern**: `cookedbooks/.claude/config/validation_overrides.yml`

**What it is**: Project-specific validation rules that extend the base criteria.

**Value for Manifest**:
- Users could define domain-specific security checks
- Example: Django projects check for CSRF middleware, Go projects check for SQL injection patterns

**Recommendation**:
- Update `~/.claude/config/validation_criteria.yml` docs to explain override mechanism
- Add example overrides for common frameworks (Django, Rails, Express, etc.)
- Document in `docs/CONFIGURATION.md`

### 4.3 Auto-Trigger Skills for Domain Patterns

**Pattern**: `cookedbooks/.claude/skills/event-flow-guard/SKILL.md`

**What it is**: A skill that auto-triggers when detecting specific code patterns (RabbitMQ changes).

**Value for Manifest**:
- Manifest already has `code-quality` skill
- Could add more domain-specific skills as templates:
  - `api-security-guard` - triggers on API endpoint changes
  - `database-migration-guard` - triggers on schema changes
  - `secret-detection-guard` - triggers on credential-like strings

**Recommendation**:
- Add `templates/skills/` directory with example auto-trigger skills
- Document trigger pattern design in `docs/SKILLS.md`

### 4.4 Multi-Phase Commands (project-commit pattern)

**Pattern**: `cookedbooks/.claude/commands/project-commit.md`

**What it is**: A command that orchestrates multiple phases (docs → pull → pre-commit → commit → push).

**Value for Manifest**:
- Demonstrates how to build robust, error-recovering workflows
- Could be adapted for other multi-step processes

**Recommendation**:
- Add as example: `.claude/commands/examples/full-commit-pipeline.md`
- Document command error recovery patterns in `docs/COMMANDS.md`

### 4.5 Issue Management Commands

**Pattern**: `cookedbooks/.claude/commands/issue-*.md` (triage, prioritize, process, review, plan)

**What it is**: Commands for managing GitHub issues programmatically.

**Value for Manifest**:
- Could be useful for projects using Claude to manage backlogs
- Not foundational, but useful for some users

**Recommendation**:
- Add as optional templates in `templates/github-workflow/`
- Not part of core Manifest, but available for users to copy if needed

---

## Implementation Plan

### Phase 1: Security (Week 1) - BLOCKING

- [ ] Audit and fix command injection in `parallel_agent.sh`
- [ ] Audit and fix command injection in `bootstrap.sh`
- [ ] Replace all `$$` temp files with `mktemp`
- [ ] Fix shell profile injection in `bootstrap.sh`
- [ ] Add security audit to `.Jules/sentinel.md` learnings
- [ ] Update `MEMORY.md` with security patterns to avoid

**Exit criteria**: All CRITICAL security issues from `.Jules/sentinel.md` fixed.

### Phase 2: Performance (Week 2) - HIGH PRIORITY

- [ ] Replace YAML parsing with single-pass `awk`
- [ ] Cache `command -v` checks at startup
- [ ] Replace `seq` with native bash loops
- [ ] Eliminate redundant validation calls
- [ ] Optimize polling loop (if exists) with `/proc` parsing
- [ ] Add performance benchmarks to `tests/`
- [ ] Update `MEMORY.md` with performance patterns

**Exit criteria**: `parallel_agent.sh` startup time < 500ms, polling overhead < 1% CPU.

### Phase 3: UX Polish (Week 3) - MEDIUM PRIORITY

- [ ] Add cursor restoration trap to `parallel_agent.sh`
- [ ] Enhance shell alias suggestions in `bootstrap.sh`
- [ ] Add `--verbose` flag to `check_status.sh` for debugging
- [ ] Improve error recovery messaging
- [ ] Add "Quick Start in 60 seconds" to README
- [ ] Update troubleshooting guide with new diagnostics

**Exit criteria**: New users can diagnose issues without reading docs.

### Phase 4: Advanced Patterns (Week 4+) - NICE TO HAVE

- [ ] Create `templates/orchestration_prompt.md`
- [ ] Create `templates/skills/` with example auto-trigger skills
- [ ] Create `templates/github-workflow/` with issue management commands
- [ ] Add `docs/ADVANCED_USAGE.md` with orchestration examples
- [ ] Add framework-specific validation override examples
- [ ] Document command error recovery patterns

**Exit criteria**: Advanced users can customize Manifest for complex workflows.

---

## Metrics

Track these before/after each phase:

| Metric | Current | Target |
|--------|---------|--------|
| Security issues (critical) | ? | 0 |
| Startup time (parallel_agent.sh) | ? | < 500ms |
| YAML parse overhead | ~12 forks | 1 fork |
| Polling loop overhead | ~30 forks/sec | < 1 fork/sec |
| New user time-to-first-success | ? | < 5 min |
| GitHub issues (Manifest) | ? | Tracked |

---

## References

- `.Jules/bolt.md` - Performance learnings
- `.Jules/sentinel.md` - Security learnings
- `.Jules/palette.md` - UX learnings
- `cookedbooks/.claude/headless_prompt.md` - Orchestration pattern
- `cookedbooks/.claude/config/validation_overrides.yml` - Project-specific validation
- `cookedbooks/.claude/skills/event-flow-guard/SKILL.md` - Auto-trigger skill pattern
- `cookedbooks/.claude/commands/project-commit.md` - Multi-phase command pattern
