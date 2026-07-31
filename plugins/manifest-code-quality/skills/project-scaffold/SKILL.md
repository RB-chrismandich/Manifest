---
name: project-scaffold
description: Initialize new projects with language-specific quality gates, linting configs, test frameworks, CI/CD templates, and Manifest integration.
---

# Project Scaffold Skill

Initialize a new project directory with language-appropriate tooling, quality gates,
and Manifest agent integration out of the box.

## Arguments

- `$ARGUMENTS` — Expected format: `[language] [project-name]`
  - **language**: One of `python`, `go`, `node`, `terraform`. If omitted, detect from existing files.
  - **project-name**: Name for the project (used in module paths, package names, etc.).
    If omitted, use the current directory name.

---

## Phase 1: Language Detection

If a language argument is provided, use it directly. Otherwise, detect the language
by scanning the current directory for indicator files:

| Language | Indicator Files |
|----------|----------------|
| Python | `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `*.py` |
| Go | `go.mod`, `go.sum`, `*.go` |
| Node | `package.json`, `tsconfig.json`, `*.ts`, `*.js` |
| Terraform | `*.tf`, `*.tfvars`, `terraform.tfstate` |

**Priority**: If multiple languages are detected, ask the user to specify which one.
If no language is detected and none was provided, stop and report:

```text
Error: Could not detect project language. Please specify: /project-scaffold python my-project
```

---

## Phase 2: Project Name Resolution

Resolve the project name in this order:

1. Use the `project-name` argument if provided
2. Use the current directory basename
3. Sanitize the name: lowercase, replace spaces/special chars with hyphens, strip leading digits

The sanitized name is used as:

- Python: package name (underscores for module, hyphens for distribution)
- Go: module path suffix (e.g., `github.com/user/{project-name}`)
- Node: package name in `package.json`
- Terraform: not used in templates (infrastructure is unnamed)

---

## Phase 3: Template Copying

Copy boilerplate files from the appropriate template directory. The templates live at:

```text
<this skill's own directory>          (illustrative; never hard-code the path)
templates/scaffold/{language}/  (in the Manifest repo)
```

For each language, copy and process the following files:

### Python

| Template | Destination | Processing |
|----------|-------------|------------|
| `templates/scaffold/python/pyproject.toml` | `pyproject.toml` | Replace `__PROJECT_NAME__` with project name |
| `templates/scaffold/python/.pre-commit-config.yaml` | `.pre-commit-config.yaml` | Copy as-is |

Create these additional files if they do not exist:

- `src/{package_name}/__init__.py` — Empty init file
- `src/{package_name}/py.typed` — PEP 561 marker (empty file)
- `tests/__init__.py` — Empty init file
- `tests/test_placeholder.py` — Minimal pytest placeholder

### Go

| Template | Destination | Processing |
|----------|-------------|------------|
| `templates/scaffold/go/go.mod.tmpl` | `go.mod` | Replace `__MODULE_PATH__` with module path |
| `templates/scaffold/go/Makefile` | `Makefile` | Copy as-is |
| `templates/scaffold/go/.golangci.yml` | `.golangci.yml` | Copy as-is |

Create these additional files if they do not exist:

- `cmd/{project-name}/main.go` — Minimal main package
- `internal/.gitkeep` — Placeholder for internal packages
- `main_test.go` — Minimal test placeholder

### Node

| Template | Destination | Processing |
|----------|-------------|------------|
| `templates/scaffold/node/package.json.tmpl` | `package.json` | Replace `__PROJECT_NAME__` with project name |
| `templates/scaffold/node/tsconfig.json` | `tsconfig.json` | Copy as-is |
| `templates/scaffold/node/eslint.config.js` | `eslint.config.js` | Copy as-is |

Create these additional files if they do not exist:

- `src/index.ts` — Minimal entry point
- `tests/index.test.ts` — Minimal vitest placeholder
- `.prettierrc` — Default Prettier config (`{ "semi": true, "singleQuote": true }`)

### Terraform

| Template | Destination | Processing |
|----------|-------------|------------|
| `templates/scaffold/terraform/main.tf.tmpl` | `main.tf` | Replace `__PROJECT_NAME__` with project name |
| `templates/scaffold/terraform/.tflint.hcl` | `.tflint.hcl` | Copy as-is |
| `templates/scaffold/terraform/versions.tf.tmpl` | `versions.tf` | Copy as-is (no substitution needed) |

Create these additional files if they do not exist:

- `variables.tf` — Empty variables file with header comment
- `outputs.tf` — Empty outputs file with header comment
- `terraform.tfvars.example` — Example tfvars with placeholder values

**Important**: Never overwrite existing files. If a destination file already exists,
skip it and note it in the summary output.

---

## Phase 4: Pre-commit Configuration

Generate a `.pre-commit-config.yaml` with language-appropriate hooks if one was not
already copied from templates.

### Python Hooks

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1
    hooks:
      - id: mypy
        additional_dependencies: []
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.22.1
    hooks:
      - id: gitleaks
```

