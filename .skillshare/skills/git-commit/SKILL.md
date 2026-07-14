---
name: git-commit
description: "Run the end-to-end commit pipeline: docs refresh, sync with remote, checks, staging, commit, and push with safe failure handling."
---

# Project Commit Pipeline

Orchestrate a full project commit cycle: regenerate documentation, sync with remote,
run pre-commit checks, stage changes, commit, and push.

## Arguments

- `$ARGUMENTS` — Optional commit message. If not provided, auto-generate one from the staged diff.

---

## Pipeline Phases

Execute these phases **in order**. Each phase must succeed before proceeding to the next.
If a phase fails, attempt to fix the issue up to **2 times** before stopping and
reporting the failure to the user.

---

### Phase 1: Documentation Generation

Generate/update project documentation in this order.
Do **not** invoke slash commands in this pipeline. Execute the equivalent workflows directly.

1. **Generate architecture diagrams**
   - Target: `docs/architecture/ARCHITECTURE_DIAGRAMS.md` (or closest existing architecture diagrams path)
   - Analyze: main entry points, orchestration files, integration clients/services,
     provider/adapter patterns, config files, and project context docs.
   - Update Mermaid diagrams to match current code:
     - Application architecture flowchart
     - Integration sequence flow
     - Component architecture (class/entity or equivalent)
     - Deployment/output flow sequence
     - Add state/decision/data/config diagrams when relevant
   - Use traffic-light classes (`active`, `pending`, `error`, `external`) and keep Mermaid compatible:
     no class assignment on subgraphs, avoid unstable diagram types, avoid syntax-breaking labels.
   - If analyzing 5+ unique imports/modules, run:
     `manifest parallel-agent --json --validate`
     and incorporate findings before finalizing.

2. **Improve documentation**
   - Audit docs using the Diataxis framework.
   - Inventory: `README.md`, `AGENTS.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/**/*.md`.
   - Validate required docs and create/update where needed:
     `README.md`, `AGENTS.md`, `docs/README.md`, `docs/GETTING_STARTED.md`,
     `docs/CONFIGURATION.md`, `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`,
     `CONTRIBUTING.md`, `CHANGELOG.md`.
   - Apply structure/content/format/link checks and fix issues:
     headings, TOC for long docs, "Last Updated", related-doc references,
     code block language tags, broken links, and stale placeholders.
   - Changelog entry check (CONTRIBUTING.md convention): if the staged work is
     notable — a new feature, breaking change, or deprecation — require a
     `CHANGELOG.md` entry under `[Unreleased]` and add one when missing
     before proceeding to commit.
   - Compute/update a documentation health score summary.
   - If total documentation lines > 500, run:
     `manifest parallel-agent --json --validate`
     and incorporate findings before finalizing.

3. **Improve README**
   - Analyze `README.md`, `AGENTS.md`, `CLAUDE.md`, dependency files, and key source/test directories.
   - Ensure README is accurate and includes:
     title/description, key features, quick start, requirements, project structure,
     configuration, usage/workflow, troubleshooting, and testing.
   - Validate all links and code blocks (language-tagged), and align claims with actual codebase behavior.

4. **Regenerate knowledge base docs**

   ```bash
   ~/.claude/scripts/learning_capture.sh sync-docs
   ```

   This regenerates `docs/KNOWLEDGE_BASE.md` from the YAML source of truth
   (`~/.claude/config/knowledge_base.yml`). Non-blocking — skip if the script
   is not available or fails.

After all four complete, run `git status` to confirm documentation files were modified.

---

### Phase 2: Pull Latest & Resolve Conflicts

1. **Fetch and pull latest from the current branch's upstream**:

   ```bash
   git fetch origin
   git pull --rebase origin $(git branch --show-current)
   ```

2. **If rebase conflicts occur**:
   - Run `git diff --name-only --diff-filter=U` to list conflicted files
   - For each conflicted file:
     a. Read the file to understand the conflict markers
     b. Resolve the conflict by keeping both changes where possible, preferring the
        incoming (remote) change for non-functional conflicts (formatting, docs)
        and the local change for functional code
     c. Stage the resolved file with `git add <file>`
   - Continue the rebase: `git rebase --continue`
   - If conflicts cannot be auto-resolved, **stop and ask the user** for guidance using AskUserQuestion

3. **If pull fails for other reasons** (e.g., no upstream):
   - Try `git pull --rebase origin main` as fallback
   - If that also fails, report the error and continue (user may be on a new branch)

---

### Phase 3: Pre-commit Checks

1. **Stage all modified and new files** for pre-commit to analyze:

   ```bash
   git add -A
   ```

2. **Run pre-commit hooks**:

   ```bash
   pre-commit run --all-files
   ```

