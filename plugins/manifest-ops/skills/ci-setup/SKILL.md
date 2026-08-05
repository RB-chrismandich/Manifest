---
name: ci-setup
description: Use when setting up CI/CD for a repo — auto-detects languages, project structure, and hosting platform (GitHub Actions or GitLab CI) to generate pipeline configs.
---

# CI Setup Skill

Configure production-ready CI/CD pipelines by detecting project languages, selecting
appropriate templates, and customizing them for the target repository.

## Inputs

- `$ARGUMENTS` — Optional. Format: `[github|gitlab] [project-path]`
  - If platform is omitted, auto-detect from Git remote.
  - If project-path is omitted, use the current working directory.

## Safety Checks

Before making any changes:

1. **Verify target directory is a Git repository** — abort if not.
2. **Check for existing CI configuration** — if `.github/workflows/` or `.gitlab-ci.yml`
   already exists, warn the user and ask before overwriting.
3. **Never commit or push** — only write files. The user decides when to commit.
4. **Never modify source code** — only create/update CI configuration files.

## Execution Steps

### Step 1: Parse Arguments

```text
Parse $ARGUMENTS to extract:
  - platform: "github" | "gitlab" | auto-detect
  - project_path: absolute path to the target repository (default: cwd)
```

If no platform is specified, detect it:

```bash
# Use git_platform.sh if available, otherwise check remote URL
platform=$(~/.claude/scripts/git_platform.sh 2>/dev/null || echo "github")
```

### Step 2: Detect Project Languages

Scan the project root for language indicators. Check for the presence of:

| Language   | Indicators                                                         |
|------------|--------------------------------------------------------------------|
| Python     | `*.py`, `pyproject.toml`, `setup.cfg`, `requirements*.txt`, `Pipfile` |
| Go         | `*.go`, `go.mod`, `go.sum`                                        |
| Node.js/TS | `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `package.json`                   |
| Terraform  | `*.tf`, `*.tfvars`, `.terraform.lock.hcl`                          |

Record which languages are detected. At least one must be found.

### Step 3: Detect Project Structure

For each detected language, gather details:

**Python:**

- Package manager: `pyproject.toml` (modern) vs `requirements.txt` vs `Pipfile`
- Test framework: check for `pytest.ini`, `setup.cfg [tool:pytest]`, `pyproject.toml [tool.pytest]`
- Python version constraints: parse `pyproject.toml` `requires-python` or `.python-version`

**Go:**

- Go version: parse `go.mod` for `go` directive
- Module path: extract from `go.mod`
- Workspace: check for `go.work`

**Node.js:**

- Package manager: `bun.lock` (bun), `pnpm-lock.yaml` (pnpm), `yarn.lock` (yarn), `package-lock.json` (npm)
- Framework: check `package.json` dependencies for Next.js, Vite, Remix, etc.
- Has TypeScript: check for `tsconfig.json`
- Test runner: check for vitest, jest, mocha in `package.json`
- Scripts available: read `package.json` scripts for `lint`, `test`, `build`, `typecheck`

**Terraform:**

- Backend type: parse `*.tf` for `backend` blocks
- Provider list: parse `required_providers`
- Module structure: check for `modules/` directory

### Step 4: Select and Customize Templates

Templates are located in the Manifest repository (or deployed location):

- **GitHub**: `templates/ci/github/ci.yml`, `security.yml`, `release.yml`
- **GitLab**: `templates/ci/gitlab/.gitlab-ci.yml`

For the canonical template source, check these paths in order:

1. `./templates/ci/` (if running inside the Manifest repo)
2. `~/.claude/../templates/ci/` (if Manifest is deployed)
3. Inline generation as fallback

Read the selected template(s) and customize:

**Customizations to apply:**

1. **Remove unused language blocks** — If the project does not use Go, remove all Go jobs.
   If it does not use Terraform, remove Terraform jobs. Keep only detected languages.

2. **Adjust version matrices** — Replace default versions with detected versions.
   For example, if `go.mod` specifies `go 1.22`, use `['1.22']` instead of `['1.22', '1.23']`.

3. **Match package manager** — For Node.js, if only `pnpm-lock.yaml` exists, simplify the
   package manager detection to just use pnpm directly.

4. **Adjust paths filters** — If all Python code lives under `src/`, narrow the paths filter
   from `**/*.py` to `src/**/*.py`.

5. **Add framework-specific steps** — If Next.js is detected, add `next build` and
   potentially `next lint`. If Django, add `python manage.py check`.

6. **Set Python/Node/Go versions** — Use the project's actual version constraints rather than
   template defaults.

### Step 4.5: E2E Smoke Test Job (Optional)

If `smoke-catalog/` exists in the project and contains `*.yaml` or `*.yml` files,
add a smoke test job running the deterministic `Lite` tier (see the
smoke-manage skill) to the CI pipeline:

**GitHub Actions** — add after the test job:

```yaml
  smoke-tests:
    runs-on: ubuntu-latest
    needs: [test]
    if: hashFiles('smoke-catalog/*.yaml') != '' || hashFiles('smoke-catalog/*.yml') != ''
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install smoke runtime deps
        run: |
          pip install playwright pyyaml
          python3 -m playwright install --with-deps chromium
      - name: Run smoke tests (Lite tier)
        run: manifest smoke run --tier Lite --junit smoke-report.xml
```

**GitLab CI** — add after the test stage:

```yaml
smoke-tests:
  stage: test
  image: python:3.12
  before_script:
    - pip install playwright pyyaml
    - python3 -m playwright install --with-deps chromium
  script:
    - manifest smoke run --tier Lite --junit smoke-report.xml
  rules:
    - exists:
        - smoke-catalog/*.yaml
        - smoke-catalog/*.yml
  allow_failure: true
```

The smoke test job should:

- Run **after** unit tests (dependency/needs)
- Use `allow_failure: true` / `continue-on-error: true` so it does not block the pipeline
- Install Playwright + Chromium in the CI environment (headless)

If `smoke-catalog/` does not exist, skip this step entirely.

### Step 5: Write Configuration Files

**GitHub Actions:**

```text
.github/workflows/ci.yml       — Main CI pipeline
.github/workflows/security.yml — Security scanning
.github/workflows/release.yml  — Automated releases
```

**GitLab CI:**

```text
.gitlab-ci.yml — Complete pipeline (all stages in one file)
```

Create the target directories if they do not exist.

### Step 6: Report Summary

Output a summary of what was created:

```text
## CI/CD Setup Complete

**Platform**: GitHub Actions
**Detected languages**: Python 3.13, Node.js 22
**Package managers**: pip (pyproject.toml), pnpm

### Files created:
- .github/workflows/ci.yml — Multi-language CI (Python + Node.js)
- .github/workflows/security.yml — Dependency audit, secret scan, SAST
- .github/workflows/release.yml — Automated semver releases

### Next steps:
1. Review the generated workflow files
2. Add any required secrets (e.g., CODECOV_TOKEN, SEMGREP_APP_TOKEN)
3. Commit and push to trigger the first pipeline run
4. Configure branch protection rules to require CI to pass
```

## Validation Rules

After writing files, verify:

1. **YAML syntax** — Parse each generated file to confirm valid YAML.
2. **No hardcoded secrets** — Confirm no API keys, tokens, or passwords appear in the output.
3. **Correct indentation** — YAML files must use consistent 2-space indentation.
4. **File permissions** — Generated files should not be executable.

## Output Format

Provide the summary as markdown to the user. Include the full list of created files
with brief descriptions of what each contains and any manual configuration needed.
