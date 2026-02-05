# Pre-commit Hooks

> Automated code quality checks before each commit

**Last Updated**: 2026-02-05

---

## Overview

This project uses [pre-commit](https://pre-commit.com/) to run automated checks
before commits. Hooks validate code quality, security, and formatting.

## Installation

Pre-commit is automatically installed and configured by `/project-commit` command.

To install manually:

```bash
# Install pre-commit (if not already installed)
pip3 install pre-commit --user

# Install git hooks
~/Library/Python/3.9/bin/pre-commit install
```

## Configured Hooks

### Standard Checks

- **trailing-whitespace**: Remove trailing whitespace
- **end-of-file-fixer**: Ensure files end with newline
- **check-yaml**: Validate YAML syntax
- **check-json**: Validate JSON syntax
- **check-added-large-files**: Prevent large files (>500KB)
- **detect-private-key**: Detect private keys
- **mixed-line-ending**: Normalize line endings (LF)

### Shell Scripts

- **shellcheck**: Static analysis for shell scripts
- **shfmt**: Shell script formatting (4-space indent)

### Markdown

- **markdownlint**: Markdown linting and formatting

### YAML

- **yamllint**: YAML linting (120 char line limit)

### Security

- **gitleaks**: Detect hardcoded secrets and API keys

### Custom Checks

- **validate-parallel-agent**: Bash syntax check for parallel_agent.sh
- **validate-bootstrap**: Bash syntax check for bootstrap.sh
- **check-credentials**: Search for hardcoded API keys
- **validate-yaml-configs**: Validate .claude/config/*.yml files
- **check-command-frontmatter**: Ensure command files have frontmatter

## Running Manually

```bash
# Run all hooks on all files
~/Library/Python/3.9/bin/pre-commit run --all-files

# Run specific hook
~/Library/Python/3.9/bin/pre-commit run shellcheck --all-files

# Run on specific files
~/Library/Python/3.9/bin/pre-commit run --files bootstrap.sh .claude/scripts/parallel_agent.sh
```

## Bypassing Hooks (Not Recommended)

```bash
# Only bypass when absolutely necessary
git commit --no-verify -m "Emergency fix"
```

**Warning**: Bypassing hooks can introduce security vulnerabilities or broken code.

## Configuration Files

| File | Purpose |
|------|---------|
| `.pre-commit-config.yaml` | Main pre-commit configuration |
| `.markdownlintrc` | Markdown linting rules |
| `.gitleaks.toml` | Secret detection configuration |

## Troubleshooting

### Hook Fails on First Run

Pre-commit downloads and caches tools on first run. This is normal and takes 2-5 minutes.

### Shellcheck Errors

Fix the reported issues or add `# shellcheck disable=SCXXXX` comment if false positive.

### Markdown Linting

Markdownlint will auto-fix many issues. For persistent errors, see `.markdownlintrc` configuration.

### Gitleaks False Positives

Add patterns to `.gitleaks.toml` allowlist or use `# gitleaks:allow` comment.

## Related

- [Pre-commit Documentation](https://pre-commit.com/)
- [Shellcheck Wiki](https://github.com/koalaman/shellcheck/wiki)
- [Markdownlint Rules](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md)
- [Gitleaks Documentation](https://github.com/gitleaks/gitleaks)