3. **If pre-commit fails**:
   - Parse the output to identify which hooks failed and which files are affected
   - **For each failure**, attempt a fix:
     - **gitleaks** (secrets detected): **STOP immediately**. Do NOT commit.
       Report the finding to the user with the file and line number.
       Ask the user how to proceed.
     - **bandit** (Python security): Read the flagged file, understand the
       finding, and fix the security issue if it's a true positive.
       If it's a false positive, add a `# nosec` comment with justification.
     - **test-go / test-python / test-ts** (test failures): Read the test
       output, identify the failing test, read the relevant source code, and
       fix the issue. If the failure is pre-existing (check MEMORY.md for
       known failures), note it and continue.
     - **Formatting/linting**: Run the appropriate formatter (`ruff format`, `gofmt`, `prettier`) and re-stage.
   - After fixes, **re-stage and re-run** pre-commit:

     ```bash
     git add -A
     pre-commit run --all-files
     ```

   - Allow up to **2 retry cycles**. If pre-commit still fails after 2 retries,
     stop and report the remaining failures to the user.

---

### Phase 4: Stage & Commit

1. **Stage all changes** (including any fixes from Phase 3):

   ```bash
   git add -A
   ```

2. **Verify there are changes to commit**:

   ```bash
   git status --porcelain
   ```

   - If empty, inform the user "Nothing to commit — working tree clean" and skip to end.

3. **Generate or use commit message**:
   - If `$ARGUMENTS` was provided, use it as the commit message
   - If not provided:
     a. Run `git diff --cached --stat` and `git diff --cached` to analyze staged changes
     b. Run `git log --oneline -5` to match the repository's commit message style
     c. Generate a concise commit message that summarizes the changes (1-2 sentences focusing on "why")
     d. Present the message to the user via AskUserQuestion for approval before committing

4. **Auto-detect issue references and append "Fixes #" keywords**:
   - Scan the commit message for issue number references (#123, issue #123, etc.)
   - Check git branch name for issue numbers (e.g., `fix/issue-296-backtest`)
   - Search staged files for comments mentioning issues (e.g., "// Fix for #288", "# Resolves issue #296")
   - For each detected issue number, verify it's open using
     `~/.claude/scripts/git_ops.sh issue-view <number> --json state --jq '.state'`
   - If open issues are found, append to the commit message:

     ```text

     Fixes #296
     Fixes #288
     ```

   - If multiple issues are detected, ask the user to confirm which ones should be closed by this commit
   - If no issue references are found, skip this step

5. **Create the commit**:

   ```bash
   git commit -m "$(cat <<'EOF'
   <commit message here>
   EOF
   )"
   ```

6. **Verify the commit succeeded**:

   ```bash
   git log --oneline -1
   ```

---

### Phase 5: Push

1. **Push to remote**:

   ```bash
   git push origin $(git branch --show-current)
   ```

2. **If push fails**:
   - If rejected (non-fast-forward): pull with rebase and retry push once

     ```bash
     git pull --rebase origin $(git branch --show-current) && git push origin $(git branch --show-current)
     ```

   - If no upstream: push with `-u` flag

     ```bash
     git push -u origin $(git branch --show-current)
     ```

   - If push still fails, report the error to the user

3. **Confirm success**: Show the user the final `git log --oneline -1` and the remote URL.

---

## Error Recovery

- **Network errors**: Retry once after 5 seconds
- **Authentication errors**: Stop and inform the user to check their git credentials
- **Merge conflicts that can't be auto-resolved**: Stop and present the conflicts to the user
- **Secrets detected by gitleaks**: NEVER commit. Always stop and report.

## Summary Output

After the pipeline completes (or stops), provide a summary:

```text
## Project Commit Summary

| Phase | Status |
|-------|--------|
| Documentation Generation | pass/fail/skipped |
| Pull & Rebase | pass/fail/skipped |
| Pre-commit Checks | pass/fail (N retries) |
| Commit | pass/fail/nothing-to-commit |
| Push | pass/fail |

**Commit**: <hash> <message>
**Branch**: <branch-name>
**Files changed**: <count>
```

---

## Learning Capture (Optional)

After the pipeline completes, if pre-commit checks failed and were fixed during Phase 3,
capture the failure patterns for the knowledge base:

1. For each pre-commit hook that failed:
   - Record the hook name, failure reason, and fix applied
   - Run:

     ```bash
     ~/.claude/scripts/learning_capture.sh add \
       --category antipattern --language <detected> \
       --title "Pre-commit: <hook> failure" \
       --description "<what failed and how it was fixed>" \
       --source git-commit --confidence medium
     ```

2. This step is **non-blocking** -- failures in learning capture should not affect the commit pipeline.
