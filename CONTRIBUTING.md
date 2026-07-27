# Contributing to Manifest

> Guidelines for contributing to the Manifest parallel agent orchestration framework

**Last Updated**: 2026-07-02
**Audience**: Contributors

---

## Getting Started

1. Fork the repository and clone your fork
2. Run `./bootstrap.sh` to set up your local environment
3. Run the test suite to verify everything passes:

```bash
# One-time setup: the bats suites need the bats-support/bats-assert submodules
# (clone with `git clone --recurse-submodules`, or run this in an existing clone)
git submodule update --init

# Python tests
pytest tests/python/ -q

# Shell tests
npx bats tests/bats/
```

## Development Workflow

### Making Changes

- Work on a feature branch from `main`
- Keep commits focused and well-described
- Follow the per-language [Coding Standards](docs/CODING_STANDARDS.md). They are
  enforced in four layers: editor (`.editorconfig`), edit-time (an advisory
  PostToolUse hook that lints the file you just edited), commit-time
  (`pre-commit`), and CI (the gate of record runs `pre-commit` on the files you
  changed — so skipping `pre-commit install` locally will not let violations
  through).
- Install the local hooks once: `pip install pre-commit && pre-commit install`
- Run `shellcheck` on any modified shell scripts:

```bash
shellcheck configs/claude/scripts/*.sh bootstrap.sh bootstrap/lib/*.sh
```

- Validate YAML configs after editing:

```bash
yamllint configs/claude/config/*.yml
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))"
```

### Testing

All changes to `configs/claude/scripts/` require corresponding tests in `tests/python/` or `tests/bats/`.
CI runs the full bats + pytest suites on every PR and all of them must pass;
the changed-file pre-commit gate runs the complete hook suite on every file a
PR touches. Do not reduce coverage.

### Skills

New skills go in `.apm/skills/<skill-name>/SKILL.md`. See [.claude/CLAUDE.md](.claude/CLAUDE.md)
for the skill-management architecture and how skills are deployed.

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add new command
fix: correct broken link in docs
refactor: split module into subpackage
docs: update getting started guide
```

## Pull Requests

- Target the `main` branch
- Include a clear description of what changed and why
- Reference related issues with `Closes #N` or `Relates to #N`
- Ensure CI is green before requesting review

## Documentation

When adding features, update the relevant docs in `docs/` and the `Last Updated` date.
Notable changes — new features, breaking changes, deprecations — also add a changelog
entry to `CHANGELOG.md` under `[Unreleased]` in the same PR (the entry moves into a
dated section when it ships). Small fixes, refactors, and docs-only changes don't need one.
See [docs/README.md](docs/README.md) for documentation standards.

---

## Related Documents

- [CLAUDE.md](CLAUDE.md) — Repository context and structure
- [docs/README.md](docs/README.md) — Documentation hub
- [.claude/CLAUDE.md](.claude/CLAUDE.md) — Developer guide for working in this repo