### Go Hooks

```yaml
repos:
  - repo: https://github.com/golangci/golangci-lint
    rev: v1.63.4
    hooks:
      - id: golangci-lint
  - repo: https://github.com/dnephin/pre-commit-golang
    rev: v0.5.1
    hooks:
      - id: go-fmt
      - id: go-vet
      - id: go-build
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.22.1
    hooks:
      - id: gitleaks
```

### Node Hooks

```yaml
repos:
  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v9.18.0
    hooks:
      - id: eslint
        files: \.(ts|tsx|js|jsx)$
        additional_dependencies:
          - eslint
          - typescript-eslint
          - "@eslint/js"
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v4.0.0-alpha.8
    hooks:
      - id: prettier
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.22.1
    hooks:
      - id: gitleaks
```

### Terraform Hooks

```yaml
repos:
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.96.3
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
      - id: terraform_tflint
      - id: terraform_docs
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.22.1
    hooks:
      - id: gitleaks
```

---

## Phase 4.5: Smoke Test Scaffolding (Node.js Web Projects)

For Node.js projects that include a web framework (detected via `next`, `vite`, `remix`,
`nuxt`, `astro`, `gatsby`, or `sveltekit` in `package.json` dependencies):

1. **Seed a starter smoke catalog** for the app — write a workflow-description
   JSON (schema and tiers: see the smoke-manage skill) and append it:

   ```bash
   echo '{"app": "<app>", "id": "homepage-loads", "tier": "Lite",
          "workflow": "Load the homepage; assert 200 and the app shell renders"}' |
     manifest smoke append --stdin --dry-run   # drop --dry-run to write
   ```

2. **Add a note to the summary** suggesting the optional runtime deps and gate:

   ```text
   Smoke testing (optional):
     Playwright + Chromium for deterministic UI steps (see smoke-manage install)
     manifest smoke run --app <app> --tier Lite
   ```

This phase is **non-blocking** — only suggests, does not require installation.
Skip silently if no web framework is detected.

---

## Phase 5: Manifest Agent Integration

Add Manifest agent configuration to the project so that `.claude/`, `.cursor/`,
`.gemini/`, and `.codex/` are wired up from the start.

1. **Create `.claude/` directory** (if it does not exist):

   ```text
   .claude/
   └── settings.local.json   # Empty local settings: {}
   ```

2. **Create `.cursor/` symlinks** (if `.cursor/` does not exist):

   ```bash
   mkdir -p .cursor
   ln -sf ../.claude/skills .cursor/skills 2>/dev/null || true
   ```

3. **Add `.gitignore` entries** (append if not already present):

   ```text
   # Manifest agent outputs
   .claude/.agent_outputs/
   .claude/settings.local.json
   ```

---

## Phase 6: Summary Output

After scaffolding is complete, output a summary in this format:

```markdown
## Scaffold Summary

**Language**: {language}
**Project**: {project-name}
**Directory**: {absolute-path}

### Files Created

| File | Status |
|------|--------|
| pyproject.toml | Created |
| .pre-commit-config.yaml | Created |
| src/my_project/__init__.py | Created |
| tests/test_placeholder.py | Created |
| .claude/settings.local.json | Skipped (exists) |

### Quality Gates Configured

| Tool | Purpose | Config |
|------|---------|--------|
| ruff | Linting + formatting | pyproject.toml [tool.ruff] |
| pytest | Testing | pyproject.toml [tool.pytest] |
| mypy | Type checking | pyproject.toml [tool.mypy] |
| pre-commit | Git hooks | .pre-commit-config.yaml |
| gitleaks | Secret scanning | .pre-commit-config.yaml |

### Next Steps

1. Run `pre-commit install` to activate git hooks
2. Run `{test-command}` to verify the test framework
3. Review and customize the generated configuration files
```

Substitute `{test-command}` with:

- Python: `pytest`
- Go: `make test`
- Node: `npm test`
- Terraform: `terraform validate`

---

## Safety Checks

- **Never overwrite existing files** -- skip and report in summary
- **Never delete files** -- this skill only creates
- **Validate project name** -- reject names with shell metacharacters (`;&|$\`'"`)
- **Check template directory exists** -- if templates are missing, report clearly:

  ```text
  Warning: Template directory not found at templates/scaffold/{language}/
  Generating minimal configuration inline instead.
  ```

  When templates are missing, generate the equivalent configuration inline using
  the specifications in Phase 4 as the reference.

---

## Configuration

Template locations can be customized in `~/.claude/config/command_config.yml`:

```yaml
scaffold:
  template_dir: templates/scaffold
  default_language: null
  manifest_integration: true
```
